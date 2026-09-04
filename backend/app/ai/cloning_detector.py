"""
app/ai/cloning_detector.py — Custom voice cloning detection model.

Architecture
------------
1.  Feature vector (62 dims) from feature_extractor.py
2.  StandardScaler normalization
3.  RandomForestClassifier (primary, fast, interpretable)
    OR a small MLPClassifier (neural network, higher accuracy)

The model is trained by training/train.py and saved to:
    backend/models/voice_clone_detector.pkl

Usage
-----
    detector = CloningDetector()
    detector.load()               # load trained model
    result = detector.predict(wav_bytes)
    # → DetectionResult(is_clone=True, confidence=0.91, top_features=[...])
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import numpy as np

from app.ai.feature_extractor import extract_features

logger = logging.getLogger(__name__)

# Path where the trained model is saved
MODEL_DIR = Path(__file__).parent.parent.parent / "models"
MODEL_PATH = MODEL_DIR / "voice_clone_detector.pkl"
SCALER_PATH = MODEL_DIR / "scaler.pkl"


@dataclass
class DetectionResult:
    """Result of a single voice cloning detection."""
    is_clone: bool              # True if AI-generated voice detected
    confidence: float           # 0.0 → 1.0 (1.0 = very confident)
    risk_level: str             # "low" | "medium" | "high" | "critical"
    features_extracted: bool    # Whether feature extraction succeeded
    top_indicators: List[str] = field(default_factory=list)
    raw_scores: dict = field(default_factory=dict)

    @property
    def risk_emoji(self) -> str:
        return {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}.get(
            self.risk_level, "⚪"
        )

    def __str__(self) -> str:
        status = "AI CLONE DETECTED" if self.is_clone else "Real Human Voice"
        return (
            f"{self.risk_emoji} {status} | "
            f"Confidence: {self.confidence:.0%} | "
            f"Risk: {self.risk_level.upper()}"
        )


class CloningDetector:
    """
    Voice cloning detector — wraps a trained sklearn pipeline.

    Lifecycle:
        1. Train once:  python -m app.ai.training.train
        2. Load in app: detector = CloningDetector(); detector.load()
        3. Predict:     result = detector.predict(wav_bytes)
    """

    def __init__(self) -> None:
        self._model = None
        self._scaler = None
        self._loaded = False
        self._feature_names = _build_feature_names()

    # ── Public API ────────────────────────────────────────────────────────

    def load(self) -> bool:
        """
        Load the trained model from disk.
        Returns True on success, False if model not found (needs training).
        """
        if not MODEL_PATH.exists() or not SCALER_PATH.exists():
            logger.warning(
                "[DETECTOR] Model not found at %s — run training/train.py first",
                MODEL_PATH,
            )
            return False

        try:
            with open(MODEL_PATH, "rb") as f:
                self._model = pickle.load(f)
            with open(SCALER_PATH, "rb") as f:
                self._scaler = pickle.load(f)
            self._loaded = True
            logger.info("[DETECTOR] Model loaded from %s", MODEL_PATH)
            return True
        except Exception as exc:
            logger.error("[DETECTOR] Failed to load model: %s", exc)
            return False

    def predict(self, wav_bytes: bytes) -> DetectionResult:
        """
        Predict whether the voice in wav_bytes is AI-cloned.

        Parameters
        ----------
        wav_bytes : Complete WAV file bytes for one audio chunk.

        Returns
        -------
        DetectionResult with is_clone, confidence, risk_level, indicators.
        """
        # Step 1: Extract features
        features = extract_features(wav_bytes)
        if features is None:
            return DetectionResult(
                is_clone=False,
                confidence=0.0,
                risk_level="low",
                features_extracted=False,
                top_indicators=["Feature extraction failed — audio too short"],
            )

        features_2d = features.reshape(1, -1)

        # Step 2: Fallback to heuristic if model not trained yet
        if not self._loaded:
            return self._heuristic_predict(features)

        # Step 3: Scale + predict
        try:
            features_scaled = self._scaler.transform(features_2d)
            proba = self._model.predict_proba(features_scaled)[0]
            clone_proba = float(proba[1])  # class 1 = AI clone

            is_clone = clone_proba >= 0.5
            risk = _confidence_to_risk(clone_proba)
            indicators = self._get_top_indicators(features, clone_proba)

            result = DetectionResult(
                is_clone=is_clone,
                confidence=clone_proba,
                risk_level=risk,
                features_extracted=True,
                top_indicators=indicators,
                raw_scores={"clone_prob": clone_proba, "real_prob": float(proba[0])},
            )
            logger.info("[DETECTOR] %s", result)
            return result

        except Exception as exc:
            logger.error("[DETECTOR] Prediction failed: %s", exc)
            return self._heuristic_predict(features)

    def is_ready(self) -> bool:
        """True if model is loaded and ready for inference."""
        return self._loaded

    # ── Heuristic fallback (no trained model needed) ──────────────────────

    def _heuristic_predict(self, features: np.ndarray) -> DetectionResult:
        """
        Rule-based heuristic detection using known AI voice signatures.
        Used when the trained model is not yet available.

        Key heuristics:
        - AI voices: low pitch jitter (index 43), low pitch std (index 41)
        - AI voices: very consistent RMS (low variance = unnatural)
        - AI voices: low spectral flux (index 38 = too smooth)
        """
        indicators = []
        score = 0.0

        # Feature indices (from feature_extractor):
        # 0-12: MFCC means, 13-25: delta, 26-38: delta2
        # 39: spectral centroid, 40: rolloff, 41: bandwidth, 42: flux, 43: contrast
        # 44: ZCR, 45: RMS
        # 46: F0 mean, 47: F0 std, 48: F0 range, 49: voiced_ratio, 50: jitter, 51: shimmer
        # 52-61: chroma

        if len(features) < 52:
            return DetectionResult(False, 0.0, "low", True,
                                   ["Insufficient features for heuristic"])

        # Check 1: Pitch jitter (index 50) — AI voices have very low jitter
        jitter = features[50]
        if jitter < 0.01:
            score += 0.25
            indicators.append(f"Unnaturally low pitch jitter ({jitter:.4f})")

        # Check 2: Pitch std (index 47) — AI voices monotone
        pitch_std = features[47]
        if pitch_std < 10.0 and features[46] > 0:  # has pitch but low variation
            score += 0.25
            indicators.append(f"Monotone pitch (std={pitch_std:.1f} Hz)")

        # Check 3: Spectral flux (index 42) — AI voices very smooth
        flux = features[42]
        if flux < 0.001:
            score += 0.2
            indicators.append(f"Unnaturally smooth spectrum (flux={flux:.6f})")

        # Check 4: Shimmer (index 51) — AI voices have constant amplitude
        shimmer = features[51]
        if shimmer < 0.05:
            score += 0.15
            indicators.append(f"Constant amplitude (shimmer={shimmer:.3f})")

        # Check 5: MFCC-delta (index 13) — AI has smoother transitions
        mfcc_delta_mean = np.abs(features[13:26]).mean()
        if mfcc_delta_mean < 2.0:
            score += 0.15
            indicators.append(f"Unnatural speech transitions (MFCC-Δ={mfcc_delta_mean:.2f})")

        score = min(score, 1.0)
        is_clone = score >= 0.5

        if not indicators:
            indicators = ["Voice patterns appear natural"]

        return DetectionResult(
            is_clone=is_clone,
            confidence=score,
            risk_level=_confidence_to_risk(score),
            features_extracted=True,
            top_indicators=indicators,
            raw_scores={"heuristic_score": score},
        )

    def _get_top_indicators(
        self, features: np.ndarray, clone_prob: float
    ) -> List[str]:
        """Return human-readable top indicators from feature values."""
        indicators = []
        if len(features) < 52:
            return indicators

        pitch_std = features[47]
        jitter = features[50]
        flux = features[42]
        shimmer = features[51]

        if jitter < 0.01:
            indicators.append(f"Low pitch jitter (AI signature): {jitter:.4f}")
        if pitch_std < 10 and features[46] > 0:
            indicators.append(f"Monotone pitch: {pitch_std:.1f} Hz variation")
        if flux < 0.001:
            indicators.append(f"Suspiciously smooth spectrum")
        if shimmer < 0.05:
            indicators.append(f"Unnatural amplitude consistency")
        if not indicators:
            indicators = ["Normal voice characteristics detected"]

        return indicators[:3]


# ---------------------------------------------------------------------------
# Module-level singleton (imported by pipeline.py)
# ---------------------------------------------------------------------------

_detector: Optional[CloningDetector] = None


def get_detector() -> CloningDetector:
    """Return the module-level singleton CloningDetector (lazy init)."""
    global _detector
    if _detector is None:
        _detector = CloningDetector()
        _detector.load()   # loads if model exists, else uses heuristic
    return _detector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _confidence_to_risk(confidence: float) -> str:
    if confidence >= 0.85:
        return "critical"
    if confidence >= 0.65:
        return "high"
    if confidence >= 0.40:
        return "medium"
    return "low"


def _build_feature_names() -> List[str]:
    names = [f"mfcc_{i}" for i in range(13)]
    names += [f"mfcc_delta_{i}" for i in range(13)]
    names += [f"mfcc_delta2_{i}" for i in range(13)]
    names += ["spectral_centroid", "spectral_rolloff", "spectral_bandwidth",
               "spectral_flux", "spectral_contrast"]
    names += ["zcr", "rms"]
    names += ["f0_mean", "f0_std", "f0_range", "voiced_ratio", "jitter", "shimmer"]
    names += [f"chroma_{i}" for i in range(10)]
    return names
