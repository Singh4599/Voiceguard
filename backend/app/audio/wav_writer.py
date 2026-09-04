"""
audio/wav_writer.py — WAV file utilities.

Provides two public helpers:
    pcm_to_wav_bytes(pcm_bytes, sample_rate, channels, sample_width)
        → bytes   (in-memory WAV, suitable for streaming or saving)

    save_wav(path, pcm_bytes, sample_rate, channels, sample_width)
        → None    (write WAV file to disk)

Uses only Python's built-in `wave` module — no external dependencies.
The WAV header is generated correctly by the wave module; we never rename
raw PCM bytes to .wav.
"""

from __future__ import annotations

import io
import logging
import wave
from pathlib import Path

logger = logging.getLogger(__name__)


def pcm_to_wav_bytes(
    pcm_bytes: bytes,
    sample_rate: int,
    channels: int = 1,
    sample_width: int = 2,  # 2 bytes = 16-bit PCM
) -> bytes:
    """
    Wrap raw linear PCM bytes in a proper WAV container and return as bytes.

    Parameters
    ----------
    pcm_bytes    : Raw linear-16 PCM audio data.
    sample_rate  : e.g. 8000 (Hz).
    channels     : 1 = mono, 2 = stereo.
    sample_width : Bytes per sample — 2 for 16-bit PCM.

    Returns
    -------
    bytes : Complete WAV file including RIFF header.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def save_wav(
    path: Path | str,
    pcm_bytes: bytes,
    sample_rate: int,
    channels: int = 1,
    sample_width: int = 2,
) -> None:
    """
    Write raw linear PCM bytes to a WAV file at `path`.

    Parameters
    ----------
    path         : Destination file path (created or overwritten).
    pcm_bytes    : Raw linear-16 PCM audio data.
    sample_rate  : e.g. 8000 (Hz).
    channels     : 1 = mono, 2 = stereo.
    sample_width : Bytes per sample (2 for 16-bit PCM).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)

    logger.info("WAV saved → %s  (%.2f s)", path.name,
                len(pcm_bytes) / (sample_rate * channels * sample_width))
