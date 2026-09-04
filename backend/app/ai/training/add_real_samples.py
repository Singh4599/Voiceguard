"""
app/ai/training/add_real_samples.py — Add real-world audio to training data.

This script takes actual recordings and adds them to training_data/:
  - Real ElevenLabs AI voice → training_data/fake/
  - Real human call recordings → training_data/real/

Crucially, it simulates the Exotel phone network pipeline:
  WAV → downsample to 8kHz (PCMU-like) → upsample to 16kHz
This makes the training data match exactly what the model sees during live calls.

Run:
    cd backend
    source venv/bin/activate
    python -m app.ai.training.add_real_samples
"""

from __future__ import annotations

import io
import logging
import struct
import wave
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger(__name__)

TRAINING_DIR = Path(__file__).parent.parent.parent.parent / "training_data"
RECORDINGS_DIR = Path(__file__).parent.parent.parent.parent / "recordings"
CHUNK_DURATION = 2.0  # seconds — must match live pipeline


def phone_degrade(y: np.ndarray, orig_sr: int) -> tuple[np.ndarray, int]:
    """
    Simulate Exotel PCMU 8kHz phone degradation pipeline:
    1. Downsample to 8000 Hz (phone quality)
    2. Quantise to 8-bit (PCMU-like) to introduce codec noise
    3. Upsample back to 16000 Hz (what feature_extractor receives)
    This makes synthetic training data match real call audio.
    """
    # Step 1: Downsample to 8kHz
    y8 = librosa.resample(y, orig_sr=orig_sr, target_sr=8000)

    # Step 2: Simulate 8-bit PCMU quantisation noise
    y8_q = np.round(y8 * 127).clip(-128, 127) / 127.0

    # Step 3: Upsample back to 16kHz (what pipeline delivers to model)
    y16 = librosa.resample(y8_q, orig_sr=8000, target_sr=16000)
    return y16, 16000


def chunk_audio(y: np.ndarray, sr: int, label: str, out_dir: Path,
                prefix: str, start_index: int) -> int:
    """Slice audio into CHUNK_DURATION chunks and save as WAV."""
    out_dir.mkdir(parents=True, exist_ok=True)
    chunk_samples = int(CHUNK_DURATION * sr)
    n_chunks = 0

    for i, start in enumerate(range(0, len(y) - chunk_samples + 1, chunk_samples)):
        chunk = y[start: start + chunk_samples]
        # Skip silent chunks (RMS < 0.003)
        rms = np.sqrt(np.mean(chunk ** 2))
        if rms < 0.003:
            logger.debug("  Skipping silent chunk %d (RMS=%.4f)", i, rms)
            continue

        filename = out_dir / f"{prefix}_{start_index + i:05d}.wav"
        sf.write(str(filename), chunk, sr, subtype="PCM_16")
        n_chunks += 1

    return n_chunks


def add_elevenlabs(elevenlabs_path: Path) -> int:
    """Add real ElevenLabs AI voice samples to training_data/fake/."""
    if not elevenlabs_path.exists():
        logger.error("ElevenLabs WAV not found: %s", elevenlabs_path)
        return 0

    logger.info("Loading ElevenLabs WAV: %s", elevenlabs_path.name)
    y, sr = librosa.load(str(elevenlabs_path), sr=None, mono=True)
    logger.info("  Duration: %.1fs  SR: %d Hz", len(y) / sr, sr)

    # Simulate phone degradation so it matches live call audio
    y_phone, sr_phone = phone_degrade(y, sr)
    logger.info("  After phone simulation: %.1fs @ %d Hz", len(y_phone) / sr_phone, sr_phone)

    # Find highest existing fake index to avoid overwriting
    fake_dir = TRAINING_DIR / "fake"
    existing = list(fake_dir.glob("elevenlabs_real_*.wav"))
    start_idx = len(existing)

    n = chunk_audio(y_phone, sr_phone, label="fake",
                    out_dir=fake_dir,
                    prefix="elevenlabs_real",
                    start_index=start_idx)
    logger.info("  ✅ Added %d ElevenLabs chunks to training_data/fake/", n)
    return n


