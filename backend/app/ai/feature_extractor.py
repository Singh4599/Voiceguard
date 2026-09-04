"""
app/ai/feature_extractor.py — Audio forensics feature extraction.

Extracts features that distinguish REAL human voices from AI-cloned/
TTS-generated voices.  All features are chosen because published
research shows they differ significantly between real and synthetic speech.

Features extracted (total: 62 per chunk)
------------------------------------------
1.  MFCC (13)           — Mel-frequency cepstral coefficients, mean
2.  MFCC-delta (13)     — First-order MFCC derivatives (rate of change)
3.  MFCC-delta2 (13)    — Second-order derivatives (acceleration)
4.  Spectral (5)        — Centroid, rolloff, bandwidth, flux, contrast
5.  ZCR (1)             — Zero Crossing Rate
6.  RMS (1)             — Energy (root-mean-square)
7.  Pitch stats (6)     — F0 mean, std, range, voiced_ratio, jitter, shimmer
8.  Chroma (10)         — Pitch class energy distribution (real voices vary more)

Why these features?
-------------------
- AI voices tend to have VERY stable pitch (low std, low jitter)
- AI voices have unnatural MFCC-delta patterns (too smooth)
- AI voices have consistent RMS (real voices breathe, pause, vary energy)
- Spectral flux is higher in real voices (they move around more)
"""

from __future__ import annotations

import io
import logging
import wave
from typing import Optional

# pyrefly: ignore [missing-import]
import librosa
import numpy as np

# Praat-grade jitter/shimmer via parselmouth (optional but highly recommended)
try:
    # pyrefly: ignore [missing-import]
    import parselmouth
    # pyrefly: ignore [missing-import]
    from parselmouth.praat import call as praat_call
    PRAAT_AVAILABLE = True
except ImportError:
    PRAAT_AVAILABLE = False

logger = logging.getLogger(__name__)

# Number of MFCC coefficients to extract
N_MFCC = 13
# Target sample rate for feature extraction
TARGET_SR = 16000


def extract_features(wav_bytes: bytes) -> Optional[np.ndarray]:
    """
    Extract a fixed-length feature vector from WAV audio bytes.

    Parameters
    ----------
    wav_bytes : bytes
        Complete WAV file bytes (header + PCM data).

    Returns
    -------
    np.ndarray of shape (62,) or None if extraction fails.
    """
    try:
        y, sr = _load_wav_bytes(wav_bytes)
        if y is None or len(y) < 512:
            logger.warning("[FEATURES] Audio too short to extract features")
            return None

        # ── Voice Activity Detection (VAD) ──
        # Silence/phone static has ~0 pitch and shimmer, causing false AI flags.
        # Skip extraction if audio is practically silent.
        rms = librosa.feature.rms(y=y).mean()
        if rms < 0.005:
            logger.info("[FEATURES] Audio is silent (RMS=%.4f). Skipping.", rms)
            return None

        # Resample to standard rate if needed
        if sr != TARGET_SR:
            y = librosa.resample(y, orig_sr=sr, target_sr=TARGET_SR)
            sr = TARGET_SR

        features = np.concatenate([
            _mfcc_features(y, sr),        # 39 features
            _spectral_features(y, sr),    # 5 features
            _zcr_rms_features(y),         # 2 features
            _pitch_features(y, sr),       # 6 features
            _chroma_features(y, sr),      # 10 features
        ])

        logger.debug("[FEATURES] Extracted %d features", len(features))
        return features.astype(np.float32)

    except Exception as exc:
        logger.error("[FEATURES] Extraction failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _load_wav_bytes(wav_bytes: bytes):
    """Load WAV bytes → (y: np.ndarray float32, sr: int)."""
    try:
        with io.BytesIO(wav_bytes) as buf:
            with wave.open(buf, "rb") as wf:
                sr = wf.getframerate()
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                frames = wf.readframes(wf.getnframes())

        # Convert raw bytes → float32 in [-1, 1]
        dtype_map = {1: np.int8, 2: np.int16, 4: np.int32}
        dtype = dtype_map.get(sampwidth, np.int16)
        pcm = np.frombuffer(frames, dtype=dtype).astype(np.float32)
        pcm /= np.iinfo(dtype).max

        # Mono mix if stereo
        if n_channels == 2:
            pcm = pcm.reshape(-1, 2).mean(axis=1)

        return pcm, sr
    except Exception as exc:
        logger.error("[FEATURES] WAV load failed: %s", exc)
        return None, 0


def _mfcc_features(y: np.ndarray, sr: int) -> np.ndarray:
    """Mean of MFCC, MFCC-delta, MFCC-delta2 → 39 values."""
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=N_MFCC)
    delta = librosa.feature.delta(mfcc)
    delta2 = librosa.feature.delta(mfcc, order=2)
    return np.concatenate([
        mfcc.mean(axis=1),
        delta.mean(axis=1),
        delta2.mean(axis=1),
    ])


