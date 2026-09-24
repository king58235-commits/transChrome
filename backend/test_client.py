"""Manual test client: sends synthetic PCM16 audio to the local server
to verify the WebSocket audio pipeline without needing the Chrome extension.
"""
import asyncio
import json
import struct

import websockets

from config import HOST, PORT, SAMPLE_RATE

CHUNK_MS = 250
SAMPLES_PER_CHUNK = SAMPLE_RATE * CHUNK_MS // 1000


def make_silence_chunk():
    return struct.pack("<%dh" % SAMPLES_PER_CHUNK, *([0] * SAMPLES_PER_CHUNK))


async def main():
    uri = f"ws://{HOST}:{PORT}"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"type": "start"}))
        chunk = make_silence_chunk()
        for _ in range(16):  # ~4 seconds of audio, enough to cross TRANSCRIBE_CHUNK_SECONDS
            await ws.send(chunk)
            await asyncio.sleep(CHUNK_MS / 1000)
        await ws.send(json.dumps({"type": "stop"}))


if __name__ == "__main__":
    asyncio.run(main())
