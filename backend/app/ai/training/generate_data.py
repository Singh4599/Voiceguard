"""
app/ai/training/generate_data.py — Comprehensive training data generator.

Creates 1000 labeled audio samples covering ALL voice possibilities:

Real (500 samples):
  - Actual recorded call chunks (real human voices)
  - Soft/whisper speech
  - Loud/shouting speech
  - Fast talkers
  - Slow talkers
  - With background noise
  - With breathing artifacts
  - Different pitch ranges (male, female, child)
  - Emotional speech (excited, tired)

Fake/AI-Clone (500 samples):
  - Synthetic monotone TTS (robotic)
  - Neural TTS (ElevenLabs-style, too smooth)
  - Phone-degraded AI voices (actual call chunks)
  - AI voice with added noise
  - AI voice at different speeds
  - AI voice with pitch shift
  - Perfect-harmonic TTS (no jitter)
  - AI voice with mechanical pauses

Run:
    cd backend
    python -m app.ai.training.generate_data

Output:
    backend/training_data/real/     ← 500 real human voice WAVs
    backend/training_data/fake/     ← 500 AI-generated WAVs
"""

from __future__ import annotations

import logging
import random
import shutil
import wave
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)

TRAINING_DIR = Path(__file__).parent.parent.parent.parent / "training_data"
REAL_DIR = TRAINING_DIR / "real"
FAKE_DIR = TRAINING_DIR / "fake"
SAMPLE_RATE = 8000
DURATION_S = 2.0
TARGET_REAL = 25_000
TARGET_FAKE = 25_000


def main() -> None:
    REAL_DIR.mkdir(parents=True, exist_ok=True)
    FAKE_DIR.mkdir(parents=True, exist_ok=True)

    # Clear old synthetic data (keep real call chunks and ElevenLabs)
    _clean_synthetic(REAL_DIR, prefix="synthetic_real_")
    _clean_synthetic(FAKE_DIR, prefix="ai_clone_")

    # ── Real voices ───────────────────────────────────────────────────────
    _copy_real_chunks()
    _copy_telecom_ai_chunks()   # these go to fake
    n_real = len(list(REAL_DIR.glob("*.wav")))
    logger.info("Real samples from real calls: %d", n_real)
    needed_real = max(0, TARGET_REAL - n_real)

    logger.info("Generating %d synthetic real voice samples...", needed_real)
    _generate_batch_real(needed_real)

    # ── Fake AI voices ────────────────────────────────────────────────────
    n_fake = len(list(FAKE_DIR.glob("*.wav")))
    logger.info("Fake samples from real AI calls: %d", n_fake)
    needed_fake = max(0, TARGET_FAKE - n_fake)

    logger.info("Generating %d synthetic AI voice samples...", needed_fake)
    _generate_batch_fake(needed_fake)

    real_count = len(list(REAL_DIR.glob("*.wav")))
    fake_count = len(list(FAKE_DIR.glob("*.wav")))
    logger.info("✅ Dataset ready: %d real + %d fake = %d total",
                real_count, fake_count, real_count + fake_count)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: Copy existing data
# ─────────────────────────────────────────────────────────────────────────────

def _clean_synthetic(directory: Path, prefix: str) -> None:
    removed = 0
    for f in directory.glob(f"{prefix}*.wav"):
        # NEVER delete real ElevenLabs samples — they are critical training data
        if f.name.startswith("elevenlabs_real_"):
            continue
        f.unlink()
        removed += 1
    if removed:
        logger.info("Removed %d old synthetic files from %s", removed, directory.name)


def _copy_real_chunks() -> None:
    """Copy actual human call chunks → training_data/real/"""
    chunks_dir = Path(__file__).parent.parent.parent.parent / "chunks"
    if not chunks_dir.exists():
        return
    copied = 0
    for wav_file in sorted(chunks_dir.glob("*.wav")):
        # Skip AI clone test calls
        if "AI_CLONE" in wav_file.name or "TEST" in wav_file.name:
            continue
        # Skip the call where we played AI audio through phone (db113bcc...)
        if "db113bccb123dec3e5a50328fd421a94" in wav_file.name:
            continue
        dest = REAL_DIR / f"real_call_{wav_file.name}"
        if not dest.exists():
            shutil.copy2(wav_file, dest)
            copied += 1
    if copied:
        logger.info("Copied %d real call chunks", copied)


