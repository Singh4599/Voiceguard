"""
app/ai/feature_extractor.py — Enhanced audio forensics feature extraction.

Features extracted (total: 84 per chunk)
------------------------------------------
1.  MFCC means      (13)   — Mel-frequency cepstral coefficients, mean per band
2.  MFCC variance   (13)   — NEW: Temporal variance of each MFCC band
                              AI voices have unnaturally LOW variance (too smooth)
3.  MFCC-delta      (13)   — First-order MFCC derivatives (rate of change)
4.  MFCC-delta2     (13)   — Second-order MFCC derivatives (acceleration)
                              Re-enabled — delta2 captures AI smoothness
5.  Spectral        (7)    — Centroid, rolloff, bandwidth, flux, contrast,
                              entropy (NEW), flatness (NEW)
6.  ZCR + RMS       (2)    — Zero Crossing Rate, energy
7.  Pitch/Prosody   (8)    — F0 mean, std, range, voiced_ratio, jitter, shimmer,
                              HNR approx (NEW), F0 velocity (NEW)
8.  Chroma          (10)   — Pitch class energy distribution
9.  Voice Quality   (5)    — NEW: Cepstral peak prominence proxy, RMS variance,
                              ZCR variance, spectral rolloff variance, energy entropy

Total: 13+13+13+13+7+2+8+10+5 = 84 features

Why new features help:
-  MFCC variance: AI voices are temporally consistent (low var) — very strong signal
-  Spectral entropy: AI voices have lower spectral entropy (too ordered)
-  Spectral flatness: tonal vs noise-like (AI = more tonal = lower flatness)
-  HNR: human voices have noise in their harmonics; AI = cleaner
-  F0 velocity: frame-to-frame F0 change rate (AI = smoother transitions)
-  RMS variance: humans breathe, pause — energy varies; AI = flat energy
"""

from __future__ import annotations

import io
import logging
import wave
from typing import Optional

import librosa
import numpy as np

logger = logging.getLogger(__name__)

N_MFCC = 13
TARGET_SR = 16000


def extract_features(wav_bytes: bytes) -> Optional[np.ndarray]:
    """
    Extract a fixed-length feature vector from WAV audio bytes.

    Returns np.ndarray of shape (84,) or None if extraction fails.
    """
    try:
        y, sr = _load_wav_bytes(wav_bytes)
        if y is None or len(y) < 512:
            logger.warning("[FEATURES] Audio too short to extract features")
            return None

        # Voice Activity Detection — skip silent frames
        rms = librosa.feature.rms(y=y).mean()
        if rms < 0.005:
            logger.info("[FEATURES] Audio is silent (RMS=%.4f). Skipping.", rms)
            return None

        if sr != TARGET_SR:
            y = librosa.resample(y, orig_sr=sr, target_sr=TARGET_SR)
            sr = TARGET_SR

        features = np.concatenate([
            _mfcc_features(y, sr),         # 52 features (mean+var+delta+delta2)
            _spectral_features(y, sr),     # 7 features
            _zcr_rms_features(y),          # 2 features
            _pitch_features(y, sr),        # 8 features
            _chroma_features(y, sr),       # 10 features
            _voice_quality_features(y, sr),# 5 features
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

        dtype_map = {1: np.int8, 2: np.int16, 4: np.int32}
        dtype = dtype_map.get(sampwidth, np.int16)
        pcm = np.frombuffer(frames, dtype=dtype).astype(np.float32)
        pcm /= np.iinfo(dtype).max

        if n_channels == 2:
            pcm = pcm.reshape(-1, 2).mean(axis=1)

        return pcm, sr
    except Exception as exc:
        logger.error("[FEATURES] WAV load failed: %s", exc)
        return None, 0


def _mfcc_features(y: np.ndarray, sr: int) -> np.ndarray:
    """
    Mean + Variance of MFCC + MFCC-delta + MFCC-delta2 → 52 values.

    Adding variance is KEY for AI detection:
    - AI voice MFCC is temporally very consistent → low variance
    - Human voice varies naturally → higher variance
    """
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=N_MFCC)
    delta = librosa.feature.delta(mfcc)
    delta2 = librosa.feature.delta(mfcc, order=2)

    return np.concatenate([
        mfcc.mean(axis=1),    # 13: MFCC means
        mfcc.var(axis=1),     # 13: MFCC temporal variance (AI = very low)
        delta.mean(axis=1),   # 13: MFCC delta means
        delta2.mean(axis=1),  # 13: MFCC delta2 means
    ])


def _spectral_features(y: np.ndarray, sr: int) -> np.ndarray:
    """
    Spectral centroid, rolloff, bandwidth, flux, contrast,
    entropy (NEW), flatness (NEW) → 7 values.
    """
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr).mean()
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr).mean()
    bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr).mean()

    stft = np.abs(librosa.stft(y))

    # Spectral flux: mean change between frames
    flux = np.mean(np.diff(stft, axis=1) ** 2)

    # Spectral contrast
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr).mean()

    # Spectral entropy — AI voices have lower entropy (more ordered spectrum)
    # Compute per-frame power spectrum, normalize to probability dist, then entropy
    power = stft ** 2 + 1e-10
    power_norm = power / (power.sum(axis=0, keepdims=True) + 1e-10)
    frame_entropy = -np.sum(power_norm * np.log2(power_norm + 1e-10), axis=0)
    spectral_entropy = float(frame_entropy.mean())

    # Spectral flatness — ratio of geometric mean to arithmetic mean of spectrum
    # AI voices tend to be more tonal (lower flatness) vs human (noisier = higher)
    flatness = float(librosa.feature.spectral_flatness(y=y).mean())

    return np.array([centroid, rolloff, bandwidth, flux, contrast,
                     spectral_entropy, flatness])


