"""
app/ai/training/generate_data.py — Synthetic training data generator.

Creates labeled audio samples:
  - Label 0: Real human voices (from recorded call chunks)
  - Label 1: AI-generated / cloned voices (synthesized via gTTS/pyttsx3)

Run:
    cd backend
    python -m app.ai.training.generate_data

Output:
    backend/training_data/real/     ← WAV files of real human speech
    backend/training_data/fake/     ← WAV files of AI-generated speech
"""

from __future__ import annotations

import io
import logging
import math
import os
import random
import struct
import wave
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

TRAINING_DIR = Path(__file__).parent.parent.parent.parent / "training_data"
REAL_DIR = TRAINING_DIR / "real"
FAKE_DIR = TRAINING_DIR / "fake"
SAMPLE_RATE = 8000
DURATION_S = 2.0
N_SAMPLES_PER_CLASS = 200   # 200 real + 200 fake = 400 total


def main() -> None:
    REAL_DIR.mkdir(parents=True, exist_ok=True)
    FAKE_DIR.mkdir(parents=True, exist_ok=True)

    # Copy existing real call chunks if available
    _copy_real_chunks()

    # Generate synthetic real-like voices (varied, natural)
    n_real = len(list(REAL_DIR.glob("*.wav")))
    logger.info("Real samples so far: %d", n_real)
    for i in range(max(0, N_SAMPLES_PER_CLASS - n_real)):
        path = REAL_DIR / f"synthetic_real_{i:04d}.wav"
        _generate_natural_voice(path)

    # Generate AI-clone-like voices (smooth, monotone)
    for i in range(N_SAMPLES_PER_CLASS):
        path = FAKE_DIR / f"ai_clone_{i:04d}.wav"
        _generate_ai_like_voice(path)

    real_count = len(list(REAL_DIR.glob("*.wav")))
    fake_count = len(list(FAKE_DIR.glob("*.wav")))
    logger.info("✅ Dataset ready: %d real, %d fake", real_count, fake_count)


def _copy_real_chunks() -> None:
    """Copy existing recorded call chunks into training_data/real/."""
    chunks_dir = Path(__file__).parent.parent.parent.parent / "chunks"
    if not chunks_dir.exists():
        return
    copied = 0
    for wav_file in list(chunks_dir.glob("*.wav"))[:N_SAMPLES_PER_CLASS]:
        dest = REAL_DIR / f"real_call_{wav_file.name}"
        if not dest.exists():
            import shutil
            shutil.copy2(wav_file, dest)
            copied += 1
    if copied:
        logger.info("Copied %d real call chunks from %s", copied, chunks_dir)


def _generate_natural_voice(path: Path) -> None:
    """
    Generate a WAV that mimics real human speech characteristics:
    - Varying pitch (natural jitter ~2-5%)
    - Amplitude modulation (breathing, stress)
    - Formant-like resonances
    - Pauses / silence bursts
    """
    n = int(SAMPLE_RATE * DURATION_S)
    t = np.linspace(0, DURATION_S, n)

    # Random base pitch between 80-300 Hz
    base_f0 = random.uniform(80, 300)

    # Natural pitch variation: jitter + slow modulation
    jitter = np.random.normal(0, base_f0 * 0.03, n)
    slow_mod = 10 * np.sin(2 * np.pi * 0.5 * t)  # 0.5 Hz slow drift
    f0 = base_f0 + slow_mod + jitter

    # Voice signal: sum of harmonics with random weights
    signal = np.zeros(n)
    for harmonic in range(1, 8):
        weight = random.uniform(0.1, 1.0) / harmonic
        signal += weight * np.sin(2 * np.pi * harmonic * f0 * t)

    # Amplitude modulation (syllable rhythm ~4 Hz)
    syllable_rate = random.uniform(3, 6)
    amplitude = 0.5 + 0.5 * np.abs(np.sin(2 * np.pi * syllable_rate * t))
    # Add shimmer (amplitude noise)
    amplitude *= (1 + np.random.normal(0, 0.08, n))
    signal *= amplitude

    # Add pauses (silence) at random intervals
    pause_prob = 0.15
    for start in range(0, n, int(SAMPLE_RATE * 0.3)):
        if random.random() < pause_prob:
            end = min(start + int(SAMPLE_RATE * 0.1), n)
            signal[start:end] *= 0.05

    # Add slight noise (breathing, background)
    signal += np.random.normal(0, 0.01, n)

    # Normalize and convert to int16
    signal = np.clip(signal / (np.abs(signal).max() + 1e-8) * 0.8, -1, 1)
    _save_wav(path, signal)


def _generate_ai_like_voice(path: Path) -> None:
    """
    Generate a WAV that mimics AI/TTS voice characteristics:
    - Very stable pitch (low jitter < 0.5%)
    - Consistent amplitude (no breathing variation)
    - Too-perfect spectral smoothness
    - No pauses or very mechanical pauses
    """
    n = int(SAMPLE_RATE * DURATION_S)
    t = np.linspace(0, DURATION_S, n)

    # AI voices: stable pitch, very little variation
    base_f0 = random.uniform(100, 250)
    # Very slight drift only (simulating TTS)
    f0 = base_f0 + 0.5 * np.sin(2 * np.pi * 0.1 * t)  # minimal 0.1 Hz drift

    # Clean harmonic signal (no jitter)
    signal = np.zeros(n)
    for harmonic in range(1, 6):
        weight = 1.0 / harmonic  # perfect harmonic decay (too perfect)
        signal += weight * np.sin(2 * np.pi * harmonic * f0 * t)

    # Constant amplitude (no shimmer, no breathing)
    amplitude = 0.7 * np.ones(n)
    # Only very slight modulation
    amplitude += 0.02 * np.sin(2 * np.pi * 3 * t)
    signal *= amplitude

    # Mechanical silence (perfectly timed)
    if random.random() < 0.3:
        pause_start = int(n * random.uniform(0.4, 0.6))
        pause_len = int(SAMPLE_RATE * 0.15)
        signal[pause_start:pause_start + pause_len] = 0

    # Very little noise (AI is clean)
    signal += np.random.normal(0, 0.002, n)

    signal = np.clip(signal / (np.abs(signal).max() + 1e-8) * 0.8, -1, 1)
    _save_wav(path, signal)


def _save_wav(path: Path, signal: np.ndarray) -> None:
    pcm = (signal * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())


if __name__ == "__main__":
    main()