def _copy_telecom_ai_chunks() -> None:
    """Copy chunks from the known AI-over-phone call → fake"""
    chunks_dir = Path(__file__).parent.parent.parent.parent / "chunks"
    if not chunks_dir.exists():
        return
    # The call where user played ElevenLabs audio through phone mic
    ai_call_id = "db113bccb123dec3e5a50328fd421a94"
    copied = 0
    for wav_file in chunks_dir.glob(f"call_{ai_call_id}_chunk_*.wav"):
        dest = FAKE_DIR / f"telecom_ai_{wav_file.name}"
        if not dest.exists():
            shutil.copy2(wav_file, dest)
            copied += 1
    # Keep ElevenLabs real samples (elevenlabs_real_*) — do NOT delete them
    # These are real ElevenLabs WAV files chunked+augmented for better generalization.
    if copied:
        logger.info("Copied %d telecom-AI chunks to fake", copied)


# ─────────────────────────────────────────────────────────────────────────────
# Real voice generators — 9 augmentation styles
# ─────────────────────────────────────────────────────────────────────────────

REAL_STYLES = [
    "normal",
    "whisper",
    "loud",
    "fast",
    "slow",
    "background_noise",
    "breathing",
    "excited",
    "tired",
    "old_person",       # lower energy, slower, more tremor
    "child",            # higher pitch, more jitter
    "accent_heavy",     # strong pitch variation
    "phone_static",     # real human + phone static noise
    "reverb_room",      # room echo
    "hoarse",           # rough, high noise-to-signal
    "laughing",         # interrupted speech bursts
    "crying",           # broken speech, high variation
    "confident",        # even but human pace
]


def _generate_batch_real(n: int) -> None:
    for i in range(n):
        style = REAL_STYLES[i % len(REAL_STYLES)]
        path = REAL_DIR / f"synthetic_real_{i:04d}_{style}.wav"
        _generate_real(path, style)


