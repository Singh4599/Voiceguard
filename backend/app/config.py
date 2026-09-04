"""
config.py — VoiceGuard Phase 1 central configuration.

All tuneable values live here.  Environment variables (via .env or shell)
override every default so the binary can be deployed without code changes.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Load .env if present (development convenience)
# python-dotenv is optional — if missing, env vars must be set in the shell.
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv  # type: ignore[import]
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; rely on shell environment variables

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
HOST: str = os.getenv("VOICEGUARD_HOST", "0.0.0.0")
PORT: int = int(os.getenv("VOICEGUARD_PORT", "8000"))

# ---------------------------------------------------------------------------
# Audio chunking
# ---------------------------------------------------------------------------
# Duration of each real-time chunk forwarded to the AI detector in Phase 2.
CHUNK_DURATION_SECONDS: float = float(os.getenv("CHUNK_DURATION_SECONDS", "2.0"))

# ---------------------------------------------------------------------------
# Audio defaults (overridden by Exotel start-event metadata at runtime)
# ---------------------------------------------------------------------------
DEFAULT_SAMPLE_RATE: int = int(os.getenv("DEFAULT_SAMPLE_RATE", "8000"))
DEFAULT_CHANNELS: int = int(os.getenv("DEFAULT_CHANNELS", "1"))

# Supported encoding identifiers (normalised to lowercase for comparison)
ENCODING_PCMU: str = "pcmu"          # μ-law 8-bit (very common in telephony)
ENCODING_PCM: str = "pcm"            # linear PCM / L16
ENCODING_LINEAR16: str = "linear16"  # alias used by some providers

# ---------------------------------------------------------------------------
# Filesystem
# ---------------------------------------------------------------------------
_BASE_DIR: Path = Path(__file__).resolve().parent.parent  # backend/

RECORDINGS_DIR: Path = Path(os.getenv("RECORDINGS_DIR", str(_BASE_DIR / "recordings")))
CHUNKS_DIR: Path = Path(os.getenv("CHUNKS_DIR", str(_BASE_DIR / "chunks")))

# Create directories on import so the rest of the code never has to worry.
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

# ---------------------------------------------------------------------------
# Media-packet log throttle
# ---------------------------------------------------------------------------
AUDIO_LOG_EVERY_N_PACKETS: int = int(os.getenv("AUDIO_LOG_EVERY_N_PACKETS", "50"))

# ---------------------------------------------------------------------------
# Exotel SMS Alert (Prevention Layer)
# ---------------------------------------------------------------------------
EXOTEL_SID: str      = os.getenv("EXOTEL_SID", "")
EXOTEL_API_KEY: str  = os.getenv("EXOTEL_API_KEY", "")
EXOTEL_API_TOKEN: str= os.getenv("EXOTEL_API_TOKEN", "")
EXOTEL_FROM_NUMBER: str = os.getenv("EXOTEL_FROM_NUMBER", "")  # e.g. 0XXXXXXXXXX

# Trigger SMS alert when AI confidence crosses this threshold for N consecutive chunks
ALERT_CONFIDENCE_THRESHOLD: float = float(os.getenv("ALERT_CONFIDENCE_THRESHOLD", "0.70"))
ALERT_CONSECUTIVE_CHUNKS: int = int(os.getenv("ALERT_CONSECUTIVE_CHUNKS", "3"))
