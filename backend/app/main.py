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

from fastapi import FastAPI, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app.exotel.websocket import handle_exotel_websocket
from app.dashboard_ws import handle_dashboard_websocket
import app.reports_db as reports_db

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

# Allow Next.js dev server to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount recordings directory for playback
config.RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/recordings", StaticFiles(directory=config.RECORDINGS_DIR), name="recordings")

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


@app.get("/api/reports", tags=["Reports"])
async def get_reports() -> JSONResponse:
    """Return all saved call reports."""
    reports = reports_db.get_all_reports()
    return JSONResponse(content={"reports": reports}, status_code=200)


@app.post("/api/analyze", tags=["Analysis"])
async def analyze_audio(file: UploadFile) -> JSONResponse:
    """
    Upload an audio file (WAV/MP3) and run voice clone detection on it.
    Returns: is_clone, confidence, risk_level, indicators.
    """
    import io
    import numpy as np
    import librosa
    import soundfile as sf

    try:
        contents = await file.read()
        filename = (file.filename or "upload").lower()

        if filename.endswith(".wav"):
            wav_bytes = contents
        else:
            # Decode MP3/OGG/M4A via librosa
            audio_buf = io.BytesIO(contents)
            y, sr = librosa.load(audio_buf, sr=16000, mono=True)
            out_buf = io.BytesIO()
            sf.write(out_buf, y.astype(np.float32), sr, format="WAV", subtype="PCM_16")
            wav_bytes = out_buf.getvalue()

        from app.ai.cloning_detector import get_detector
        detector = get_detector()

        if not detector.is_ready():
            return JSONResponse(
                content={"error": "Model not loaded. Run training/train.py first."},
                status_code=503,
            )

        result = detector.predict(wav_bytes)

        return JSONResponse(content={
            "is_clone": result.is_clone,
            "confidence": round(result.confidence * 100, 1),
            "risk_level": result.risk_level,
            "indicators": result.top_indicators,
            "raw_scores": result.raw_scores,
            "label": "AI Voice Detected" if result.is_clone else "Real Human Voice",
        }, status_code=200)

    except Exception as exc:
        logger.error("[ANALYZE] Error: %s", exc)
        return JSONResponse(content={"error": str(exc)}, status_code=500)

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


@app.websocket("/ws/dashboard")
async def dashboard_stream(websocket: WebSocket) -> None:
    """
    Frontend dashboard WebSocket endpoint.
    Connect from Next.js: ws://localhost:8000/ws/dashboard
    """
    await handle_dashboard_websocket(websocket)
