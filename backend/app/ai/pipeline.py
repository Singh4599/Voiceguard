"""
app/ai/pipeline.py — Real-time AI voice cloning detection pipeline.

Called every 2 seconds when a new audio chunk arrives from a live call.

Flow:
    WAV chunk bytes
         ↓
    feature_extractor.extract_features()   ← 62-dim audio forensics vector
         ↓
    cloning_detector.predict()             ← ML model / heuristic
         ↓
    DetectionResult
         ↓
    Log + (Phase 3) → Dashboard WebSocket alert
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.ai.cloning_detector import DetectionResult, get_detector

logger = logging.getLogger(__name__)


async def analyze_chunk(
    call_id: str,
    chunk_number: int,
    wav_bytes: bytes,
) -> DetectionResult:
    """
    Analyze one 2-second audio chunk for voice cloning.

    Parameters
    ----------
    call_id      : Unique ID for this call.
    chunk_number : 1-based chunk index.
    wav_bytes    : Complete WAV file bytes (header + PCM).

    Returns
    -------
    DetectionResult with is_clone, confidence, risk_level, indicators.
    """
    detector = get_detector()
    result = detector.predict(wav_bytes)

    # ── Logging ──────────────────────────────────────────────────────────
    log_prefix = f"[AI] call={call_id[:8]}… chunk={chunk_number:03d}"

    if result.is_clone:
        logger.warning(
            "%s  🚨 AI CLONE DETECTED | confidence=%.0f%% | risk=%s",
            log_prefix,
            result.confidence * 100,
            result.risk_level.upper(),
        )
        for indicator in result.top_indicators:
            logger.warning("%s    → %s", log_prefix, indicator)
    else:
        logger.info(
            "%s  ✅ Real human voice  | confidence=%.0f%%",
            log_prefix,
            (1 - result.confidence) * 100,
        )

    # ── Phase 3 hook: broadcast to dashboard ─────────────────────────────
    # TODO: await dashboard_ws.broadcast(call_id, result)

    return result
