"""
exotel/parser.py — Exotel WebSocket event parsing.

Parses the raw JSON dict that Exotel sends over the WebSocket and returns
typed dataclasses.  All field access goes through this module; if Exotel
ever changes a key name, only this file needs to be updated.

Supported events
----------------
  connected  →  ExotelConnectedEvent
  start      →  ExotelStartEvent
  media      →  ExotelMediaEvent
  stop       →  ExotelStopEvent
  *          →  ExotelUnknownEvent
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ExotelConnectedEvent:
    raw: dict = field(repr=False)


@dataclass
class MediaFormat:
    """Audio format extracted from the Exotel start event."""
    encoding: str = ""
    sample_rate: int = 8000
    channels: int = 1

    # Raw dict kept so future code can access additional keys without
    # requiring a parser change.
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class ExotelStartEvent:
    stream_id: str
    call_id: str
    account_id: str
    media_format: MediaFormat
    raw: dict = field(repr=False)


@dataclass
class ExotelMediaEvent:
    stream_id: str
    call_id: str
    chunk_id: str       # sequence identifier in Exotel payload
    payload: str        # base64 audio string
    raw: dict = field(repr=False)


@dataclass
class ExotelStopEvent:
    stream_id: str
    call_id: str
    raw: dict = field(repr=False)


@dataclass
class ExotelUnknownEvent:
    event: str
    raw: dict = field(repr=False)


# Union type for callers
ExotelEvent = Union[
    ExotelConnectedEvent,
    ExotelStartEvent,
    ExotelMediaEvent,
    ExotelStopEvent,
    ExotelUnknownEvent,
]

# ---------------------------------------------------------------------------
# Public parser
# ---------------------------------------------------------------------------


def parse_event(data: dict) -> ExotelEvent:
    """
    Convert a raw Exotel JSON dict to the appropriate typed event object.

    This function never raises; unknown or malformed events produce an
    ExotelUnknownEvent so the caller can log and continue.
    """
    event_type: str = (data.get("event") or "").lower().strip()

    try:
        if event_type == "connected":
            return _parse_connected(data)
        if event_type == "start":
            return _parse_start(data)
        if event_type == "media":
            return _parse_media(data)
        if event_type == "stop":
            return _parse_stop(data)
    except Exception as exc:
        logger.error(
            "Error parsing Exotel event '%s': %s — returning unknown event",
            event_type,
            exc,
        )

    return ExotelUnknownEvent(event=event_type or "(missing)", raw=data)


# ---------------------------------------------------------------------------
# Internal parsers — each is focused on one event type
# ---------------------------------------------------------------------------


def _parse_connected(data: dict) -> ExotelConnectedEvent:
    return ExotelConnectedEvent(raw=data)


def _parse_media_format(mf_raw: Any) -> MediaFormat:
    """
    Safely extract audio parameters from the media_format section.

    Exotel may send encoding as "audio/x-mulaw", "PCMU", "LINEAR16", etc.
    We normalise to lowercase here so decoder.py can do simple comparisons.
    """
    if not isinstance(mf_raw, dict):
        logger.warning("media_format is not a dict (%r) — using defaults", mf_raw)
        mf_raw = {}

    raw_encoding = str(mf_raw.get("encoding", "") or "").lower().strip()

    # Normalise common Exotel encoding strings to our canonical names
    encoding_map = {
        "audio/x-mulaw": "pcmu",
        "audio/pcmu": "pcmu",
        "mulaw": "pcmu",
        "ulaw": "pcmu",
        "u-law": "pcmu",
        "pcmu": "pcmu",
        "base64": "pcmu",
        "audio/l16": "linear16",
        "audio/pcm": "linear16",
        "linear16": "linear16",
        "l16": "linear16",
        "pcm": "linear16",
        "linear_16": "linear16",
    }
    encoding = encoding_map.get(raw_encoding, raw_encoding)

    # Sample rate — try multiple key spellings that Exotel might use
    sample_rate_raw = (
        mf_raw.get("sample_rate")
        or mf_raw.get("sampleRate")
        or mf_raw.get("rate")
        or 8000
    )
    try:
        sample_rate = int(sample_rate_raw)
    except (TypeError, ValueError):
        sample_rate = 8000

    channels_raw = mf_raw.get("channels", 1) or 1
    try:
        channels = int(channels_raw)
    except (TypeError, ValueError):
        channels = 1

    return MediaFormat(
        encoding=encoding,
        sample_rate=sample_rate,
        channels=channels,
        raw=mf_raw,
    )


def _get_str(data: dict, *keys: str, default: str = "") -> str:
    """Try multiple key names in order; return first non-empty string found."""
    for key in keys:
        val = data.get(key)
        if val is not None:
            return str(val)
    return default


def _parse_start(data: dict) -> ExotelStartEvent:
    # Exotel start event may nest metadata under a "start" key or top-level
    start_block: dict = data.get("start") or data

    stream_id = _get_str(
        data, "streamSid", "stream_sid", "streamId", "stream_id",
        default=_get_str(start_block, "streamSid", "stream_sid", "streamId", "stream_id"),
    )
    call_id = _get_str(
        data, "callSid", "call_sid", "callId", "call_id",
        default=_get_str(start_block, "callSid", "call_sid", "callId", "call_id"),
    )
    account_id = _get_str(
        data, "accountSid", "account_sid", "accountId", "account_id",
        default=_get_str(start_block, "accountSid", "account_sid", "accountId", "account_id"),
    )

    mf_raw = (
        start_block.get("mediaFormat")
        or start_block.get("media_format")
        or data.get("mediaFormat")
        or data.get("media_format")
        or {}
    )
    media_format = _parse_media_format(mf_raw)

    return ExotelStartEvent(
        stream_id=stream_id,
        call_id=call_id,
        account_id=account_id,
        media_format=media_format,
        raw=data,
    )


def _parse_media(data: dict) -> ExotelMediaEvent:
    media_block: dict = data.get("media") or data

    stream_id = _get_str(data, "streamSid", "stream_sid", "streamId", "stream_id")
    call_id = _get_str(
        data, "callSid", "call_sid", "callId", "call_id",
        default=_get_str(media_block, "callSid", "call_sid"),
    )
    chunk_id = _get_str(media_block, "chunk", "chunkId", "chunk_id", "sequence")
    payload = _get_str(media_block, "payload", "data", "audio")

    return ExotelMediaEvent(
        stream_id=stream_id,
        call_id=call_id,
        chunk_id=chunk_id,
        payload=payload,
        raw=data,
    )


def _parse_stop(data: dict) -> ExotelStopEvent:
    stop_block: dict = data.get("stop") or data

    stream_id = _get_str(data, "streamSid", "stream_sid", "streamId", "stream_id",
                          default=_get_str(stop_block, "streamSid", "stream_sid"))
    call_id = _get_str(data, "callSid", "call_sid", "callId", "call_id",
                        default=_get_str(stop_block, "callSid", "call_sid"))

    return ExotelStopEvent(stream_id=stream_id, call_id=call_id, raw=data)
