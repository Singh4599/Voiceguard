"""
test_ai_voice.py — Simulate an AI-cloned voice call to test detection.

Reads AI-generated WAV files from training_data/fake/ and sends them
through the WebSocket exactly like Exotel would, to verify the detector
flags them as AI clones.

Run:
    cd backend
    python test_ai_voice.py
"""

import asyncio
import audioop
import base64
import json
import random
import wave
from pathlib import Path

import websockets

WS_URL = "ws://localhost:8000/ws/exotel"
FAKE_DIR = Path(__file__).parent / "training_data" / "fake"
CHUNK_MS = 20   # 20ms per packet (same as Exotel)


async def simulate_ai_voice_call():
    # Pick a random AI-generated audio file
    fake_files = list(FAKE_DIR.glob("*.wav"))
    if not fake_files:
        print("❌ No fake audio found in training_data/fake/")
        print("   Run: python -m app.ai.training.generate_data")
        return

    fake_wav = random.choice(fake_files)
    print(f"\n🤖 Simulating AI CLONE voice call using: {fake_wav.name}")
    print(f"🌐 Connecting to {WS_URL} ...\n")

    try:
        async with websockets.connect(WS_URL) as ws:
            call_sid = "AI_CLONE_TEST_" + "".join(
                random.choices("abcdef0123456789", k=16)
            )

            # ── connected event ───────────────────────────────────────
            await ws.send(json.dumps({"event": "connected", "protocol": "Call",
                                      "version": "1.0.0"}))

            # ── start event ───────────────────────────────────────────
            await ws.send(json.dumps({
                "event": "start",
                "stream_sid": call_sid,
                "start": {
                    "call_sid": call_sid,
                    "account_sid": "test_account",
                    "mediaFormat": {
                        "encoding": "base64",
                        "sampleRate": 8000,
                        "channels": 1,
                    },
                },
            }))
            print(f"📞 [CALL START] call_sid={call_sid[:20]}...")
            print("🤖 Sending AI-generated audio — watch for CLONE DETECTED...\n")

            # ── Read WAV and send as μ-law packets ────────────────────
            with wave.open(str(fake_wav), "rb") as wf:
                sr = wf.getframerate()
                sw = wf.getsampwidth()
                frames = wf.readframes(wf.getnframes())

            # Resample to 8000 Hz if needed (simple repeat/skip)
            if sr != 8000 and sr == 16000:
                # Downsample 16kHz → 8kHz by taking every other sample
                import struct
                samples = struct.unpack(f"<{len(frames)//2}h", frames)
                samples_8k = samples[::2]
                frames = struct.pack(f"<{len(samples_8k)}h", *samples_8k)

            # Convert PCM16 → μ-law
            ulaw_bytes = audioop.lin2ulaw(frames, 2)

            # Send in 20ms chunks (160 bytes each @ 8kHz)
            chunk_size = 160
            total_chunks = len(ulaw_bytes) // chunk_size
            print(f"   Sending {total_chunks} packets ({total_chunks * 20}ms audio)...")

            for i in range(total_chunks):
                chunk = ulaw_bytes[i * chunk_size:(i + 1) * chunk_size]
                payload = base64.b64encode(chunk).decode("utf-8")

                await ws.send(json.dumps({
                    "event": "media",
                    "stream_sid": call_sid,
                    "media": {
                        "track": "inbound",
                        "chunk": str(i + 1),
                        "payload": payload,
                    },
                }))

                # 20ms between packets (real-time simulation)
                await asyncio.sleep(0.020)

            # ── stop event ────────────────────────────────────────────
            await ws.send(json.dumps({
                "event": "stop",
                "stream_sid": call_sid,
                "stop": {
                    "call_sid": call_sid,
                    "account_sid": "test_account",
                },
            }))

            print(f"\n📵 [CALL STOP] sent — check uvicorn logs above!")
            print("   Should see: 🔴 AI CLONE DETECTED | risk=HIGH/CRITICAL")
            await asyncio.sleep(1)

    except ConnectionRefusedError:
        print("❌ Could not connect — is uvicorn running on port 8000?")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(simulate_ai_voice_call())
