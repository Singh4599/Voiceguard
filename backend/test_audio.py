"""
test_audio.py — VoiceGuard Phase 1 local audio pipeline test.

Run this script directly (no Exotel connection needed) to verify that:
  1. WAV file generation works correctly.
  2. Chunk duration calculations are accurate.
  3. PCM buffer accumulation and chunking behave as expected.
  4. The μ-law decoder produces valid PCM output.

Usage (from backend/ directory):
    python test_audio.py

All generated test files are written to backend/test_output/.
Inspect them with any audio player (e.g. macOS QuickLook or afplay).
"""

import asyncio
import math
import os
import struct
import sys
import wave
from pathlib import Path

# ── Ensure imports resolve when run from backend/ directly ────────────────
sys.path.insert(0, str(Path(__file__).parent))

from app.audio.buffer import AudioBuffer
from app.audio.decoder import decode_exotel_audio, _ulaw_to_pcm16
from app.audio.wav_writer import pcm_to_wav_bytes, save_wav

OUTPUT_DIR = Path(__file__).parent / "test_output"
OUTPUT_DIR.mkdir(exist_ok=True)

SAMPLE_RATE = 8000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit
CHUNK_DURATION = 2.0  # seconds


# ---------------------------------------------------------------------------
# Helper: generate a pure sine wave as PCM bytes
# ---------------------------------------------------------------------------

def generate_sine_wave(
    frequency_hz: float = 440.0,
    duration_s: float = 1.0,
    sample_rate: int = SAMPLE_RATE,
    amplitude: float = 0.4,
) -> bytes:
    """Return raw 16-bit signed LE PCM bytes for a sine tone."""
    num_samples = int(sample_rate * duration_s)
    samples = bytearray(num_samples * 2)
    for i in range(num_samples):
        val = int(amplitude * 32767 * math.sin(2 * math.pi * frequency_hz * i / sample_rate))
        val = max(-32768, min(32767, val))
        struct.pack_into("<h", samples, i * 2, val)
    return bytes(samples)


# ---------------------------------------------------------------------------
# Test 1: WAV generation
# ---------------------------------------------------------------------------

def test_wav_generation() -> None:
    print("\n[TEST 1] WAV generation")
    pcm = generate_sine_wave(440.0, 3.0)
    path = OUTPUT_DIR / "test_sine_440hz.wav"
    save_wav(path, pcm, sample_rate=SAMPLE_RATE)

    # Verify with wave module
    with wave.open(str(path), "rb") as wf:
        assert wf.getnchannels() == CHANNELS, "Channel mismatch"
        assert wf.getsampwidth() == SAMPLE_WIDTH, "Sample width mismatch"
        assert wf.getframerate() == SAMPLE_RATE, "Sample rate mismatch"
        frames = wf.getnframes()
        duration = frames / SAMPLE_RATE
        assert abs(duration - 3.0) < 0.01, f"Duration mismatch: {duration}"
    print(f"  ✓ WAV written to {path.name}")
    print(f"  ✓ Duration verified: {duration:.2f} s")
    print(f"  ✓ Sample rate: {SAMPLE_RATE} Hz  Channels: {CHANNELS}")


# ---------------------------------------------------------------------------
# Test 2: pcm_to_wav_bytes round-trip
# ---------------------------------------------------------------------------

def test_wav_bytes_roundtrip() -> None:
    print("\n[TEST 2] pcm_to_wav_bytes round-trip")
    pcm = generate_sine_wave(880.0, 1.0)
    wav_bytes = pcm_to_wav_bytes(pcm, SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH)

    # Verify the bytes are a valid WAV
    import io
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getframerate() == SAMPLE_RATE
        assert wf.getnchannels() == CHANNELS
        duration = wf.getnframes() / SAMPLE_RATE
        assert abs(duration - 1.0) < 0.01

    path = OUTPUT_DIR / "test_roundtrip_880hz.wav"
    path.write_bytes(wav_bytes)
    print(f"  ✓ In-memory WAV: {len(wav_bytes)} bytes  duration={duration:.2f}s")
    print(f"  ✓ Saved to {path.name}")


# ---------------------------------------------------------------------------
# Test 3: Chunk duration calculation
# ---------------------------------------------------------------------------

def test_chunk_duration_calculation() -> None:
    print("\n[TEST 3] Chunk duration calculation")
    bytes_per_second = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH
    chunk_bytes = int(bytes_per_second * CHUNK_DURATION)
    print(f"  bytes/sec        = {bytes_per_second}")
    print(f"  chunk_duration   = {CHUNK_DURATION} s")
    print(f"  chunk_bytes      = {chunk_bytes}")
    assert chunk_bytes == 32000, f"Expected 32000, got {chunk_bytes}"
    print("  ✓ Chunk byte threshold correct: 32000 bytes = 2.0 s @ 8 kHz mono 16-bit")


