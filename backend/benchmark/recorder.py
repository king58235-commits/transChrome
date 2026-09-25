"""Temporary standalone recorder for Stage 2A model benchmarking.

Not part of the production pipeline — run this INSTEAD of main.py to capture
a fixed test clip to a WAV file, using the same extension/WebSocket protocol
(binary PCM16 chunks + {"type":"start"/"stop"} control messages) so the
existing Chrome extension can point at it unmodified.

Usage:
    venv\\Scripts\\python.exe benchmark\\recorder.py [output.wav]

Then load the extension, click "開始字幕" on the test video, let it run for
the desired duration, click "停止字幕", and Ctrl+C this script.
"""
import asyncio
import sys
import wave

import websockets

sys.path.insert(0, ".")
from config import HOST, PORT, SAMPLE_RATE, CHANNELS, SAMPLE_WIDTH_BYTES

OUTPUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "benchmark/test_clip.wav"


async def handler(websocket):
    print(f"Connected: {websocket.remote_address}")
    wav = wave.open(OUTPUT_PATH, "wb")
    wav.setnchannels(CHANNELS)
    wav.setsampwidth(SAMPLE_WIDTH_BYTES)
    wav.setframerate(SAMPLE_RATE)
    total_bytes = 0

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                wav.writeframes(message)
                total_bytes += len(message)
                secs = total_bytes / (SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH_BYTES)
                print(f"\rRecorded: {secs:.1f}s", end="", flush=True)
    except websockets.ConnectionClosed:
        pass
    finally:
        wav.close()
        print(f"\nSaved to {OUTPUT_PATH}")


async def main():
    print(f"Recorder listening on ws://{HOST}:{PORT}, writing to {OUTPUT_PATH}")
    print("Point the extension at this (it already does, same host/port as main.py).")
    async with websockets.serve(handler, HOST, PORT, max_size=None):
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
