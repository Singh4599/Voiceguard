"""
sessions/manager.py — Call session model and session lifecycle manager.

CallSession
-----------
Holds all state for one active phone call:
  - identifiers  (call_id, stream_id, account_id)
  - audio params (sample_rate, encoding, channels, sample_width)
  - counters      (packet_count, bytes_received)
  - timestamps    (started_at, ended_at)
  - audio buffer  (AudioBuffer instance)

SessionManager
--------------
A thin dict-backed registry for active sessions.
  create_session(...)  → CallSession
  get_session(id)      → CallSession | None
  remove_session(id)   → CallSession | None  (and finalises it)

Design: no global variables scattered around; import `session_manager`
(the singleton at the bottom of this file) wherever needed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app import config
from app.audio.buffer import AudioBuffer

logger = logging.getLogger(__name__)


class CallSession:
    """All state for one active phone call."""

    def __init__(
        self,
        *,
        call_id: str,
        stream_id: str,
        account_id: str = "",
        sample_rate: int = config.DEFAULT_SAMPLE_RATE,
        encoding: str = "",
        channels: int = config.DEFAULT_CHANNELS,
        sample_width: int = 2,
        raw_media_format: Optional[dict] = None,
    ) -> None:
        self.call_id: str = call_id
        self.stream_id: str = stream_id
        self.account_id: str = account_id

        # Audio parameters (from Exotel start event)
        self.sample_rate: int = sample_rate
        self.encoding: str = encoding
        self.channels: int = channels
        self.sample_width: int = sample_width
        self.raw_media_format: dict = raw_media_format or {}

        # Timestamps
        self.started_at: datetime = datetime.now(tz=timezone.utc)
        self.ended_at: Optional[datetime] = None

        # Counters
        self.packet_count: int = 0
        self.bytes_received: int = 0

        # Audio buffer (owns complete + chunk buffers)
        self.audio_buffer: AudioBuffer = AudioBuffer(
            call_id=call_id,
            sample_rate=sample_rate,
            channels=channels,
            sample_width=sample_width,
        )

    # ── Convenience helpers ───────────────────────────────────────────────

    @property
    def duration_seconds(self) -> float:
        """Wall-clock duration from call start to now (or ended_at)."""
        end = self.ended_at or datetime.now(tz=timezone.utc)
        return (end - self.started_at).total_seconds()

    @property
    def buffered_duration_seconds(self) -> float:
        return self.audio_buffer.buffered_duration_seconds

    def add_audio(self, pcm_bytes: bytes) -> None:
        """Update counters and feed audio into the buffer."""
        self.packet_count += 1
        self.bytes_received += len(pcm_bytes)
        self.audio_buffer.add_audio(pcm_bytes)

    def finalise(self) -> None:
        """Mark the session as ended and flush any partial chunk."""
        self.ended_at = datetime.now(tz=timezone.utc)
        self.audio_buffer.flush_remaining_chunk()

    def __repr__(self) -> str:
        return (
            f"<CallSession call_id={self.call_id!r} "
            f"packets={self.packet_count} "
            f"duration={self.duration_seconds:.1f}s>"
        )


class SessionManager:
    """
    Registry of currently active CallSessions.

    Thread-safety: VoiceGuard runs inside a single asyncio event loop.
    All WebSocket handlers run as coroutines on that loop, so there is no
    concurrent dict access from multiple OS threads.  If you ever add
    thread-pool workers, add a threading.Lock here.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, CallSession] = {}

    # ── Public API ────────────────────────────────────────────────────────

    def create_session(
        self,
        *,
        call_id: str,
        stream_id: str,
        account_id: str = "",
        sample_rate: int = config.DEFAULT_SAMPLE_RATE,
        encoding: str = "",
        channels: int = config.DEFAULT_CHANNELS,
        sample_width: int = 2,
        raw_media_format: Optional[dict] = None,
    ) -> CallSession:
        """
        Create and register a new CallSession.

        If a session with the same call_id already exists (e.g. duplicate
        start event), the old session is returned unchanged and a warning
        is logged — we never silently drop buffered audio.
        """
        if call_id in self._sessions:
            logger.warning(
                "[SESSION] Session already exists for call_id=%s — "
                "ignoring duplicate start event",
                call_id,
            )
            return self._sessions[call_id]

        session = CallSession(
            call_id=call_id,
            stream_id=stream_id,
            account_id=account_id,
            sample_rate=sample_rate,
            encoding=encoding,
            channels=channels,
            sample_width=sample_width,
            raw_media_format=raw_media_format,
        )
        self._sessions[call_id] = session
        logger.debug("[SESSION] Created session for call_id=%s", call_id)
        return session

    def get_session(self, call_id: str) -> Optional[CallSession]:
        """Return the CallSession for call_id, or None if not found."""
        return self._sessions.get(call_id)

    def remove_session(self, call_id: str) -> Optional[CallSession]:
        """
        Remove and return the CallSession for call_id.
        Calls session.finalise() before returning so the caller can then
        write the recording without worrying about flushing.
        """
        session = self._sessions.pop(call_id, None)
        if session is None:
            logger.warning(
                "[SESSION] remove_session called for unknown call_id=%s", call_id
            )
            return None
        session.finalise()
        return session

    @property
    def active_count(self) -> int:
        return len(self._sessions)

    def active_call_ids(self) -> list[str]:
        return list(self._sessions.keys())


# ---------------------------------------------------------------------------
# Module-level singleton — import this everywhere instead of instantiating
# ---------------------------------------------------------------------------
session_manager: SessionManager = SessionManager()
