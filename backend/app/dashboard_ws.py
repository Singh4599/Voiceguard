"""
dashboard_ws.py — Dashboard WebSocket broadcaster.

Maintains a set of connected frontend clients and broadcasts
real-time detection events to all of them.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Set

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

# Global set of connected dashboard clients
_clients: Set[WebSocket] = set()


async def handle_dashboard_websocket(websocket: WebSocket) -> None:
    """Accept and maintain a frontend dashboard connection."""
    await websocket.accept()
    _clients.add(websocket)
    logger.info("[DASHBOARD] Client connected. Total: %d", len(_clients))
    try:
        # Keep alive — frontend sends pings, we echo pong
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_text(json.dumps({"type": "keepalive"}))
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("[DASHBOARD] Client error: %s", exc)
    finally:
        _clients.discard(websocket)
        logger.info("[DASHBOARD] Client disconnected. Total: %d", len(_clients))


async def broadcast(msg: dict) -> None:
    """Broadcast a JSON message to all connected dashboard clients."""
    global _clients
    if not _clients:
        return
    payload = json.dumps(msg)
    dead: Set[WebSocket] = set()
    for ws in list(_clients):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    for d in dead:
        _clients.discard(d)


async def broadcast_chunk(
    call_id: str,
    chunk: int,
    is_clone: bool,
    confidence: float,
    risk: str,
    indicators: list[str],
    timestamp: str,
) -> None:
    """Convenience wrapper — broadcast a chunk detection result."""
    await broadcast({
        "type": "chunk",
        "data": {
            "call_id": call_id,
            "chunk": chunk,
            "is_clone": is_clone,
            "confidence": confidence,
            "risk": risk,
            "indicators": indicators,
            "timestamp": timestamp,
        },
    })


async def broadcast_call_end(call_id: str) -> None:
    """Notify dashboard that a call has ended."""
    await broadcast({"type": "call_end", "call_id": call_id})
