# VoiceGuard

**AI-Powered Real-Time Voice Cloning / Synthetic Speech Detection for Live Phone Calls**

> Smart India Hackathon Project

---

## Overview

VoiceGuard protects people from voice-cloning fraud on live phone calls.
It intercepts audio via Exotel AgentStream, runs real-time AI inference
on 2-second audio chunks, and flags synthetic / deepfake voices before
harm is done.

---

## Phases

| Phase | Status | Description |
|-------|--------|-------------|
| **1** | ✅ Complete | Real-time telephony audio ingestion (Exotel → PCM → WAV chunks) |
| 2 | Planned | AI deepfake voice detection on live chunks |
| 3 | Planned | Operator alerts, dashboard, call recording UI |

---

## Quick Start (Phase 1)

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Full instructions: [backend/README.md](backend/README.md)

---

## Architecture (Phase 1)

```
Real Phone Call → Exotel → WebSocket → VoiceGuard Backend
                                              │
                              ┌───────────────┼───────────────┐
                              │               │               │
                         Decode Audio    Buffer PCM    Write WAV chunks
                         (μ-law→PCM)   (per call)    (every 2 seconds)
                                                            │
                                                    [Phase 2 hook]
                                                    AI Deepfake Detector
```