def _spectral_features(y: np.ndarray, sr: int) -> np.ndarray:
    """Spectral centroid, rolloff, bandwidth, flux, contrast → 5 values."""
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr).mean()
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr).mean()
    bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr).mean()

    # Spectral flux: mean change between frames (higher = more natural variation)
    stft = np.abs(librosa.stft(y))
    flux = np.mean(np.diff(stft, axis=1) ** 2)

    # Spectral contrast (mean across sub-bands)
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr).mean()

    return np.array([centroid, rolloff, bandwidth, flux, contrast])


def _zcr_rms_features(y: np.ndarray) -> np.ndarray:
    """Zero crossing rate + RMS energy → 2 values."""
    zcr = librosa.feature.zero_crossing_rate(y).mean()
    rms = librosa.feature.rms(y=y).mean()
    return np.array([zcr, rms])


def _pitch_features(y: np.ndarray, sr: int) -> np.ndarray:
    """
    Pitch (F0) + Praat-grade Jitter/Shimmer → 6 values.

    Uses parselmouth (Python Praat) for clinically-validated jitter/shimmer.
    This is the GOLD STANDARD used in forensic voice analysis.

    AI voices (simple TTS): jitter < 0.001, shimmer < 0.01
    AI voices (ElevenLabs): jitter > 0.018, shimmer > 0.06 (over-injected)
    Human voice:            jitter 0.003-0.015, shimmer 0.02-0.06
    """
    # ── Praat path (parselmouth installed) ───────────────────────────────
    try:
        if not PRAAT_AVAILABLE:
            raise RuntimeError("parselmouth not installed")

        sound = parselmouth.Sound(y, sampling_frequency=float(sr))

        # Extract pitch via autocorrelation (robust on 8kHz phone audio)
        pitch_obj = praat_call(
            sound, "To Pitch (ac)",
            0.0,    # time step (auto)
            75.0,   # min pitch Hz
            600.0,  # max pitch Hz
            False,  # very accurate
            0.03,   # silence threshold
            0.45,   # voicing threshold
            0.01,   # octave cost
            0.35,   # octave-jump cost
            0.14,   # voiced/unvoiced cost
            500.0,  # max candidates
        )

        # Collect voiced F0 values safely
        times = pitch_obj.xs()
        f0_values = []
        for t in times:
            v = pitch_obj.get_value_at_time(t)
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                f0_values.append(float(v))

        if len(f0_values) < 4:
            return np.zeros(6, dtype=np.float32)

        f0_arr = np.array(f0_values, dtype=np.float32)
        f0_mean = float(f0_arr.mean())
        f0_std = float(f0_arr.std())
        f0_range = float(f0_arr.max() - f0_arr.min())
        voiced_ratio = float(len(f0_values)) / float(max(len(times), 1))

        # Praat PointProcess for jitter/shimmer
        point_process = praat_call(sound, "To PointProcess (periodic, cc)", 75.0, 600.0)

        # Jitter (local) — AI voices: ~0.000 or >0.018 (over-injected)
        try:
            jitter = praat_call(point_process, "Get jitter (local)", 0.0, 0.0, 0.0001, 0.02, 1.3)
            jitter = float(jitter) if jitter is not None else 0.0
            if np.isnan(jitter):
                jitter = 0.0
        except Exception:
            jitter = 0.0

        # Shimmer (local) — AI voices: ~0.000 or >0.06 (over-injected)
        try:
            shimmer = praat_call(
                [sound, point_process], "Get shimmer (local)",
                0.0, 0.0, 0.0001, 0.02, 1.3, 1.6
            )
            shimmer = float(shimmer) if shimmer is not None else 0.0
            if np.isnan(shimmer):
                shimmer = 0.0
        except Exception:
            shimmer = 0.0

        return np.array([f0_mean, f0_std, f0_range, voiced_ratio, jitter, shimmer],
                        dtype=np.float32)

    except Exception:
        pass  # Fall through to librosa fallback

    # ── Fallback: librosa approximation if parselmouth fails ─────────────
    try:
        f0, voiced_flag, _ = librosa.pyin(
            y,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C7"),
            sr=sr,
        )
        f0_voiced = f0[voiced_flag & ~np.isnan(f0)]
        if len(f0_voiced) < 4:
            return np.zeros(6, dtype=np.float32)
        f0_mean = float(f0_voiced.mean())
        f0_std = float(f0_voiced.std())
        f0_range = float(f0_voiced.max() - f0_voiced.min())
        voiced_ratio = float(voiced_flag.mean())
        diffs = np.abs(np.diff(f0_voiced))
        jitter = float(diffs.mean() / (f0_mean + 1e-8))
        amplitude = np.abs(y)
        shimmer = float(amplitude.std() / (amplitude.mean() + 1e-8))
        return np.array([f0_mean, f0_std, f0_range, voiced_ratio, jitter, shimmer],
                        dtype=np.float32)
    except Exception:
        return np.zeros(6, dtype=np.float32)




def _chroma_features(y: np.ndarray, sr: int) -> np.ndarray:
    """Chroma energy across 10 pitch classes → 10 values."""
    chroma = librosa.feature.chroma_stft(y=y, sr=sr, n_chroma=10)
    return chroma.mean(axis=1)
