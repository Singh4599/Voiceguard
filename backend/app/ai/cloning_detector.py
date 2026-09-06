"""
app/ai/cloning_detector.py — Custom voice cloning detection model.

Architecture
------------
1.  Feature vector (84 dims) from feature_extractor.py
    [0-12]  MFCC means
    [13-25] MFCC temporal variance (AI KEY: very low variance)
    [26-38] MFCC delta
    [39-51] MFCC delta2
    [52-58] Spectral (centroid, rolloff, BW, flux, contrast, entropy, flatness)
    [59-60] ZCR, RMS
    [61-68] Pitch (F0 mean/std/range, voiced_ratio, jitter, shimmer, HNR, F0_velocity)
    [69-78] Chroma
    [79-83] Voice quality (RMS_var, ZCR_var, rolloff_var, energy_entropy, MFCC1_var)
2.  StandardScaler normalization
3.  VotingClassifier ensemble (RandomForest + GradientBoosting + MLP)

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

        # Step 2: Calculate heuristic score for zero-day AI models
        heuristic_result = self._heuristic_predict(features)

        # Step 3: Combine with ML model if loaded
        if not self._loaded:
            return heuristic_result

        try:
            features_scaled = self._scaler.transform(features_2d)
            proba = self._model.predict_proba(features_scaled)[0]
            ml_proba = float(proba[1])  # class 1 = AI clone

            # ════════════════════════════════════════════════════════
            # 3-LEVEL DETECTION ARCHITECTURE
            # ════════════════════════════════════════════════════════
            #
            # LEVEL 1 — Physics Inviolable (ABSOLUTE)
            #   Some signals are physically impossible for human voice.
            #   No TTS engine can fake them. If triggered → 100% AI.
            #
            # LEVEL 2 — Strong Heuristics (HIGH CONFIDENCE)
            #   Acoustic forensics: jitter, shimmer, pitch std.
            #   If triggered → override ML (heuristic is more reliable).
            #
            # LEVEL 3 — ML Ensemble (GENERAL CATCH-ALL)
            #   For advanced AI voices that partially mimic humans.
            # ════════════════════════════════════════════════════════

            # New feature layout (84 dims):
            # [0-12]  MFCC means
            # [13-25] MFCC temporal variance
            # [26-38] MFCC delta
            # [39-51] MFCC delta2
            # [52-58] spectral (centroid, rolloff, bw, flux, contrast, entropy, flatness)
            # [59-60] ZCR, RMS
            # [61-68] pitch (f0_mean, f0_std, f0_range, voiced_ratio, jitter, shimmer, hnr, f0_vel)
            # [69-78] chroma
            # [79-83] voice quality (rms_var, zcr_var, rolloff_var, energy_entropy, mfcc1_var)

            jitter       = features[65]   # was [50]
            shimmer      = features[66]   # was [51]
            pitch_mean   = features[61]   # was [46]
            pitch_std    = features[62]   # was [47]
            voiced_ratio = features[64]   # was [49]
            hnr_approx   = features[67]   # NEW
            f0_velocity  = features[68]   # NEW
            mfcc_var_mean = features[13:26].mean()   # NEW: MFCC temporal variance

            # ── LEVEL 1: Physics Inviolable ──────────────────────────────
            # No human larynx can produce perfectly periodic vocal folds.
            level1_triggered = (
                jitter < 0.0005              # essentially zero jitter
                and voiced_ratio > 0.3       # there IS actual speech
                and pitch_mean > 60          # there IS a pitch
            )
            if level1_triggered:
                logger.warning(
                    "[DETECTOR] LEVEL 1 PHYSICS - Zero jitter=%.5f", jitter
                )
                return DetectionResult(
                    is_clone=True, confidence=0.99, risk_level="high",
                    features_extracted=True,
                    top_indicators=[
                        f"ZERO JITTER ({jitter:.5f}) - synthesized voice signature",
                        f"Voiced speech confirmed (ratio={voiced_ratio:.2f}, F0={pitch_mean:.0f}Hz)",
                    ],
                    raw_scores={"ml_prob": ml_proba, "level": 1},
                )

            # ── LEVEL 2: MFCC Variance check (NEW) ───────────────────────
            # AI voices have extremely consistent MFCCs across time.
            # Human voices have natural temporal variance in all MFCC bands.
            if mfcc_var_mean < 0.5 and voiced_ratio > 0.3:
                logger.warning(
                    "[DETECTOR] LEVEL 2 LOW-MFCC-VAR - mean_var=%.4f", mfcc_var_mean
                )
                # Boost ML score significantly
                ml_proba = min(1.0, ml_proba * 1.4 + 0.15)


            # ── LEVEL 2: Strong Heuristics ───────────────────────────
            # When heuristic score is high (>= 0.55), it means multiple
            # strong AI signatures are present. Trust it over ML.
            h_score = heuristic_result.confidence
            if h_score >= 0.55:
                final_proba = max(ml_proba, h_score) # Never lower ML if ML is higher
                indicators = heuristic_result.top_indicators
            elif h_score >= 0.30:
                # Moderate heuristic + ML blend
                final_proba = max(ml_proba, 0.6 * ml_proba + 0.4 * h_score)
                indicators = heuristic_result.top_indicators if h_score > ml_proba \
                    else self._get_top_indicators(features, ml_proba)
            else:
                # ── LEVEL 3: ML is primary ───────────────────────────
                final_proba = ml_proba # Trust ML entirely if heuristics find nothing
                indicators = self._get_top_indicators(features, ml_proba)

            # ── LEVEL 4: ElevenLabs-style Advanced AI Detection ──────────────
            # Modern premium TTS (ElevenLabs, PlayHT, etc.) adds synthetic
            # warmth/noise to evade detection. Key telltale: very high
            # spectral entropy COMBINED with unnaturally high HNR (no real
            # harmonic noise). Real humans can't have both simultaneously.
            spec_entropy_raw = features[57]   # [52-58] spectral features
            l4_has_speech = voiced_ratio > 0.1 and pitch_mean > 50
            if spec_entropy_raw > 3.5 and hnr_approx > 0.995 and l4_has_speech:
                logger.warning("[DETECTOR] LEVEL 4 ELEVENLABS-STYLE - entropy=%.2f, hnr=%.4f",
                               spec_entropy_raw, hnr_approx)
                final_proba = max(final_proba, 0.72)  # Floor at 72% for this pattern
                if not indicators or indicators == ["Normal voice characteristics detected"]:
                    indicators = ["⚠️ High-quality AI TTS detected (ElevenLabs/PlayHT pattern)"]

            # ── Clone threshold: 0.45 (not 0.50) ────────────────────────────
            # Using 0.45 because modern AI voices fool ML into 48-52% range.
            # False positive rate at 0.45 vs 0.50 is minimal on real voices.
            is_clone = final_proba >= 0.45
            risk = _confidence_to_risk(final_proba)

            result = DetectionResult(
                is_clone=is_clone,
                confidence=final_proba,
                risk_level=risk,
                features_extracted=True,
                top_indicators=indicators,
                raw_scores={
                    "ml_prob": ml_proba,
                    "heuristic_score": h_score,
                    "final_prob": final_proba,
                    "mfcc_var": float(mfcc_var_mean),
                    "jitter": float(jitter),
                    "hnr": float(hnr_approx),
                    "level": 2 if h_score >= 0.30 else 3,
                },
            )
            logger.info("[DETECTOR] %s (ML: %.2f, Heuristic: %.2f)",
                        result, ml_proba, h_score)
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

        # ── LEVEL 1 physics check (also done in predict() for combination logic)
        # Here we compute a raw heuristic score for blend weighting.

        jitter = features[65]
        shimmer = features[66]
        pitch_mean = features[61]
        pitch_std = features[62]
        voiced_ratio = features[64]
        has_speech = voiced_ratio > 0.25 and pitch_mean > 60

        # Check 1: Jitter — the #1 universal AI signature
        # AI: near-zero jitter (synthesized pitch = too perfect)
        # Human: always > 0.003 due to laryngeal muscle noise
        if jitter < 0.0005 and has_speech:
            score += 0.60  # near-certain AI — catches ALL TTS engines
            indicators.append(f"⚡ Zero pitch jitter ({jitter:.5f}) — AI physics signature")
        elif jitter < 0.003 and has_speech:
            score += 0.35
            indicators.append(f"Very low pitch jitter ({jitter:.4f}) — likely AI")
        elif jitter < 0.008 and has_speech:
            score += 0.15
            indicators.append(f"Low pitch jitter ({jitter:.4f}) — possible AI")

        # Check 2: Shimmer — AI amplitude is machine-perfect
        # Human breathing + vocal fold tension causes 2-5% shimmer naturally
        if shimmer < 0.003 and has_speech:
            score += 0.25
            indicators.append(f"Zero shimmer ({shimmer:.4f}) — machine-perfect amplitude")
        elif shimmer < 0.01 and has_speech:
            score += 0.10
            indicators.append(f"Very low shimmer ({shimmer:.4f}) — unnatural")

        # Check 3: Pitch monotony — AI voices follow mathematical F0 curves
        # Human pitch varies naturally by 15-40 Hz across a sentence
        if pitch_std < 2.0 and has_speech:
            score += 0.15
            indicators.append(f"Monotone pitch (std={pitch_std:.1f} Hz) — AI prosody")

        # Check 4: Spectral flux (now at index 55)
        flux = features[55]
        if flux < 0.0005:
            score += 0.10
            indicators.append(f"Unnaturally smooth spectrum (flux={flux:.6f})")

        # Check 5: Spectral entropy (index 57)
        # AI voices often have unnaturally high spectral entropy (added synthetic noise)
        spec_entropy = features[57]
        if spec_entropy > 3.5 and has_speech:
            score += 0.20
            indicators.append(f"High spectral entropy ({spec_entropy:.2f}) — AI characteristic")

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

        pitch_std = features[62]
        jitter = features[65]
        flux = features[55]
        shimmer = features[66]

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
    names = [f"mfcc_mean_{i}" for i in range(13)]
    names += [f"mfcc_var_{i}" for i in range(13)]
    names += [f"mfcc_delta_{i}" for i in range(13)]
    names += [f"mfcc_delta2_{i}" for i in range(13)]
    names += ["spectral_centroid", "spectral_rolloff", "spectral_bandwidth",
               "spectral_flux", "spectral_contrast", "spectral_entropy", "spectral_flatness"]
    names += ["zcr", "rms"]
    names += ["f0_mean", "f0_std", "f0_range", "voiced_ratio",
              "jitter", "shimmer", "hnr_approx", "f0_velocity"]
    names += [f"chroma_{i}" for i in range(10)]
    names += ["rms_var", "zcr_var", "rolloff_var", "energy_entropy", "mfcc1_var"]
    return names
