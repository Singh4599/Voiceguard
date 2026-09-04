"""
audio/buffer.py — Dual-purpose audio buffer for VoiceGuard Phase 1.

Each CallSession owns one AudioBuffer instance.

The buffer has two responsibilities:

1. COMPLETE CALL BUFFER
   Accumulates every decoded PCM byte for the duration of the call so that
   a full-quality WAV recording can be written when the call ends.

2. REAL-TIME CHUNK BUFFER
   Collects decoded PCM bytes and, as soon as ~CHUNK_DURATION_SECONDS worth
   of audio has arrived, emits a chunk.  Chunks are saved to
   backend/chunks/ and trigger the on_audio_chunk() callback.

   ┌─────────────────────────────────────────────────────────┐
   │  Phase 2: Each completed chunk will be forwarded to the │
   │  AI voice deepfake detector (replace the stub below).   │
   └─────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from app import config
from app.audio.wav_writer import pcm_to_wav_bytes, save_wav

logger = logging.getLogger(__name__)


class AudioBuffer:
    """
    Manages incoming PCM audio for a single call.

    Parameters
    ----------
    call_id      : Unique identifier for the call (used in filenames).
    sample_rate  : Audio sample rate in Hz (from Exotel start event).
    channels     : Number of audio channels (1 = mono).
    sample_width : Bytes per sample (2 for 16-bit PCM).
    chunks_dir   : Directory where real-time chunk WAV files are saved.
    chunk_duration_seconds : Target duration for each chunk.
    """

    def __init__(
        self,
        call_id: str,
        sample_rate: int = config.DEFAULT_SAMPLE_RATE,
        channels: int = config.DEFAULT_CHANNELS,
        sample_width: int = 2,
        chunks_dir: Path = config.CHUNKS_DIR,
        chunk_duration_seconds: float = config.CHUNK_DURATION_SECONDS,
    ) -> None:
        self.call_id = call_id
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = sample_width
        self.chunks_dir = chunks_dir
        self.chunk_duration_seconds = chunk_duration_seconds

        # ── Complete call buffer ──────────────────────────────────────────
        self._complete_buffer: bytearray = bytearray()

        # ── Real-time chunk buffer ────────────────────────────────────────
        self._chunk_buffer: bytearray = bytearray()
        self._chunk_index: int = 0

        # Bytes per chunk = sample_rate × channels × sample_width × duration
        self._chunk_bytes_threshold: int = int(
            sample_rate * channels * sample_width * chunk_duration_seconds
        )

        logger.debug(
            "[BUFFER] call=%s  chunk_threshold=%d bytes (%.1f s @ %d Hz)",
            call_id,
            self._chunk_bytes_threshold,
            chunk_duration_seconds,
            sample_rate,
        )

    # ── Public interface ──────────────────────────────────────────────────

    def add_audio(self, pcm_bytes: bytes) -> None:
        """
        Feed decoded PCM bytes into both buffers.
        Call this from the WebSocket handler for every decoded media packet.
        Chunk emission is triggered synchronously here; awaiting is not needed.
        """
        if not pcm_bytes:
            return

        # 1. Append to complete recording buffer
        self._complete_buffer.extend(pcm_bytes)

        # 2. Append to rolling chunk buffer; emit whenever threshold is crossed
        self._chunk_buffer.extend(pcm_bytes)
        while len(self._chunk_buffer) >= self._chunk_bytes_threshold:
            chunk_pcm = bytes(self._chunk_buffer[: self._chunk_bytes_threshold])
            self._chunk_buffer = self._chunk_buffer[self._chunk_bytes_threshold:]
            self._emit_chunk(chunk_pcm)

    def get_complete_pcm(self) -> bytes:
        """Return all accumulated PCM bytes for the full call recording."""
        return bytes(self._complete_buffer)

    def flush_remaining_chunk(self) -> None:
        """
        Called at call end.  If leftover audio in the chunk buffer is long
        enough to be useful (>= 25% of a full chunk), emit it as a partial
        chunk so nothing is silently dropped.
        """
        min_bytes = self._chunk_bytes_threshold // 4
        if len(self._chunk_buffer) >= min_bytes:
            logger.debug(
                "[BUFFER] Flushing partial chunk: %d bytes for call=%s",
                len(self._chunk_buffer),
                self.call_id,
            )
            self._emit_chunk(bytes(self._chunk_buffer))
            self._chunk_buffer = bytearray()

    @property
    def total_bytes(self) -> int:
        return len(self._complete_buffer)

    @property
    def buffered_duration_seconds(self) -> float:
        """Duration of the complete accumulated audio in seconds."""
        bytes_per_second = self.sample_rate * self.channels * self.sample_width
        return len(self._complete_buffer) / bytes_per_second if bytes_per_second else 0.0

    @property
    def chunk_count(self) -> int:
        return self._chunk_index

    # ── Internal helpers ──────────────────────────────────────────────────

    def _emit_chunk(self, chunk_pcm: bytes) -> None:
        """
        Save one chunk WAV file and invoke the async callback.
        """
        self._chunk_index += 1
        chunk_num = self._chunk_index
        duration_s = len(chunk_pcm) / (
            self.sample_rate * self.channels * self.sample_width
        )

        # Build filename: call_<id>_chunk_<NNNN>.wav
        filename = f"call_{self.call_id}_chunk_{chunk_num:04d}.wav"
        chunk_path = self.chunks_dir / filename

        save_wav(
            chunk_path,
            chunk_pcm,
            sample_rate=self.sample_rate,
            channels=self.channels,
            sample_width=self.sample_width,
        )

        logger.info(
            "[CHUNK READY] call=%s  chunk=%d  duration=%.2f s  → %s",
            self.call_id,
            chunk_num,
            duration_s,
            filename,
        )

        # Convert to WAV bytes for the callback (avoids re-reading from disk)
        wav_bytes = pcm_to_wav_bytes(
            chunk_pcm,
            sample_rate=self.sample_rate,
            channels=self.channels,
            sample_width=self.sample_width,
        )

        # Fire-and-forget the async callback without blocking add_audio().
        # asyncio.create_task requires a running loop; schedule safely.
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self.on_audio_chunk(self.call_id, chunk_num, wav_bytes)
            )
        except RuntimeError:
            # No running event loop (e.g. called from sync test code)
            pass

    # ── Callback stub ─────────────────────────────────────────────────────

    async def on_audio_chunk(
        self,
        call_id: str,
        chunk_number: int,
        wav_bytes: bytes,
    ) -> None:
        """
        Called every time a ~CHUNK_DURATION_SECONDS chunk is ready.
        Runs the AI voice cloning detection pipeline on the chunk.

        Parameters
        ----------
        call_id      : The call this chunk belongs to.
        chunk_number : 1-based sequence number for this call.
        wav_bytes    : Complete WAV file bytes (header + PCM data).
        """
        try:
            from app.ai.pipeline import analyze_chunk
            await analyze_chunk(call_id, chunk_number, wav_bytes)
        except ImportError:
            logger.debug(
                "[CHUNK CALLBACK] call=%s  chunk=%d  — AI module not yet installed",
                call_id, chunk_number,
            )
        except Exception as exc:
            logger.error(
                "[CHUNK CALLBACK] call=%s  chunk=%d  AI error: %s",
                call_id, chunk_number, exc,
            )

