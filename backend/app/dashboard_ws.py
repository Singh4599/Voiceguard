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

# Heartbeat interval — send server ping every 20s to keep Railway/proxies alive
_HEARTBEAT_INTERVAL = 20


async def handle_dashboard_websocket(websocket: WebSocket) -> None:
    """Accept and maintain a frontend dashboard connection with keepalive."""
    await websocket.accept()
    global _clients
    _clients.add(websocket)
    logger.info("[DASHBOARD] Client connected. Total: %d", len(_clients))

    # Send heartbeat pings independently of incoming messages
    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
            try:
                await websocket.send_text(json.dumps({"type": "keepalive"}))
            except Exception:
                break  # connection gone — the receiver task will clean up

    heartbeat_task = asyncio.create_task(_heartbeat())

    try:
        # Drain incoming frames (frontend may send "ping") — also detects disconnects
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # 60s without any message from client is unusual — send one more ping
                try:
                    await websocket.send_text(json.dumps({"type": "keepalive"}))
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("[DASHBOARD] Client error: %s", exc)
    finally:
        heartbeat_task.cancel()
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
