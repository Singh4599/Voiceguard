"""
audio/buffer.py — Dual-purpose audio buffer for VoiceGuard.

Each CallSession owns one AudioBuffer instance.

Two responsibilities:

1. COMPLETE CALL BUFFER
   Accumulates every decoded PCM byte so a full WAV can be written on call end.

2. SLIDING-WINDOW CHUNK EMITTER
   ┌──────────────────────────────────────────────────────────────┐
   │  window  = WINDOW_SECONDS of audio (e.g. 2.0 s)             │
   │  step    = STEP_SECONDS between emissions (e.g. 1.5 s)       │
   │                                                              │
   │  ┤────────── 2s window ──────────────┤                       │
   │         ┤────────── 2s window ──────────────┤                │
   │              ┤──── step ────┤                                │
   │                                                              │
   │  50% overlap ensures no word is ever lost at a chunk         │
   │  boundary — every syllable is fully captured in at least     │
   │  one analysis window.                                        │
   └──────────────────────────────────────────────────────────────┘

3. DECOUPLED CALLBACK
   The AI pipeline is wired in by websocket.py via on_chunk_ready.
   AudioBuffer is completely ignorant of the AI layer — no circular
   imports, and errors surface correctly in logs.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable, Optional

from app import config
from app.audio.wav_writer import pcm_to_wav_bytes, save_wav

logger = logging.getLogger(__name__)

# Type alias for the async callback
ChunkCallback = Callable[[str, int, bytes], Awaitable[None]]


class AudioBuffer:
    """
    Manages incoming PCM audio for a single call.

    Parameters
    ----------
    call_id           : Unique identifier for the call.
    sample_rate       : Audio sample rate in Hz.
    channels          : Number of audio channels (1 = mono).
    sample_width      : Bytes per sample (2 for 16-bit PCM).
    chunks_dir        : Directory where chunk WAV files are saved.
    on_chunk_ready    : Async callback(call_id, chunk_num, wav_bytes).
                        Wired externally — AudioBuffer never imports AI modules.
    window_seconds    : Duration of each analysis window (default 2.0 s).
    step_seconds      : How often to emit a new window (default 1.5 s).
                        step < window means overlapping chunks.
    """

    def __init__(
        self,
        call_id: str,
        sample_rate: int = config.DEFAULT_SAMPLE_RATE,
        channels: int = config.DEFAULT_CHANNELS,
        sample_width: int = 2,
        chunks_dir: Path = config.CHUNKS_DIR,
        on_chunk_ready: Optional[ChunkCallback] = None,
        window_seconds: float = config.CHUNK_DURATION_SECONDS,
        step_seconds: Optional[float] = None,
    ) -> None:
        self.call_id = call_id
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = sample_width
        self.chunks_dir = chunks_dir
        self._on_chunk_ready: Optional[ChunkCallback] = on_chunk_ready

        # ── Sliding window parameters ─────────────────────────────────────
        # step defaults to 75 % of window (25 % overlap)
        self._window_seconds = window_seconds
        self._step_seconds = step_seconds if step_seconds is not None else window_seconds * 0.75

        bps = sample_rate * channels * sample_width  # bytes per second
        self._window_bytes: int = int(bps * self._window_seconds)
        self._step_bytes: int = int(bps * self._step_seconds)

        # ── Buffers ───────────────────────────────────────────────────────
        self._complete_buffer: bytearray = bytearray()
        # Sliding window buffer holds up to window_bytes; we advance by step_bytes
        self._window_buffer: bytearray = bytearray()
        self._chunk_index: int = 0

        logger.info(
            "[BUFFER] call=%s  window=%.1fs  step=%.1fs  overlap=%.0f%%  "
            "window_bytes=%d  step_bytes=%d",
            call_id,
            self._window_seconds,
            self._step_seconds,
            (1.0 - self._step_seconds / self._window_seconds) * 100,
            self._window_bytes,
            self._step_bytes,
        )

    # ── Public interface ───────────────────────────────────────────────────

    def add_audio(self, pcm_bytes: bytes) -> None:
        """
        Feed decoded PCM bytes into both buffers.
        Called from the WebSocket handler for every decoded media packet.
        """
        if not pcm_bytes:
            return

        self._complete_buffer.extend(pcm_bytes)
        self._window_buffer.extend(pcm_bytes)

        # Emit a window whenever the buffer is full, then advance by step_bytes
        while len(self._window_buffer) >= self._window_bytes:
            chunk_pcm = bytes(self._window_buffer[: self._window_bytes])
            # Slide forward: drop one step worth of data, keep the overlap
            self._window_buffer = self._window_buffer[self._step_bytes:]
            self._emit_chunk(chunk_pcm)

    def get_complete_pcm(self) -> bytes:
        """Return all accumulated PCM bytes for the full call recording."""
        return bytes(self._complete_buffer)

    def flush_remaining_chunk(self) -> None:
        """
        Called at call end. Emit leftover audio if >= 25% of a full window,
        so nothing is silently dropped.
        """
        min_bytes = self._window_bytes // 4
        if len(self._window_buffer) >= min_bytes:
            logger.debug(
                "[BUFFER] Flushing partial chunk: %d bytes for call=%s",
                len(self._window_buffer),
                self.call_id,
            )
            self._emit_chunk(bytes(self._window_buffer))
            self._window_buffer = bytearray()

    @property
    def total_bytes(self) -> int:
        return len(self._complete_buffer)

    @property
    def buffered_duration_seconds(self) -> float:
        bps = self.sample_rate * self.channels * self.sample_width
        return len(self._complete_buffer) / bps if bps else 0.0

    @property
    def chunk_count(self) -> int:
        return self._chunk_index

    # ── Internal helpers ───────────────────────────────────────────────────

    def _emit_chunk(self, chunk_pcm: bytes) -> None:
        """Save one chunk WAV file and fire the on_chunk_ready callback."""
        self._chunk_index += 1
        chunk_num = self._chunk_index
        duration_s = len(chunk_pcm) / (
            self.sample_rate * self.channels * self.sample_width
        )

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

        if self._on_chunk_ready is None:
            logger.debug("[BUFFER] No on_chunk_ready callback registered — chunk %d dropped", chunk_num)
            return

        wav_bytes = pcm_to_wav_bytes(
            chunk_pcm,
            sample_rate=self.sample_rate,
            channels=self.channels,
            sample_width=self.sample_width,
        )

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._on_chunk_ready(self.call_id, chunk_num, wav_bytes),
                name=f"chunk-{self.call_id}-{chunk_num}",
            )
        except RuntimeError:
            # No running event loop (e.g. called from sync test code)
            logger.warning("[BUFFER] No running event loop - chunk %d not dispatched", chunk_num)