def add_real_calls(recordings_dir: Path) -> int:
    """Add real human call recordings to training_data/real/."""
    # Use the larger recordings (>500KB = at least 15 seconds of audio)
    # These are real human conversations
    wavs = sorted([f for f in recordings_dir.glob("call_*.wav")
                   if f.stat().st_size > 500_000
                   and "AI_CLONE" not in f.name
                   and "TEST" not in f.name])

    if not wavs:
        logger.warning("No suitable real call recordings found in %s", recordings_dir)
        return 0

    logger.info("Found %d large real call recordings", len(wavs))
    real_dir = TRAINING_DIR / "real"
    existing = list(real_dir.glob("real_call_*.wav"))
    start_idx = len(existing)
    total = 0

    for wav_path in wavs:
        logger.info("  Processing: %s (%.0f KB)", wav_path.name,
                    wav_path.stat().st_size / 1024)
        try:
            y, sr = librosa.load(str(wav_path), sr=None, mono=True)
            # These are already 8kHz recordings from Exotel, upsample to 16kHz
            if sr == 8000:
                y16 = librosa.resample(y, orig_sr=8000, target_sr=16000)
                sr = 16000
            else:
                y16 = y

            n = chunk_audio(y16, sr, label="real",
                            out_dir=real_dir,
                            prefix="real_call",
                            start_index=start_idx + total)
            logger.info("    → %d chunks", n)
            total += n
        except Exception as e:
            logger.error("    Failed: %s", e)

    logger.info("✅ Added %d real call chunks to training_data/real/", total)
    return total


def add_ai_clone_recordings(recordings_dir: Path) -> int:
    """Add AI clone test recordings to training_data/fake/."""
    clone_wavs = list(recordings_dir.glob("*AI_CLONE*.wav")) + \
                 list(recordings_dir.glob("*bb04ee8b*.wav"))  # our AI clone test call

    if not clone_wavs:
        logger.info("No AI clone recordings found — skipping")
        return 0

    fake_dir = TRAINING_DIR / "fake"
    existing = list(fake_dir.glob("real_ai_call_*.wav"))
    start_idx = len(existing)
    total = 0

    logger.info("Found %d AI clone call recordings", len(clone_wavs))
    for wav_path in clone_wavs:
        logger.info("  Processing AI clone: %s", wav_path.name)
        try:
            y, sr = librosa.load(str(wav_path), sr=None, mono=True)
            if sr == 8000:
                y16 = librosa.resample(y, orig_sr=8000, target_sr=16000)
                sr = 16000
            else:
                y16 = y

            n = chunk_audio(y16, sr, label="fake",
                            out_dir=fake_dir,
                            prefix="real_ai_call",
                            start_index=start_idx + total)
            total += n
        except Exception as e:
            logger.error("    Failed: %s", e)

    logger.info("✅ Added %d real AI clone chunks to training_data/fake/", total)
    return total


def main():
    elevenlabs_path = Path(
        "/Users/dhruvsingh/Downloads/"
        "ElevenLabs_2026-09-04T06_55_37_Bunty – Reel Perfect Voice"
        "_pvc_sp100_s50_sb75_se0_b_m2 (1).wav"
    )

    logger.info("=" * 60)
    logger.info("Adding real-world audio samples to training data")
    logger.info("=" * 60)

    # Count existing samples
    fake_before = len(list((TRAINING_DIR / "fake").glob("*.wav")))
    real_before = len(list((TRAINING_DIR / "real").glob("*.wav")))
    logger.info("Before: %d fake, %d real", fake_before, real_before)

    # Add real-world AI voice (ElevenLabs)
    n_eleven = add_elevenlabs(elevenlabs_path)

    # Add real-world call recordings
    n_real = add_real_calls(RECORDINGS_DIR)

    # Add AI clone call recordings
    n_ai_calls = add_ai_clone_recordings(RECORDINGS_DIR)

    # Final count
    fake_after = len(list((TRAINING_DIR / "fake").glob("*.wav")))
    real_after = len(list((TRAINING_DIR / "real").glob("*.wav")))

    logger.info("=" * 60)
    logger.info("After: %d fake (+%d), %d real (+%d)",
                fake_after, fake_after - fake_before,
                real_after, real_after - real_before)
    logger.info("ElevenLabs chunks: %d", n_eleven)
    logger.info("Real call chunks : %d", n_real)
    logger.info("AI clone chunks  : %d", n_ai_calls)
    logger.info("=" * 60)
    logger.info("Now run: python -m app.ai.training.train")


if __name__ == "__main__":
    main()