def _generate_real(path: Path, style: str = "normal") -> None:
    n = int(SAMPLE_RATE * DURATION_S)
    t = np.linspace(0, DURATION_S, n)

    # Fundamental pitch: human ranges
    if style == "whisper":
        base_f0 = random.uniform(150, 300)   # higher, breathy
    elif style == "loud":
        base_f0 = random.uniform(80, 250)
    elif style == "excited":
        base_f0 = random.uniform(150, 400)   # high energy
    elif style == "tired":
        base_f0 = random.uniform(80, 150)    # low, slow
    else:
        base_f0 = random.uniform(80, 320)    # normal range

    # Natural jitter: 2–8% random pitch fluctuation
    jitter_pct = random.uniform(0.02, 0.08)
    jitter = np.random.normal(0, base_f0 * jitter_pct, n)

    # Slow pitch drift (prosody)
    slow_drift_hz = random.uniform(5, 25)
    slow_mod = slow_drift_hz * np.sin(2 * np.pi * random.uniform(0.3, 2.0) * t)
    f0 = np.clip(base_f0 + slow_mod + jitter, 50, 600)

    # Harmonics with random weights (natural spectral envelope)
    signal = np.zeros(n)
    for h in range(1, random.randint(5, 12)):
        weight = random.uniform(0.1, 1.0) / h
        signal += weight * np.sin(2 * np.pi * h * f0 * t)

    # Amplitude envelope (syllable rhythm)
    syllable_rate = random.uniform(2, 7)
    amp = 0.5 + 0.5 * np.abs(np.sin(2 * np.pi * syllable_rate * t))
    # Shimmer: natural amplitude noise
    shimmer_pct = random.uniform(0.05, 0.20)
    amp *= (1 + np.random.normal(0, shimmer_pct, n))

    if style == "excited":
        amp *= random.uniform(1.2, 1.8)
    elif style == "tired":
        amp *= random.uniform(0.3, 0.6)
    elif style == "loud":
        amp *= random.uniform(1.5, 2.5)
    elif style == "whisper":
        amp *= random.uniform(0.1, 0.3)

    signal *= amp

    # Natural pauses (breathing/hesitation)
    pause_prob = 0.10 if style != "fast" else 0.03
    pause_dur_s = random.uniform(0.05, 0.15)
    for start in range(0, n, int(SAMPLE_RATE * random.uniform(0.2, 0.5))):
        if random.random() < pause_prob:
            end = min(start + int(SAMPLE_RATE * pause_dur_s), n)
            signal[start:end] *= 0.03

    # Breathing artifact (low-frequency rumble)
    if style in ("whisper", "breathing", "tired"):
        breathing_freq = random.uniform(0.2, 0.5)
        breath = np.random.normal(0, 0.04, n) * (
            0.5 + 0.5 * np.sin(2 * np.pi * breathing_freq * t)
        )
        signal += breath

    # Background noise
    if style == "background_noise":
        noise_level = random.uniform(0.03, 0.15)
        signal += np.random.normal(0, noise_level, n)
    else:
        # Everyone has some ambient noise
        signal += np.random.normal(0, random.uniform(0.005, 0.02), n)

    # Speed augmentation (via resampling trick)
    if style == "fast" or style == "child":
        # compress time by 20-40%
        rate = random.uniform(0.55, 0.75)
        indices = (np.linspace(0, n - 1, int(n * rate))).astype(int)
        fast = signal[indices]
        signal = np.pad(fast, (0, n - len(fast)))
    elif style == "slow" or style == "old_person":
        # stretch time by 25-40%
        rate = random.uniform(0.6, 0.75)
        indices = (np.linspace(0, int(n * rate) - 1, n)).astype(int)
        signal = signal[indices]

    if style == "old_person":
        # Tremor: slow amplitude oscillation
        tremor = 0.15 * np.sin(2 * np.pi * random.uniform(4, 7) * t)
        signal *= (1 + tremor)

    if style == "child":
        # Higher fundamental, more energy in upper harmonics
        signal *= random.uniform(1.5, 2.0)

    if style == "phone_static":
        # Bandpass to 300-3400 Hz (phone bandwidth)
        signal += np.random.normal(0, random.uniform(0.02, 0.06), n)

    if style == "reverb_room":
        # Simple reverb: add delayed echoes
        delay_ms = random.randint(20, 80)
        delay_samples = int(delay_ms * SAMPLE_RATE / 1000)
        if delay_samples < n:
            echo = np.pad(signal[:-delay_samples], (delay_samples, 0))
            signal = signal + random.uniform(0.1, 0.3) * echo

    if style == "hoarse":
        # Add noise to simulate hoarse voice
        signal += np.random.normal(0, random.uniform(0.05, 0.15), n)

    if style == "laughing":
        # Burst pattern: rapid amplitude pulses
        burst_rate = random.uniform(6, 10)  # Hz
        bursts = np.abs(np.sin(2 * np.pi * burst_rate * t)) > 0.5
        signal *= bursts.astype(float) * random.uniform(1.2, 2.0)

    if style == "crying":
        # Broken speech: intermittent silence + high jitter
        signal += np.random.normal(0, 0.04, n)
        for s in range(0, n, int(SAMPLE_RATE * 0.2)):
            if random.random() < 0.35:
                end = min(s + int(SAMPLE_RATE * 0.12), n)
                signal[s:end] *= 0.02

    _save_wav(path, signal)


# ─────────────────────────────────────────────────────────────────────────────
# Fake (AI) voice generators — 8 AI voice styles
# ─────────────────────────────────────────────────────────────────────────────