# ---------------------------------------------------------------------------
# Test 4: AudioBuffer chunking
# ---------------------------------------------------------------------------

async def test_audio_buffer_chunking() -> None:
    print("\n[TEST 4] AudioBuffer chunking")
    import shutil
    test_chunks_dir = OUTPUT_DIR / "chunks"
    test_chunks_dir.mkdir(exist_ok=True)

    buf = AudioBuffer(
        call_id="testcall001",
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
        sample_width=SAMPLE_WIDTH,
        chunks_dir=test_chunks_dir,
        chunk_duration_seconds=CHUNK_DURATION,
    )

    # Feed 5 seconds of audio (should produce 2 full chunks + 1 partial)
    five_seconds_pcm = generate_sine_wave(600.0, 5.0)
    chunk_size = 160  # 20 ms packets (typical Exotel packet size at 8 kHz)
    for i in range(0, len(five_seconds_pcm), chunk_size):
        buf.add_audio(five_seconds_pcm[i : i + chunk_size])

    # Allow async tasks (chunk callbacks) to run
    await asyncio.sleep(0.1)

    print(f"  Total bytes buffered : {buf.total_bytes}")
    print(f"  Buffered duration    : {buf.buffered_duration_seconds:.2f} s")
    print(f"  Chunks emitted       : {buf.chunk_count}")

    assert buf.chunk_count == 2, (
        f"Expected 2 full chunks from 5 s of audio, got {buf.chunk_count}"
    )

    # Flush partial remainder
    buf.flush_remaining_chunk()
    await asyncio.sleep(0.1)
    print(f"  Chunks after flush   : {buf.chunk_count}")

    chunk_files = sorted(test_chunks_dir.glob("call_testcall001_chunk_*.wav"))
    print(f"  Chunk files on disk  : {[f.name for f in chunk_files]}")
    assert len(chunk_files) >= 2, "Expected at least 2 chunk WAV files on disk"

    # Verify first chunk is exactly 2 seconds
    with wave.open(str(chunk_files[0]), "rb") as wf:
        dur = wf.getnframes() / wf.getframerate()
        assert abs(dur - 2.0) < 0.01, f"Chunk 1 duration wrong: {dur}"
        print(f"  ✓ Chunk 1 duration: {dur:.2f} s")
    print("  ✓ AudioBuffer chunking works correctly")


# ---------------------------------------------------------------------------
# Test 5: μ-law decoder
# ---------------------------------------------------------------------------

def test_ulaw_decoder() -> None:
    print("\n[TEST 5] μ-law decoder")
    # Generate a μ-law byte sequence (all 256 possible values)
    ulaw_bytes = bytes(range(256))
    pcm_bytes = _ulaw_to_pcm16(ulaw_bytes)
    assert len(pcm_bytes) == 512, f"Expected 512 bytes, got {len(pcm_bytes)}"
    print(f"  ✓ Decoded 256 μ-law bytes → {len(pcm_bytes)} PCM bytes")

    # Verify decode_exotel_audio handles base64 μ-law correctly
    import base64
    b64 = base64.b64encode(ulaw_bytes).decode()
    result = decode_exotel_audio(b64, {"encoding": "pcmu", "sample_rate": 8000})
    assert len(result) == 512
    print("  ✓ decode_exotel_audio with PCMU encoding: correct")

    # Verify passthrough for linear PCM
    pcm_in = generate_sine_wave(300.0, 0.1)
    b64_pcm = base64.b64encode(pcm_in).decode()
    result_pcm = decode_exotel_audio(b64_pcm, {"encoding": "linear16"})
    assert result_pcm == pcm_in
    print("  ✓ decode_exotel_audio with linear16 encoding: passthrough correct")

    # Save a decoded μ-law WAV for listening
    # Use a repeating pattern to make something slightly audible
    ulaw_8bit = bytes([i % 256 for i in range(SAMPLE_RATE * 1)])  # 1 second
    pcm_out = _ulaw_to_pcm16(ulaw_8bit)
    path = OUTPUT_DIR / "test_ulaw_decoded.wav"
    save_wav(path, pcm_out, SAMPLE_RATE)
    print(f"  ✓ μ-law decoded WAV saved: {path.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    print("=" * 55)
    print("  VoiceGuard Phase 1 — Audio Pipeline Test Suite")
    print("=" * 55)

    test_wav_generation()
    test_wav_bytes_roundtrip()
    test_chunk_duration_calculation()
    await test_audio_buffer_chunking()
    test_ulaw_decoder()

    print("\n" + "=" * 55)
    print("  All tests passed ✓")
    print(f"  Test WAV files → {OUTPUT_DIR}")
    print("  Play on macOS: afplay test_output/test_sine_440hz.wav")
    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
