"""
simulate_exotel.py — Local Exotel WebSocket simulator for testing.

Simulates a real Exotel AgentStream call without needing an actual phone call.
Sends: connected → start → media (real sine wave audio) → stop

Usage (from backend/ directory, venv active):
    python simulate_exotel.py

The backend must be running on localhost:8000.
"""

import asyncio
import base64
import json
import math
import struct
import sys
import time

try:
    import websockets
except ImportError:
    print("Run: pip install websockets")
    sys.exit(1)

WS_URL = "ws://localhost:8000/ws/exotel"

CALL_ID    = f"TEST_CALL_{int(time.time())}"
STREAM_ID  = f"TEST_STREAM_{int(time.time())}"
ACCOUNT_ID = "test_account"
SAMPLE_RATE = 8000
DURATION_SECONDS = 10       # how long to stream audio
PACKET_MS = 20              # 20 ms packets (standard telephony)


# ---------------------------------------------------------------------------
# Generate raw μ-law audio bytes (simulates Exotel PCMU stream)
# ---------------------------------------------------------------------------

def linear_to_ulaw(sample: int) -> int:
    """Convert a 16-bit linear PCM sample to μ-law byte."""
    BIAS = 0x84
    CLIP = 32635
    sign = 0
    if sample < 0:
        sample = -sample
        sign = 0x80
    sample = min(sample, CLIP)
    sample += BIAS
    exp = 7
    for exp_lut in [0x4000, 0x2000, 0x1000, 0x800, 0x400, 0x200, 0x100]:
        if sample >= exp_lut:
            break
        exp -= 1
    mantissa = (sample >> (exp + 3)) & 0x0F
    ulaw_byte = ~(sign | (exp << 4) | mantissa) & 0xFF
    return ulaw_byte


def generate_ulaw_packet(
    packet_index: int,
    sample_rate: int = SAMPLE_RATE,
    packet_ms: int = PACKET_MS,
    frequency_hz: float = 440.0,
) -> bytes:
    """Generate one packet of μ-law audio (sine wave)."""
    num_samples = int(sample_rate * packet_ms / 1000)
    offset = packet_index * num_samples
    out = bytearray(num_samples)
    for i in range(num_samples):
        t = (offset + i) / sample_rate
        linear = int(0.4 * 32767 * math.sin(2 * math.pi * frequency_hz * t))
        out[i] = linear_to_ulaw(linear)
    return bytes(out)


# ---------------------------------------------------------------------------
# Exotel event builders
# ---------------------------------------------------------------------------

def make_connected() -> str:
    return json.dumps({"event": "connected", "protocol": "Call", "version": "1.0"})


def make_start() -> str:
    return json.dumps({
        "event": "start",
        "sequenceNumber": "1",
        "start": {
            "streamSid": STREAM_ID,
            "callSid":   CALL_ID,
            "accountSid": ACCOUNT_ID,
            "mediaFormat": {
                "encoding":   "pcmu",
                "sampleRate": SAMPLE_RATE,
                "channels":   1,
            },
        },
        "streamSid": STREAM_ID,
    })


def make_media(chunk_index: int, payload_b64: str) -> str:
    return json.dumps({
        "event": "media",
        "sequenceNumber": str(chunk_index + 2),
        "callSid": CALL_ID,
        "media": {
            "chunk":   str(chunk_index),
            "payload": payload_b64,
            "callSid": CALL_ID,
        },
        "streamSid": STREAM_ID,
    })


def make_stop() -> str:
    return json.dumps({
        "event": "stop",
        "sequenceNumber": "9999",
        "stop": {
            "streamSid": STREAM_ID,
            "callSid":   CALL_ID,
        },
        "streamSid": STREAM_ID,
    })


# ---------------------------------------------------------------------------
# Main simulator
# ---------------------------------------------------------------------------

async def simulate() -> None:
    total_packets = int(DURATION_SECONDS * 1000 / PACKET_MS)
    packet_interval = PACKET_MS / 1000.0   # seconds between packets

    print("=" * 55)
    print("  VoiceGuard — Exotel WebSocket Simulator")
    print("=" * 55)
    print(f"  Target  : {WS_URL}")
    print(f"  Call ID : {CALL_ID}")
    print(f"  Audio   : {DURATION_SECONDS}s @ {SAMPLE_RATE} Hz μ-law 440 Hz sine")
    print(f"  Packets : {total_packets} × {PACKET_MS} ms")
    print("=" * 55)

    try:
        async with websockets.connect(WS_URL) as ws:
            print("\n[SIM] WebSocket connected to backend\n")

            # 1. connected
            await ws.send(make_connected())
            print("[SIM] → sent: connected")
            await asyncio.sleep(0.1)

            # 2. start
            await ws.send(make_start())
            print(f"[SIM] → sent: start  (call_id={CALL_ID})\n")
            await asyncio.sleep(0.2)

            # 3. media packets
            print(f"[SIM] Streaming {DURATION_SECONDS}s of audio...")
            for i in range(total_packets):
                ulaw_bytes  = generate_ulaw_packet(i)
                payload_b64 = base64.b64encode(ulaw_bytes).decode()
                await ws.send(make_media(i, payload_b64))

                if (i + 1) % 50 == 0:
                    elapsed = (i + 1) * packet_interval
                    print(f"[SIM] → sent {i+1} packets  ({elapsed:.1f}s)")

                await asyncio.sleep(packet_interval)

            print(f"\n[SIM] Done streaming {total_packets} packets.")
            await asyncio.sleep(0.2)

            # 4. stop
            await ws.send(make_stop())
            print(f"[SIM] → sent: stop")
            await asyncio.sleep(1.0)   # let backend finalize

    except ConnectionRefusedError:
        print("\n[ERROR] Cannot connect to backend.")
        print("  Make sure uvicorn is running:")
        print("  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")
        sys.exit(1)
    except Exception as exc:
        print(f"\n[ERROR] {exc}")
        sys.exit(1)

    print("\n" + "=" * 55)
    print("  Simulation complete!")
    print("  Check backend/recordings/ for the WAV file")
    print("  Check backend/chunks/ for 2-second chunk files")
    print("  Play: afplay recordings/<filename>.wav")
    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(simulate())
