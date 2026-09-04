"""
app/ai/pipeline.py — Real-time AI voice cloning detection pipeline.

Called every 2 seconds when a new audio chunk arrives from a live call.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import List

from app.ai.cloning_detector import DetectionResult, get_detector

logger = logging.getLogger(__name__)

# Store rolling confidence history per call
_call_history: dict[str, List[float]] = defaultdict(list)


async def analyze_chunk(
    call_id: str,
    chunk_number: int,
    wav_bytes: bytes,
) -> DetectionResult:
    """
    Analyze one 2-second audio chunk for voice cloning.

    Smoothing strategy:
    - Level 1 physics triggers (confidence >= 0.90): BYPASS smoothing → instant alert
    - All other results: exponential weighted average (recent chunks weighted more)
    """
    detector = get_detector()
    result = detector.predict(wav_bytes)

    log_prefix = f"[AI] call={call_id[:8]}… chunk={chunk_number:03d}"

    # ── INSTANT ALERT for physics-level detections (Level 1) ───────
    # These are hard physical impossibilities (e.g. zero jitter) — no smoothing needed.
    # Rolling window would suppress them (e.g. 49 real + 1 AI → avg = 0.42 = missed!)
    if result.confidence >= 0.90 and result.features_extracted:
        # Still add to history so future chunks know there was an AI hit
        _call_history[call_id].append(result.confidence)
        logger.warning(
            "%s  🚨 AI CLONE DETECTED | confidence=%.0f%% | risk=%s",
            log_prefix, result.confidence * 100, result.risk_level.upper(),
        )
        for indicator in result.top_indicators:
            logger.warning("%s    → %s", log_prefix, indicator)
        return result

    # ── Smoothing for non-physics detections (Level 2 / 3) ───────────────
    history = _call_history[call_id]
    if result.features_extracted:
        history.append(result.confidence)
        # Keep last 3 chunks (6-second window)
        if len(history) > 3:
            history.pop(0)

    if history:
        # Exponential weighted average: newest chunk counts 2x, older chunks 1x each
        n = len(history)
        weights = [1.0] * n
        weights[-1] = 2.0   # latest chunk gets double weight
        smoothed = sum(h * w for h, w in zip(history, weights)) / sum(weights)
    else:
        smoothed = result.confidence

    result.confidence = smoothed
    result.is_clone = smoothed >= 0.5

    if smoothed < 0.35:
        result.risk_level = "low"
    elif smoothed < 0.60:
        result.risk_level = "medium"
    else:
        result.risk_level = "high"

    if result.is_clone:
        logger.warning(
            "%s  🚨 AI CLONE DETECTED | confidence=%.0f%% | risk=%s",
            log_prefix, result.confidence * 100, result.risk_level.upper(),
        )
        for indicator in result.top_indicators:
            logger.warning("%s    → %s", log_prefix, indicator)
    else:
        logger.info(
            "%s  ✅ Real human voice  | confidence=%.0f%%",
            log_prefix, (1 - result.confidence) * 100,
        )

    # ── Phase 3 hook: broadcast to dashboard ─────────────────────────────
    # TODO: await dashboard_ws.broadcast(call_id, result)

    return result

