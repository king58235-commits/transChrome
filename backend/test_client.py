"""Manual test client: sends audio to the local server to verify the WebSocket
pipeline without needing the Chrome extension.

    venv\\Scripts\\python.exe test_client.py              ~4s of silence (pipeline only)
    venv\\Scripts\\python.exe test_client.py <wav> [secs]  stream a 16kHz mono PCM16 wav
                                                        (e.g. a SAVE_SESSION_AUDIO recording)
                                                        in real time, printing every
                                                        final / translation the server sends
"""
import asyncio
import json
import struct
import sys
import wave

import websockets

from config import HOST, PORT, SAMPLE_RATE

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CHUNK_MS = 250
SAMPLES_PER_CHUNK = SAMPLE_RATE * CHUNK_MS // 1000
TAIL_SECONDS = 4.0  # keep listening after the audio so the last unit is translated


def make_silence_chunk():
    return struct.pack("<%dh" % SAMPLES_PER_CHUNK, *([0] * SAMPLES_PER_CHUNK))


def audio_chunks(wav_path, max_seconds):
    if wav_path is None:
        return [make_silence_chunk()] * 16  # ~4 seconds of audio
    wav = wave.open(wav_path, "rb")
    frames = wav.getnframes() if max_seconds is None else min(wav.getnframes(), int(max_seconds * SAMPLE_RATE))
    data = wav.readframes(frames)
    step = SAMPLES_PER_CHUNK * 2
    return [data[i:i + step] for i in range(0, len(data), step)]


async def main():
    wav_path = sys.argv[1] if len(sys.argv) > 1 else None
    max_seconds = float(sys.argv[2]) if len(sys.argv) > 2 else None
    uri = f"ws://{HOST}:{PORT}"
    async with websockets.connect(uri, max_size=None) as ws:
        async def receive():
            async for message in ws:
                data = json.loads(message)
                if data.get("type") == "final":
                    print(f"JA #{data['segment_id']}: {data['text']}", flush=True)
                elif data.get("type") == "translation":
                    print(f"   ZH #{data['unit_id']}: {data['text']}", flush=True)

        receiver = asyncio.create_task(receive())
        await ws.send(json.dumps({"type": "start"}))
        for chunk in audio_chunks(wav_path, max_seconds):
            await ws.send(chunk)
            await asyncio.sleep(CHUNK_MS / 1000)
        await asyncio.sleep(TAIL_SECONDS if wav_path else 0)
        await ws.send(json.dumps({"type": "stop"}))
        receiver.cancel()


if __name__ == "__main__":
    asyncio.run(main())
