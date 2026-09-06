"""
exotel/websocket.py — FastAPI WebSocket handler for Exotel AgentStream.

This module owns the /ws/exotel endpoint and co-ordinates between:
  - parser.py     : JSON → typed events
  - sessions/     : CallSession lifecycle
  - audio/decoder : base64 + codec → linear PCM
  - audio/buffer  : PCM → chunk WAVs + complete recording
  - audio/wav_writer : write final recording to disk

The handler is intentionally thin.  All business logic lives in the
modules above; this file is just the glue.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import WebSocket, WebSocketDisconnect

from app import config
from app.audio.decoder import decode_exotel_audio
from app.audio.wav_writer import save_wav
from app.exotel.parser import (
    ExotelConnectedEvent,
    ExotelMediaEvent,
    ExotelStartEvent,
    ExotelStopEvent,
    ExotelUnknownEvent,
    parse_event,
)
from app.sessions.manager import CallSession, session_manager
from app.ai import pipeline as ai_pipeline
import app.dashboard_ws as dashboard_ws
import app.reports_db as reports_db

logger = logging.getLogger(__name__)


async def handle_exotel_websocket(websocket: WebSocket) -> None:
    """
    Accept and serve a single Exotel AgentStream WebSocket connection.

    Exotel sends UTF-8 JSON text frames.  Each frame is one event.
    Media packets arrive at high frequency (typically every 20 ms).
    """
    await websocket.accept()
    logger.info("[EXOTEL] WebSocket connected  (client=%s)", websocket.client)

    # Track the call_id for this connection so we can finalise on disconnect.
    active_call_id: str | None = None

    # Keep the media_format dict from the start event alive for decoding.
    # Keyed by call_id in case Exotel ever multiplexes (unlikely but safe).
    media_formats: dict[str, dict] = {}

    try:
        while True:
            # ── Receive one message ───────────────────────────────────────
            try:
                raw_text = await websocket.receive_text()
            except WebSocketDisconnect:
                raise  # handled in outer except

            # ── Parse JSON ────────────────────────────────────────────────
            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError as exc:
                logger.warning("[EXOTEL] Malformed JSON received — skipping: %s", exc)
                continue

            if not isinstance(data, dict):
                logger.warning("[EXOTEL] Expected JSON object, got %s — skipping", type(data))
                continue

            event = parse_event(data)

            # ── Dispatch ──────────────────────────────────────────────────
            if isinstance(event, ExotelConnectedEvent):
                _handle_connected(event)

            elif isinstance(event, ExotelStartEvent):
                active_call_id = event.call_id
                media_formats[event.call_id] = event.media_format.raw
                _handle_start(event)

            elif isinstance(event, ExotelMediaEvent):
                mf = media_formats.get(
                    event.call_id,
                    media_formats.get(active_call_id or "", {}),
                )
                await _handle_media(event, mf)

            elif isinstance(event, ExotelStopEvent):
                await _handle_stop(event)
                active_call_id = None

            elif isinstance(event, ExotelUnknownEvent):
                logger.info("[EXOTEL] Unknown event: %s", event.event)

    except WebSocketDisconnect:
        logger.warning("[EXOTEL] WebSocket disconnected unexpectedly")
        # Attempt to finalise any buffered audio so recordings are not lost.
        if active_call_id:
            logger.info(
                "[EXOTEL] Attempting emergency finalise for call_id=%s",
                active_call_id,
            )
            await _finalise_call(active_call_id)

    except Exception as exc:
        logger.exception("[EXOTEL] Unhandled error in WebSocket handler: %s", exc)
        if active_call_id:
            await _finalise_call(active_call_id)


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


def _handle_connected(event: ExotelConnectedEvent) -> None:
    logger.info("[EXOTEL] Connection accepted")


def _handle_start(event: ExotelStartEvent) -> None:
    mf = event.media_format

    sample_width = 2  # 2 bytes = 16-bit PCM (post-decoding)

    session = session_manager.create_session(
        call_id=event.call_id or f"unknown_{datetime.now(tz=timezone.utc).timestamp():.0f}",
        stream_id=event.stream_id,
        account_id=event.account_id,
        sample_rate=mf.sample_rate,
        encoding=mf.encoding,
        channels=mf.channels,
        sample_width=sample_width,
        raw_media_format=mf.raw,
    )

    # Wire the AI pipeline callback HERE, in the layer that knows about both
    # audio and AI. AudioBuffer stays ignorant of the AI module entirely.
    session.audio_buffer._on_chunk_ready = ai_pipeline.analyze_chunk

    logger.info(
        "[CALL START]\n"
        "  Call ID    : %s\n"
        "  Stream ID  : %s\n"
        "  Account ID : %s\n"
        "  Sample Rate: %d Hz\n"
        "  Encoding   : %s\n"
        "  Channels   : %d",
        event.call_id or "(unknown)",
        event.stream_id or "(unknown)",
        event.account_id or "(unknown)",
        mf.sample_rate,
        mf.encoding or "(unknown)",
        mf.channels,
    )


async def _handle_media(event: ExotelMediaEvent, media_format_raw: dict) -> None:
    """Decode one media packet and feed it into the session buffer."""
    if not event.payload:
        logger.debug("[MEDIA] Empty payload for call=%s — skipping", event.call_id)
        return

    # Resolve session — try event.call_id first, then fall back to active call
    session: CallSession | None = session_manager.get_session(event.call_id)
    if session is None and event.call_id == "":
        # Some providers omit callSid from media frames; try the active session
        active_ids = session_manager.active_call_ids()
        if active_ids:
            session = session_manager.get_session(active_ids[0])
    if session is None:
        # Exotel sometimes sends media before start; use defaults silently.
        logger.debug(
            "[MEDIA] No session for call_id=%s — packet dropped", event.call_id
        )
        return

    # Decode audio
    pcm_bytes = decode_exotel_audio(event.payload, session.raw_media_format)
    if not pcm_bytes:
        return

    # Feed into session
    session.add_audio(pcm_bytes)

    # Throttled progress log
    if session.packet_count % config.AUDIO_LOG_EVERY_N_PACKETS == 0:
        logger.info(
            "[AUDIO] call=%s  packets=%d  bytes_received=%d  buffered=%.1f s",
            session.call_id,
            session.packet_count,
            session.bytes_received,
            session.buffered_duration_seconds,
        )


async def _handle_stop(event: ExotelStopEvent) -> None:
    await _finalise_call(event.call_id)


async def _finalise_call(call_id: str) -> None:
    """Finalise a call: write recording to disk and remove session."""
    session = session_manager.remove_session(call_id)
    if session is None:
        logger.warning("[CALL STOP] No session found for call_id=%s", call_id)
        return

    # Build recording filename
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"call_{call_id}_{ts}.wav"
    recording_path = config.RECORDINGS_DIR / filename

    pcm = session.audio_buffer.get_complete_pcm()

    if pcm:
        save_wav(
            recording_path,
            pcm,
            sample_rate=session.sample_rate,
            channels=session.channels,
            sample_width=session.sample_width,
        )
        logger.info(
            "[CALL STOP]\n"
            "  Call ID   : %s\n"
            "  Duration  : %.1f s\n"
            "  Packets   : %d\n"
            "  Chunks    : %d\n"
            "  Recording : recordings/%s",
            call_id,
            session.duration_seconds,
            session.packet_count,
            session.audio_buffer.chunk_count,
            filename,
        )
    else:
        logger.warning(
            "[CALL STOP] call_id=%s — no audio received, no WAV written",
            call_id,
        )

    # Get AI Summary before cleanup
    ai_summary = ai_pipeline.get_call_summary(call_id)
    
    # Save Report
    report = {
        "call_id": call_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(session.duration_seconds, 1),
        "max_confidence": ai_summary["max_confidence"],
        "risk_level": ai_summary["risk_level"],
        "recording_url": f"/recordings/{filename}" if pcm else None,
    }
    reports_db.save_report(report)

    # Tell the dashboard the call ended and clean up AI state
    ai_pipeline.cleanup_call_sync(call_id)
    await dashboard_ws.broadcast_call_end(call_id)