def _zcr_rms_features(y: np.ndarray) -> np.ndarray:
    """Zero crossing rate + RMS energy → 2 values."""
    zcr = librosa.feature.zero_crossing_rate(y).mean()
    rms = librosa.feature.rms(y=y).mean()
    return np.array([zcr, rms])


def _pitch_features(y: np.ndarray, sr: int) -> np.ndarray:
    """
    Pitch (F0) stats + jitter/shimmer + HNR approx + F0 velocity → 8 values.

    NEW features:
    - HNR (Harmonic-to-Noise Ratio): AI voices have unnaturally high HNR
      (perfect harmonics, no noise floor). Human voices always have some noise.
    - F0 velocity: mean abs frame-to-frame F0 change. AI = very smooth curves.
    """
    try:
        f0 = librosa.yin(
            y,
            fmin=float(librosa.note_to_hz("C2")),  # ~65 Hz
            fmax=float(librosa.note_to_hz("C7")),  # ~2093 Hz
            sr=sr,
        )

        fmax = float(librosa.note_to_hz("C7"))
        voiced_mask = f0 < (fmax * 0.95)
        f0_voiced = f0[voiced_mask]

        if len(f0_voiced) < 4:
            return np.zeros(8, dtype=np.float32)

        f0_mean = float(f0_voiced.mean())
        f0_std = float(f0_voiced.std())
        f0_range = float(f0_voiced.max() - f0_voiced.min())
        voiced_ratio = float(voiced_mask.mean())

        # Jitter: mean absolute frame-to-frame F0 variation (normalized)
        diffs = np.abs(np.diff(f0_voiced))
        jitter = float(diffs.mean() / (f0_mean + 1e-8))

        # Shimmer: amplitude envelope variation
        amplitude = np.abs(y)
        shimmer = float(amplitude.std() / (amplitude.mean() + 1e-8))

        # HNR approximation: ratio of voiced energy to total energy
        # Higher HNR = more harmonic = more AI-like
        voiced_frames = librosa.effects.split(y, top_db=20)
        if len(voiced_frames) > 0:
            voiced_energy = sum(np.sum(y[s:e]**2) for s, e in voiced_frames)
            total_energy = np.sum(y**2) + 1e-10
            hnr_approx = float(voiced_energy / total_energy)
        else:
            hnr_approx = 0.0

        # F0 velocity: mean abs frame-to-frame change in F0
        # AI voices have very smooth F0 contours (low velocity = suspicious)
        f0_velocity = float(np.abs(np.diff(f0_voiced)).mean()) if len(f0_voiced) > 1 else 0.0

        return np.array([f0_mean, f0_std, f0_range, voiced_ratio,
                         jitter, shimmer, hnr_approx, f0_velocity],
                        dtype=np.float32)
    except Exception:
        return np.zeros(8, dtype=np.float32)


def _chroma_features(y: np.ndarray, sr: int) -> np.ndarray:
    """Chroma energy across 10 pitch classes → 10 values."""
    chroma = librosa.feature.chroma_stft(y=y, sr=sr, n_chroma=10)
    return chroma.mean(axis=1)


def _voice_quality_features(y: np.ndarray, sr: int) -> np.ndarray:
    """
    Additional voice quality features → 5 values.

    - RMS variance: humans breathe/pause → energy varies; AI = flat energy
    - ZCR variance: human articulation varies ZCR; AI = consistent
    - Spectral rolloff variance: AI rolloff is too steady
    - Energy entropy: distribution of energy across frames (AI = uniform)
    - MFCC1 variance: first MFCC captures overall spectral shape — AI = stable
    """
    try:
        # RMS per frame variance
        rms_frames = librosa.feature.rms(y=y)[0]
        rms_var = float(rms_frames.var())

        # ZCR per frame variance
        zcr_frames = librosa.feature.zero_crossing_rate(y)[0]
        zcr_var = float(zcr_frames.var())

        # Spectral rolloff variance
        rolloff_frames = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
        rolloff_var = float(rolloff_frames.var())

        # Energy entropy: how uniformly distributed is energy across frames?
        # AI = very uniform (low entropy might mean too consistent)
        rms_norm = rms_frames / (rms_frames.sum() + 1e-10)
        energy_entropy = float(-np.sum(rms_norm * np.log2(rms_norm + 1e-10)))

        # MFCC-1 variance (captures broadband spectral shape variability)
        mfcc1 = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=1)[0]
        mfcc1_var = float(mfcc1.var())

        return np.array([rms_var, zcr_var, rolloff_var, energy_entropy, mfcc1_var],
                        dtype=np.float32)
    except Exception:
        return np.zeros(5, dtype=np.float32)
