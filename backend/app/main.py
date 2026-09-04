"""
main.py — VoiceGuard Phase 1 FastAPI application entry point.

Registers:
  GET  /health    — liveness probe
  WS   /ws/exotel — Exotel AgentStream WebSocket endpoint

Logging is configured here so every module inherits the same format.
"""

from __future__ import annotations

import logging
import sys

from fastapi import FastAPI, WebSocket
from fastapi.responses import JSONResponse

from app import config
from app.exotel.websocket import handle_exotel_websocket

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(levelname)-5s  %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("voiceguard")

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="VoiceGuard",
    description=(
        "Phase 1 — Real-time telephony audio ingestion layer.\n\n"
        "Accepts Exotel AgentStream WebSocket connections, decodes audio, "
        "buffers it, emits 2-second chunks for AI inference (Phase 2), "
        "and saves full call recordings as WAV files."
    ),
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Startup / shutdown events
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def on_startup() -> None:
    logger.info("=" * 60)
    logger.info("VoiceGuard backend started")
    logger.info("  Recordings : %s", config.RECORDINGS_DIR)
    logger.info("  Chunks     : %s", config.CHUNKS_DIR)
    logger.info("  Chunk dur  : %.1f s", config.CHUNK_DURATION_SECONDS)
    logger.info("  Log level  : %s", config.LOG_LEVEL)
    logger.info("=" * 60)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    logger.info("VoiceGuard backend shutting down")


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------

@app.get("/", tags=["Health"])
async def root(response: JSONResponse = None) -> JSONResponse:
    """
    Root endpoint — Exotel sends an HTTP GET here before upgrading to WebSocket.
    Must return 200 or Exotel will not proceed with the stream.

    Exotel passes call metadata as query params:
    ?CallSid=...&CallFrom=...&CallTo=...&Direction=...
    """
    return JSONResponse(
        content={"status": "ok", "service": "voiceguard", "ready": True},
        status_code=200,
    )


@app.get("/health", tags=["Health"])
async def health_check() -> JSONResponse:
    """
    Liveness probe.

    Returns
    -------
    JSON: { "status": "ok", "service": "voiceguard-backend" }
    """
    return JSONResponse(
        content={"status": "ok", "service": "voiceguard-backend"},
        status_code=200,
    )


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/exotel")
async def exotel_stream(websocket: WebSocket) -> None:
    """
    Exotel AgentStream WebSocket endpoint.

    Configure this URL in the Exotel Stream applet:
        wss://<your-domain>/ws/exotel
    """
    await handle_exotel_websocket(websocket)
