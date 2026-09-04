# VoiceGuard — Phase 1 Complete, Phase 2 Handoff

## 🎯 Project Goal
**VoiceGuard** is an AI-powered real-time call fraud detection system built for SIH (Smart India Hackathon).

When someone calls a specific Exotel number:
1. The call audio streams live to our backend via WebSocket
2. Audio is chunked every 2 seconds
3. Each chunk goes to an AI model for fraud/scam detection
4. Alert is raised if fraud detected

---

## ✅ What is Done (Phase 1)

### Architecture
```
Phone Call (caller)
     ↓
Exotel (cloud telephony)  —— WebSocket ——→  VoiceGuard Backend (FastAPI)
                                                      ↓
                                         Decode μ-law → PCM16
                                                      ↓
                                         2-second audio chunks (WAV)
                                                      ↓
                                         recordings/ + chunks/ saved
                                                      ↓
                                         [PHASE 2: AI analysis HERE]
```

### Tech Stack
- **Python 3.12** with `uv` package manager
- **FastAPI** + `uvicorn` — WebSocket server
- **Exotel** — Cloud telephony (Indian provider)
- **cloudflared** — Tunnel to expose localhost to Exotel

### Key Files
```
backend/
├── app/
│   ├── main.py                  ← FastAPI app entry point
│   ├── config.py                ← All config (ports, dirs, chunk duration)
│   ├── exotel/
│   │   ├── websocket.py         ← WebSocket handler (main logic)
│   │   └── parser.py            ← Parses Exotel JSON events
│   ├── audio/
│   │   ├── decoder.py           ← μ-law → PCM16 decode
│   │   ├── buffer.py            ← Buffers audio, emits 2s chunks
│   │   └── wav_writer.py        ← Writes WAV files
│   └── sessions/
│       └── manager.py           ← Tracks active calls
├── recordings/                  ← Full call WAV files saved here
├── chunks/                      ← 2-second chunk WAVs saved here
├── simulate_exotel.py           ← Test script (no real call needed)
└── requirements.txt
```

---

## 🔧 How to Run Locally

### 1. Start Backend
```bash
cd /Users/dhruvsingh/Desktop/Voiceguard/backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Start Cloudflare Tunnel
```bash
cloudflared tunnel --url http://localhost:8000
# Copy the https://xxxx.trycloudflare.com URL
```

### 3. Update Exotel Flow
- Go to my.exotel.com → Flows → Edit Flow
- Stream applet WebSocket URL: `wss://<tunnel-url>/ws/exotel`
- Save & Publish

### 4. Call the Exotel Number
- Number: **09513886363**
- PIN: **8447-8368-94** (trial account PIN)

### 5. Test Without Real Call (Simulator)
```bash
cd backend
python simulate_exotel.py
# Sends 10s of synthetic audio to ws://localhost:8000/ws/exotel
```

---

## 📡 Exotel WebSocket Protocol

Exotel sends these JSON events over WebSocket:

```json
// 1. Connected
{"event": "connected"}

// 2. Start (call begins)
{
  "event": "start",
  "stream_sid": "...",
  "start": {
    "call_sid": "...",
    "account_sid": "iitmjanakpuri1",
    "mediaFormat": {
      "encoding": "base64",   // NOTE: means μ-law PCMU audio
      "sampleRate": 8000,
      "channels": 1
    }
  }
}

// 3. Media (audio packets, ~50/sec)
{
  "event": "media",
  "stream_sid": "...",
  "media": {
    "chunk": "5",
    "payload": "<base64-encoded-mulaw-bytes>"
  }
}

// 4. Stop (call ends)
{
  "event": "stop",
  "stream_sid": "...",
  "stop": {
    "call_sid": "...",
    "account_sid": "iitmjanakpuri1"
  }
}
```

**Important gotcha:** Exotel sends `"encoding": "base64"` but it actually means the payload is base64-encoded **μ-law (G.711u / PCMU)** audio. This is handled in `decoder.py`.

---

## 🔌 Phase 2 Hook (Where AI Goes)

In `app/audio/buffer.py`, every time a 2-second chunk is ready, a callback fires:

```python
# This is called every 2 seconds with a fresh audio chunk
async def on_chunk_ready(chunk_path: Path, call_id: str, chunk_index: int):
    # chunk_path → Path to a 2-second WAV file
    # call_id    → Unique ID for this call
    # chunk_index → Which chunk this is (1, 2, 3, ...)
    
    # TODO: Send chunk_path to AI model here
    pass
```

The WAV files are:
- **Format:** PCM 16-bit, mono, 8000 Hz
- **Duration:** 2 seconds each (configurable in config.py: `CHUNK_DURATION_SECONDS`)
- **Size:** ~32 KB each

---

## 🤖 Phase 2 — What Needs to Be Built

### Option A: Whisper + LLM (Recommended)
```
chunk.wav → Whisper (Speech-to-Text) → text → Gemini/GPT (fraud analysis) → alert
```

### Option B: Audio-based classifier
```
chunk.wav → Audio embedding model → fraud classifier → alert
```

### Suggested Phase 2 Steps:
1. **Transcription:** Use `openai-whisper` or Google Speech-to-Text on each chunk
2. **Context window:** Keep last N transcribed chunks as rolling context
3. **Fraud detection prompt:** Send context to Gemini/GPT with prompt like:
   > "Analyze this phone call transcript. Is the caller attempting fraud, impersonation, or social engineering? Return JSON: {is_fraud: bool, confidence: float, reason: string}"
4. **Alert system:** If fraud detected → send webhook/SMS/dashboard alert

### Minimal Phase 2 Code Structure:
```python
# app/ai/analyzer.py
async def analyze_chunk(chunk_path: Path, call_id: str, transcript_history: list[str]) -> dict:
    # 1. Transcribe
    text = await transcribe(chunk_path)           # Whisper / Google STT
    
    # 2. Append to history
    transcript_history.append(text)
    context = " ".join(transcript_history[-5:])   # last 10 seconds of speech
    
    # 3. Analyze
    result = await detect_fraud(context)           # LLM call
    
    return result  # {is_fraud: bool, confidence: float, reason: str}
```

---

## ⚠️ Known Issues / Gotchas

1. **Exotel Trial Account:** Requires PIN on every call. Media streams only work with a "Greeting" or IVR applet in the flow's "Next" field to keep the call alive.

2. **Cloudflare URL changes on restart:** Every time `cloudflared` restarts, a new URL is generated. Must update Exotel flow each time. For production, use a named tunnel or a permanent URL.

3. **Media events have no call_sid:** Exotel's media events don't include `call_sid`. We use `session_manager.active_call_ids()` fallback. See `app/exotel/websocket.py` line ~172.

4. **Encoding "base64":** Exotel's `mediaFormat.encoding` is `"base64"` (transport encoding), not the audio codec. Actual codec is μ-law/PCMU. Fixed in `decoder.py`.

---

## 📦 Dependencies

```
fastapi
uvicorn[standard]
python-dotenv
websockets          ← for simulate_exotel.py
```

Install:
```bash
cd backend
pip install -r requirements.txt
# or with uv:
uv pip install -r requirements.txt
```

---

## 📁 Output Files

After a real call:
```
backend/recordings/call_<call_id>_<timestamp>.wav   ← Full call recording
backend/chunks/call_<call_id>_chunk_0001.wav        ← 2s chunk 1
backend/chunks/call_<call_id>_chunk_0002.wav        ← 2s chunk 2
...
```

Play recordings:
```bash
afplay recordings/call_<id>.wav          # macOS
aplay  recordings/call_<id>.wav          # Linux
```
