"""
alerts.py — VoiceGuard Prevention Layer.

Sends SMS alerts via Exotel API when AI voice cloning is detected
with sufficient confidence across consecutive chunks.
"""
from __future__ import annotations

import logging
import httpx
from datetime import datetime, timezone

from app import config

logger = logging.getLogger(__name__)

# Track alert state per call — prevent duplicate SMS per call
_alerted_calls: set[str] = set()
# Per-call consecutive AI chunk counter
_consecutive_ai: dict[str, int] = {}


def record_chunk(call_id: str, is_clone: bool, confidence: float) -> bool:
    """
    Record chunk result. Returns True if SMS alert should be sent.
    Resets counter when a real-voice chunk is seen.
    """
    if call_id in _alerted_calls:
        return False  # already sent for this call

    if is_clone and confidence >= config.ALERT_CONFIDENCE_THRESHOLD:
        _consecutive_ai[call_id] = _consecutive_ai.get(call_id, 0) + 1
    else:
        _consecutive_ai[call_id] = 0

    return _consecutive_ai.get(call_id, 0) >= config.ALERT_CONSECUTIVE_CHUNKS


async def send_sms_alert(to_number: str, call_id: str) -> bool:
    """
    Send SMS warning to the call recipient via Exotel SMS API.
    Returns True on success.
    """
    if call_id in _alerted_calls:
        logger.info("[ALERT] Already sent for call %s — skipping", call_id[:8])
        return False

    if not all([config.EXOTEL_SID, config.EXOTEL_API_KEY, config.EXOTEL_API_TOKEN, config.EXOTEL_FROM_NUMBER]):
        logger.warning(
            "[ALERT] Exotel SMS creds not configured — skipping SMS. "
            "Set EXOTEL_SID, EXOTEL_API_KEY, EXOTEL_API_TOKEN, EXOTEL_FROM_NUMBER in .env"
        )
        # Still mark as alerted so dashboard shows prevention activated
        _alerted_calls.add(call_id)
        return False

    sms_body = (
        "⚠️ VoiceGuard Security Alert: "
        "Aapki abhi ki call mein AI voice cloning detect hua hai. "
        "Koi bhi personal ya financial information share na karein. "
        "Turant call drop karein. "
        "- VoiceGuard, SIH 2026"
    )

    url = (
        f"https://api.exotel.com/v1/Accounts/{config.EXOTEL_SID}"
        f"/Sms/send.json"
    )

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                url,
                auth=(config.EXOTEL_API_KEY, config.EXOTEL_API_TOKEN),
                data={
                    "From": config.EXOTEL_FROM_NUMBER,
                    "To": to_number,
                    "Body": sms_body,
                },
            )
        if resp.status_code in (200, 201):
            _alerted_calls.add(call_id)
            logger.warning(
                "[ALERT] 🚨 SMS SENT to %s for call %s | time=%s",
                to_number, call_id[:8],
                datetime.now(timezone.utc).strftime("%H:%M:%S"),
            )
            return True
        else:
            logger.error("[ALERT] SMS failed: %s %s", resp.status_code, resp.text[:200])
            return False

    except Exception as exc:
        logger.error("[ALERT] SMS error: %s", exc)
        return False


def is_call_alerted(call_id: str) -> bool:
    return call_id in _alerted_calls


def reset_call(call_id: str) -> None:
    """Clean up state when call ends."""
    _alerted_calls.discard(call_id)
    _consecutive_ai.pop(call_id, None)
