# VoiceGuard — Backend README

## Phase 1: Real-Time Telephony Audio Ingestion

This backend receives a live phone call via **Exotel AgentStream** (WebSocket),
decodes the audio, buffers it, emits 2-second chunks ready for Phase 2 AI
inference, and saves a full WAV recording when the call ends.

---

## Architecture

```
Real Phone Call
  → Exotel PSTN
    → Exotel AgentStream WebSocket
      → /ws/exotel  (FastAPI)
        → parser.py       (JSON events → typed structs)
        → decoder.py      (base64 + μ-law → linear PCM)
        → buffer.py       (PCM → 2-second chunks + complete buffer)
        → wav_writer.py   (linear PCM → playable WAV files)
        → manager.py      (CallSession per active call)
```

---

## Setup (macOS)

```bash
# 1. Navigate to the backend directory
cd voiceguard/backend

# 2. Create a Python virtual environment
python3 -m venv venv

# 3. Activate the virtual environment
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. (Optional) Copy environment file and customise if needed
cp .env.example .env
```

---

## Run the backend

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Expected startup output:
```
INFO  voiceguard — ============================================================
INFO  voiceguard — VoiceGuard backend started
INFO  voiceguard —   Recordings : /path/to/backend/recordings
INFO  voiceguard —   Chunks     : /path/to/backend/chunks
INFO  voiceguard —   Chunk dur  : 2.0 s
INFO  voiceguard —   Log level  : INFO
INFO  voiceguard — ============================================================
INFO  uvicorn.error — Application startup complete.
```

---

## Health check

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "ok", "service": "voiceguard-backend"}
```

Or open in browser: **http://localhost:8000/health**

---

## Expose to the internet (Cloudflare Tunnel)

Exotel needs a public HTTPS/WSS URL.  The easiest way during development:

```bash
cloudflared tunnel --url http://localhost:8000
```

Cloudflare will print a URL such as:
```
https://random-words-1234.trycloudflare.com
```

---

## Configure Exotel

In the Exotel dashboard, set your Stream applet's WebSocket URL to:

```
wss://<generated-domain>/ws/exotel
```

For example:
```
wss://random-words-1234.trycloudflare.com/ws/exotel
```

---

## Test a real call

1. Start the backend (see above).
2. Start the Cloudflare tunnel.
3. Configure Exotel as described above.
4. Call your Exotel number.
5. Speak for 10–20 seconds.
6. Hang up.

### What you should see in the terminal

```
INFO  [EXOTEL] Connection accepted
INFO  [CALL START]
        Call ID    : CA1234abcd
        Stream ID  : ...
        Sample Rate: 8000 Hz
        Encoding   : pcmu
        Channels   : 1
INFO  [AUDIO] call=CA1234abcd  packets=50  bytes_received=32000  buffered=2.0 s
INFO  [CHUNK READY] call=CA1234abcd  chunk=1  duration=2.00 s  → call_CA1234abcd_chunk_0001.wav
INFO  [AUDIO] call=CA1234abcd  packets=100  bytes_received=64000  buffered=4.0 s
INFO  [CHUNK READY] call=CA1234abcd  chunk=2  duration=2.00 s  → call_CA1234abcd_chunk_0002.wav
...
INFO  [CALL STOP]
        Call ID   : CA1234abcd
        Duration  : 12.4 s
        Packets   : 620
        Chunks    : 6
        Recording : recordings/call_CA1234abcd_20240901_143022.wav
```

### Where to find the files

| What | Location |
|------|----------|
| Full call recording | `backend/recordings/call_<id>_<timestamp>.wav` |
| 2-second chunks | `backend/chunks/call_<id>_chunk_<NNNN>.wav` |

### Play on macOS

```bash
# Play the full recording
afplay recordings/call_CA1234abcd_20240901_143022.wav

# Play a specific chunk
afplay chunks/call_CA1234abcd_chunk_0001.wav

# Or open with QuickTime Player
open recordings/call_CA1234abcd_20240901_143022.wav
```

---

## Local audio pipeline test (no Exotel needed)

Verify WAV generation, chunking, and decoding locally:

```bash
python test_audio.py
```

All generated test WAV files are saved to `backend/test_output/`.

```bash
# Listen to the 440 Hz sine wave test file
afplay test_output/test_sine_440hz.wav
```

---

## File structure

```
backend/
├── app/
│   ├── main.py            ← FastAPI app, /health, /ws/exotel
│   ├── config.py          ← All configuration + env-var overrides
│   ├── exotel/
│   │   ├── parser.py      ← JSON → typed event dataclasses
│   │   └── websocket.py   ← WebSocket handler (glue layer)
│   ├── audio/
│   │   ├── decoder.py     ← base64 + codec → linear PCM
│   │   ├── buffer.py      ← dual buffer: complete + 2-second chunks
│   │   └── wav_writer.py  ← linear PCM → WAV (wave module)
│   └── sessions/
│       └── manager.py     ← CallSession + SessionManager
├── recordings/            ← Full call WAV files (auto-created)
├── chunks/                ← 2-second chunk WAV files (auto-created)
├── test_audio.py          ← Local pipeline test (no Exotel)
├── requirements.txt
├── .env.example
└── README.md
```

---

## Phase 2 hook

Every completed 2-second chunk triggers `AudioBuffer.on_audio_chunk()` in
`audio/buffer.py`.  This is currently a no-op stub.  In Phase 2, replace
the stub body with a call to the AI deepfake voice detector:

```python
# Phase 2: Send this chunk to the AI voice deepfake detector.
async def on_audio_chunk(self, call_id, chunk_number, wav_bytes):
    result = await ai_detector.analyze(wav_bytes)
    if result.is_synthetic:
        await alert_operator(call_id, chunk_number, result.confidence)
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `VOICEGUARD_HOST` | `0.0.0.0` | Bind address |
| `VOICEGUARD_PORT` | `8000` | Bind port |
| `CHUNK_DURATION_SECONDS` | `2.0` | Chunk size for AI inference |
| `DEFAULT_SAMPLE_RATE` | `8000` | Fallback if Exotel omits sample rate |
| `RECORDINGS_DIR` | `recordings/` | Full call WAV output |
| `CHUNKS_DIR` | `chunks/` | Chunk WAV output |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `AUDIO_LOG_EVERY_N_PACKETS` | `50` | Progress log throttle |
