"""Replay a recorded session (SAVE_SESSION_AUDIO wav) through the real
backend pipeline, once per TRANSLATION_IDLE_FLUSH_S value, and write one log
per run for comparison with analyze_session_log.py.

Audio is streamed in 250ms chunks at real-time pace, exactly like the
extension does, because the pipeline's timing (partial refresh, pause
detection, idle flush) is wall-clock based. Each run therefore takes as long
as the recording. Models load once. Uses port 8766, so it doesn't clash with
a running backend, but GPU timing is only representative with the live
backend stopped.

Usage (from backend/):
    venv\\Scripts\\python.exe benchmark\\replay_session.py <wav> <idle_s> [<idle_s> ...]
Logs go to benchmark/replay_<wav name>_idle<value>.log (git-ignored: they
contain the stream's transcript).
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, ".")

import asyncio
import json
import logging
import os
import time
import wave

import websockets

import server
import transcriber
import translator

PORT = 8766
CHUNK_BYTES = 8000  # 250ms of 16kHz mono PCM16
TAIL_SECONDS = 4.0  # keep the connection open after the audio so the last unit flushes


async def stream(wav_path):
    wav = wave.open(wav_path, "rb")
    data = wav.readframes(wav.getnframes())
    async with websockets.connect(f"ws://127.0.0.1:{PORT}", max_size=None) as ws:
        # Read the partial/final/translation messages like the extension does;
        # left unread, the client's queue fills, it stops processing
        # keepalive pings, and the server drops the connection.
        async def drain():
            async for _ in ws:
                pass

        drainer = asyncio.create_task(drain())
        await ws.send(json.dumps({"type": "start"}))
        start = time.monotonic()
        for i in range(0, len(data), CHUNK_BYTES):
            target = start + (i // CHUNK_BYTES + 1) * 0.25
            await asyncio.sleep(max(0.0, target - time.monotonic()))
            await ws.send(data[i:i + CHUNK_BYTES])
        await asyncio.sleep(TAIL_SECONDS)
        await ws.send(json.dumps({"type": "stop"}))
        drainer.cancel()


async def main():
    wav_path, idles = sys.argv[1], [float(v) for v in sys.argv[2:]]
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    transcriber.load_model()
    translator.load_model()
    server.SAVE_SESSION_AUDIO = False  # never re-record the replay itself

    async with websockets.serve(server.handler, "127.0.0.1", PORT, max_size=None):
        for idle in idles:
            server.TRANSLATION_IDLE_FLUSH_S = idle
            name = os.path.splitext(os.path.basename(wav_path))[0]
            log_path = f"benchmark/replay_{name}_idle{idle}.log"
            handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
            logging.getLogger().addHandler(handler)
            print(f"=== replay idle={idle}s -> {log_path}", flush=True)
            await stream(wav_path)
            await asyncio.sleep(1.0)
            logging.getLogger().removeHandler(handler)
            handler.close()


if __name__ == "__main__":
    asyncio.run(main())
