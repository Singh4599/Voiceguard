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
    Pitch (F0) statistics → 6 values.

    Real voices:  higher jitter, shimmer, pitch variation
    AI voices:    smoother, more consistent pitch
    """
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

        voiced_ratio = voiced_flag.mean()
        f0_mean = f0_voiced.mean()
        f0_std = f0_voiced.std()
        f0_range = f0_voiced.max() - f0_voiced.min()

        # Jitter: cycle-to-cycle pitch variation (simplified)
        diffs = np.abs(np.diff(f0_voiced))
        jitter = diffs.mean() / (f0_mean + 1e-8)

        # Shimmer: amplitude variation alongside pitch
        amplitude = np.abs(y)
        shimmer = amplitude.std() / (amplitude.mean() + 1e-8)

        return np.array([f0_mean, f0_std, f0_range, float(voiced_ratio),
                          jitter, shimmer])
    except Exception:
        return np.zeros(6, dtype=np.float32)


def _chroma_features(y: np.ndarray, sr: int) -> np.ndarray:
    """Chroma energy across 10 pitch classes → 10 values."""
    chroma = librosa.feature.chroma_stft(y=y, sr=sr, n_chroma=10)
    return chroma.mean(axis=1)