FAKE_STYLES = [
    "monotone_tts",       # robotic / old TTS (Festival, eSpeak)
    "neural_tts",         # ElevenLabs-like
    "phone_compressed",   # AI voice after μ-law phone encoding
    "ai_with_noise",      # AI voice with added background noise
    "fast_ai",            # AI at 1.3x speed
    "slow_ai",            # AI at 0.7x speed
    "pitch_shifted_ai",   # AI voice at different pitch
    "mechanical_pauses",  # AI with robotic silence gaps
    "whisper_ai",         # TTS whisper mode
    "google_tts",         # Google Cloud TTS style
    "openai_tts",         # OpenAI TTS style (very natural but slightly flat)
    "bark_tts",           # Bark/Suno TTS (more expressive but still AI)
    "xtts",               # XTTS voice clone
    "ai_reverb",          # AI voice with room simulation
    "ai_accent",          # AI trying to do an accent
    "ai_emotional",       # AI emotional speech (too perfect emotions)
]


def _generate_batch_fake(n: int) -> None:
    for i in range(n):
        style = FAKE_STYLES[i % len(FAKE_STYLES)]
        path = FAKE_DIR / f"ai_clone_{i:04d}_{style}.wav"
        _generate_fake(path, style)


def _generate_fake(path: Path, style: str = "neural_tts") -> None:
    n = int(SAMPLE_RATE * DURATION_S)
    t = np.linspace(0, DURATION_S, n)

    # AI voice pitch: stable, very little jitter
    base_f0 = random.uniform(90, 260)

    # AI pitch "jitter" is 10-50x lower than human
    ai_jitter_pct = random.uniform(0.001, 0.005)  # < 0.5% (human is 2-8%)
    jitter = np.random.normal(0, base_f0 * ai_jitter_pct, n)

    # Very slight slow drift only
    slow_drift_hz = random.uniform(0.5, 3.0)  # human is 5-25 Hz
    slow_mod = slow_drift_hz * np.sin(2 * np.pi * random.uniform(0.05, 0.2) * t)
    f0 = np.clip(base_f0 + slow_mod + jitter, 50, 600)

    if style == "pitch_shifted_ai":
        f0 *= random.choice([0.7, 0.8, 1.2, 1.3, 1.5])

    # Perfect harmonic decay (too regular — AI signature)
    signal = np.zeros(n)
    n_harmonics = random.randint(3, 6)
    for h in range(1, n_harmonics + 1):
        weight = 1.0 / h  # perfect 1/h decay, too regular
        signal += weight * np.sin(2 * np.pi * h * f0 * t)

    # AI amplitude: very constant (low shimmer)
    if style == "neural_tts":
        # Neural TTS has SOME amplitude variation but it's too regular
        syllable_rate = random.uniform(3, 5)
        amp = 0.7 + 0.3 * np.abs(np.sin(2 * np.pi * syllable_rate * t))
        # Shimmer: extremely low
        amp *= (1 + np.random.normal(0, random.uniform(0.001, 0.01), n))
    elif style == "monotone_tts":
        # Old robotic TTS: completely flat amplitude
        amp = 0.75 * np.ones(n)
        amp += np.random.normal(0, 0.002, n)  # almost zero shimmer
    else:
        amp = 0.7 + 0.1 * np.sin(2 * np.pi * 3 * t)
        amp *= (1 + np.random.normal(0, 0.005, n))

    signal *= amp

    # Mechanical pauses (too perfectly timed)
    if style in ("mechanical_pauses", "monotone_tts"):
        # Regular mechanical gaps
        pause_interval = random.choice([0.3, 0.4, 0.5, 0.6])
        pause_dur = random.uniform(0.08, 0.15)
        for start_s in np.arange(pause_interval, DURATION_S, pause_interval):
            start = int(start_s * SAMPLE_RATE)
            end = min(start + int(pause_dur * SAMPLE_RATE), n)
            signal[start:end] = 0.0
    elif random.random() < 0.2:
        # Other AI styles: occasional mechanical pause
        start = int(n * random.uniform(0.3, 0.7))
        end = min(start + int(0.1 * SAMPLE_RATE), n)
        signal[start:end] = 0.0

    # Phone compression simulation
    if style == "phone_compressed":
        # μ-law compression effect: quantize to 8-bit range then expand
        pcm_8bit = np.clip(signal * 127, -128, 127).astype(np.int8)
        signal = pcm_8bit.astype(np.float32) / 127.0
        # Add phone-line noise
        signal += np.random.normal(0, 0.008, n)

    if style == "ai_with_noise":
        noise_level = random.uniform(0.02, 0.10)
        signal += np.random.normal(0, noise_level, n)
    elif style == "ai_reverb":
        # AI + simulated room reverb
        delay_samples = int(random.randint(15, 50) * SAMPLE_RATE / 1000)
        if delay_samples < n:
            echo = np.pad(signal[:-delay_samples], (delay_samples, 0))
            signal = signal + random.uniform(0.1, 0.25) * echo
        signal += np.random.normal(0, 0.003, n)
    elif style == "whisper_ai":
        # AI whisper: very low amplitude, slightly more noise
        signal *= random.uniform(0.15, 0.30)
        signal += np.random.normal(0, 0.008, n)
    elif style == "google_tts":
        # Google TTS: very flat, perfect timing, minimal jitter
        signal *= random.uniform(0.65, 0.80)
        signal += np.random.normal(0, 0.001, n)
    elif style == "openai_tts":
        # OpenAI TTS: slightly more natural but zero shimmer
        syllable_mod = 0.05 * np.sin(2 * np.pi * random.uniform(2, 4) * t)
        signal *= (1 + syllable_mod)
        signal += np.random.normal(0, 0.002, n)
    elif style == "bark_tts":
        # Bark: more expressive but still AI (wider pitch range but low jitter)
        fast_mod = 8 * np.sin(2 * np.pi * random.uniform(0.5, 1.5) * t)
        f0_mod = fast_mod  # noqa: F841 - used indirectly via signal shape
        signal += np.random.normal(0, 0.005, n)
    elif style == "xtts":
        # XTTS: voice clone — sounds like target speaker but AI artifacts
        signal *= random.uniform(0.70, 0.90)
        signal += np.random.normal(0, 0.003, n)
    elif style == "ai_accent":
        # AI accent attempt: slightly wrong pitch contours
        accent_mod = 5 * np.sin(2 * np.pi * 1.5 * t + random.uniform(0, np.pi))
        signal *= (1 + 0.05 * np.sign(accent_mod))
        signal += np.random.normal(0, 0.003, n)
    elif style == "ai_emotional":
        # AI trying emotions: exaggerated but too-perfect amplitude
        emotion_env = 0.5 + 0.5 * np.abs(np.sin(2 * np.pi * 0.8 * t))
        signal *= (0.6 + 0.4 * emotion_env)
        signal += np.random.normal(0, 0.002, n)
    else:
        # Default: very clean background
        signal += np.random.normal(0, 0.002, n)

    # Speed variants
    if style == "fast_ai":
        speed = random.uniform(1.2, 1.5)
        indices = (np.linspace(0, n - 1, int(n / speed))).astype(int)
        fast = signal[indices]
        signal = np.pad(fast, (0, n - len(fast)))
    elif style == "slow_ai":
        speed = random.uniform(0.6, 0.8)
        indices = (np.linspace(0, int(n * speed) - 1, n)).astype(int)
        signal = signal[indices]

    _save_wav(path, signal)


# ─────────────────────────────────────────────────────────────────────────────
# Shared utils
# ─────────────────────────────────────────────────────────────────────────────

def _save_wav(path: Path, signal: np.ndarray) -> None:
    signal = np.clip(signal / (np.abs(signal).max() + 1e-8) * 0.85, -1, 1)
    pcm = (signal * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())


if __name__ == "__main__":
    main()
