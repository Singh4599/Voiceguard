"""
audio/decoder.py — Exotel audio decoding.

Responsibilities
----------------
* Accept a raw base64 payload string and the media_format dict from the
  Exotel `start` event.
* Base64-decode → raw bytes.
* If the encoding is μ-law (PCMU), convert to linear-16 PCM using the
  Python standard-library `audioop` module (available on CPython ≤ 3.12).
  A pure-Python fallback ulaw_to_linear() is provided for environments
  where audioop is absent (e.g. some stripped builds / Python 3.13+).
* Return raw linear-16 PCM bytes that can be written directly into WAV
  files without further transformation.

Design note
-----------
All codec knowledge is confined here.  The rest of the pipeline only ever
sees linear PCM bytes; adding a new codec means only touching this file.
"""

from __future__ import annotations

import base64
import logging
import struct

from app import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# μ-law (PCMU) decoding tables / helpers
# ---------------------------------------------------------------------------

# Pre-built μ-law → linear-16 lookup table (256 entries).
# Formula: ITU-T G.711
_ULAW_BIAS = 0x84
_ULAW_CLIP = 32635

_ULAW_TO_LINEAR: list[int] = []


def _build_ulaw_table() -> None:
    for i in range(256):
        ulaw = ~i & 0xFF
        sign = (ulaw & 0x80)
        exponent = (ulaw >> 4) & 0x07
        mantissa = ulaw & 0x0F
        sample = ((mantissa << 3) + _ULAW_BIAS) << exponent
        sample -= _ULAW_BIAS
        _ULAW_TO_LINEAR.append(-sample if sign else sample)


_build_ulaw_table()


def _pure_python_ulaw_to_pcm16(ulaw_bytes: bytes) -> bytes:
    """Convert μ-law bytes to signed 16-bit little-endian PCM (pure Python)."""
    out = bytearray(len(ulaw_bytes) * 2)
    for idx, byte in enumerate(ulaw_bytes):
        sample = _ULAW_TO_LINEAR[byte]
        # Clamp to int16 range
        sample = max(-32768, min(32767, sample))
        struct.pack_into("<h", out, idx * 2, sample)
    return bytes(out)


def _ulaw_to_pcm16(ulaw_bytes: bytes) -> bytes:
    """
    Convert μ-law audio bytes to linear PCM-16 LE bytes.
    Prefers `audioop.ulaw2lin` (C-extension, fast).  Falls back to the
    pure-Python table if audioop is unavailable.
    """
    try:
        import audioop  # type: ignore[import]
        return audioop.ulaw2lin(ulaw_bytes, 2)
    except ImportError:
        logger.debug("audioop not available — using pure-Python μ-law decoder")
        return _pure_python_ulaw_to_pcm16(ulaw_bytes)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def decode_exotel_audio(payload_b64: str, media_format: dict) -> bytes:
    """
    Decode one Exotel `media` event payload into raw linear-16 PCM bytes.

    Parameters
    ----------
    payload_b64 : str
        The base64-encoded audio string from the Exotel `media` event.
    media_format : dict
        The `media_format` dict extracted from the Exotel `start` event.
        Expected keys (Exotel naming): "encoding", "sample_rate", "channels".
        Missing keys are handled gracefully.

    Returns
    -------
    bytes
        Linear PCM 16-bit little-endian audio bytes, mono unless the
        start event explicitly indicated stereo.
    """
    # Step 1 — base64 decode
    try:
        raw_bytes: bytes = base64.b64decode(payload_b64)
    except Exception as exc:
        logger.error("base64 decode failed: %s", exc)
        return b""

    if not raw_bytes:
        return b""

    # Step 2 — determine encoding from start-event metadata
    encoding: str = media_format.get("encoding", "").lower().strip()

    # Normalise common variant spellings.
    # NOTE: Exotel reports encoding as "base64" — this refers to the transport
    # encoding of the payload, not the audio codec.  Exotel always sends μ-law
    # (PCMU/G.711u) audio, so we treat "base64" as an alias for "pcmu".
    if encoding in (config.ENCODING_PCMU, "ulaw", "u-law", "g711u", "audio/pcmu",
                    "mulaw", "base64"):
        # μ-law → linear PCM-16
        pcm_bytes = _ulaw_to_pcm16(raw_bytes)
        logger.debug(
            "Decoded PCMU → PCM16: %d μ-law bytes → %d PCM bytes",
            len(raw_bytes),
            len(pcm_bytes),
        )
        return pcm_bytes

    if encoding in (config.ENCODING_PCM, config.ENCODING_LINEAR16, "l16", "linear",
                    "audio/l16", "audio/pcm", "pcm16", "linear_16"):
        # Already linear PCM — pass through unchanged
        logger.debug("Audio is linear PCM (%d bytes), passing through", len(raw_bytes))
        return raw_bytes

    # Unknown encoding — log a warning and pass bytes through unchanged.
    # This allows the system to record something even if the codec is novel.
    logger.warning(
        "Unknown encoding '%s' — passing raw bytes through unchanged. "
        "WAV files may sound corrupted.  Update decoder.py to handle this codec.",
        encoding or "(empty)",
    )
    return raw_bytes
