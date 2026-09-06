"""
app/ai/feature_extractor.py — Audio forensics feature extraction.

Extracts features that distinguish REAL human voices from AI-cloned/
TTS-generated voices.  All features are chosen because published
research shows they differ significantly between real and synthetic speech.

Features extracted (total: 49 per chunk)  [optimised for demo speed]
------------------------------------------
1.  MFCC (13)           — Mel-frequency cepstral coefficients, mean
2.  MFCC-delta (13)     — First-order MFCC derivatives (rate of change)
                          [delta2 removed — saves ~15ms CPU per chunk]
3.  Spectral (5)        — Centroid, rolloff, bandwidth, flux, contrast
4.  ZCR (1)             — Zero Crossing Rate
5.  RMS (1)             — Energy (root-mean-square)
6.  Pitch stats (6)     — F0 mean, std, range, voiced_ratio, jitter, shimmer
                          [librosa.yin used — ~10x faster than pyin/Praat]
7.  Chroma (10)         — Pitch class energy distribution

Why these features?
-------------------
- AI voices tend to have VERY stable pitch (low std, low jitter)
- AI voices have unnatural MFCC-delta patterns (too smooth)
- AI voices have consistent RMS (real voices breathe, pause, vary energy)
- Spectral flux is higher in real voices (they move around more)

Perf changes vs original:
- Removed parselmouth/Praat (was blocking event loop for 200-500ms per chunk)
- Replaced librosa.pyin with librosa.yin (~10x faster F0 extraction)
- Dropped MFCC delta2 (saves ~15ms, marginal detection benefit)
"""

from __future__ import annotations

import io
import logging
import wave
from typing import Optional

# pyrefly: ignore [missing-import]
import librosa
import numpy as np

# parselmouth/Praat removed — too slow for real-time demo (200-500ms per chunk).
# F0 extracted via librosa.yin which is ~10x faster.

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
            _mfcc_features(y, sr),        # 26 features (mfcc + delta, no delta2)
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
    """Mean of MFCC + MFCC-delta → 26 values. (delta2 removed for speed)"""
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=N_MFCC)
    delta = librosa.feature.delta(mfcc)
    return np.concatenate([
        mfcc.mean(axis=1),
        delta.mean(axis=1),
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
    Pitch (F0) stats + approximate jitter/shimmer → 6 values.

    Uses librosa.yin (deterministic, ~10x faster than pyin or Praat).
    YIN is a well-established F0 estimation algorithm — adequate for
    distinguishing the unnaturally stable pitch of TTS/AI voices.

    AI voices (simple TTS): f0_std ~0, jitter ~0
    AI voices (ElevenLabs): slightly boosted but still lower than human
    Human voice:            f0_std > 5 Hz, audible jitter > 0.003
    """
    try:
        # librosa.yin is O(N log N) vs pyin's probabilistic HMM — much faster
        f0 = librosa.yin(
            y,
            fmin=float(librosa.note_to_hz("C2")),  # ~65 Hz
            fmax=float(librosa.note_to_hz("C7")),  # ~2093 Hz
            sr=sr,
        )

        # Filter unvoiced frames (yin returns fmax for unvoiced frames)
        fmax = float(librosa.note_to_hz("C7"))
        voiced_mask = f0 < (fmax * 0.95)
        f0_voiced = f0[voiced_mask]

        if len(f0_voiced) < 4:
            return np.zeros(6, dtype=np.float32)

        f0_mean = float(f0_voiced.mean())
        f0_std = float(f0_voiced.std())
        f0_range = float(f0_voiced.max() - f0_voiced.min())
        voiced_ratio = float(voiced_mask.mean())

        # Approximate jitter: mean absolute frame-to-frame F0 variation
        diffs = np.abs(np.diff(f0_voiced))
        jitter = float(diffs.mean() / (f0_mean + 1e-8))

        # Approximate shimmer: amplitude envelope variation
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
