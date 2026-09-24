import asyncio
import json
import logging
import time

import websockets

import transcriber
from audio_buffer import AudioBuffer
from config import (
    HOST,
    MAX_CHUNK_SECONDS,
    MIN_CHUNK_SECONDS,
    PARTIAL_INTERVAL_SECONDS,
    PARTIAL_MIN_SECONDS,
    PORT,
    TRANSCRIBE_TIMEOUT_SECONDS,
)

logger = logging.getLogger("server")


async def handler(websocket):
    logger.info("WebSocket connected: %s", websocket.remote_address)
    buffer = AudioBuffer()
    loop = asyncio.get_running_loop()

    busy = False
    last_partial_text = ""
    last_partial_at = 0.0

    async def run_model(pcm_bytes, final):
        kind = "Final" if final else "Partial"
        started = time.monotonic()
        try:
            text = await asyncio.wait_for(
                loop.run_in_executor(None, transcriber.transcribe, pcm_bytes, final),
                timeout=TRANSCRIBE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            # The executor thread keeps running to completion in the background
            # (Python can't forcibly kill it), but we stop waiting on it so one
            # bad chunk can't block transcription for the rest of the session.
            logger.warning("%s transcription exceeded %.0fs, skipping", kind, TRANSCRIBE_TIMEOUT_SECONDS)
            return None
        except Exception:
            logger.exception("%s transcription failed", kind)
            return None
        logger.info("%s result: %r (took %.2fs)", kind, text, time.monotonic() - started)
        return text

    async def maybe_transcribe():
        nonlocal busy, last_partial_text, last_partial_at
        if busy:
            return
        duration = buffer.duration_seconds()
        if duration < PARTIAL_MIN_SECONDS:
            return

        # Finalize (commit + clear) at a natural pause so a segment lands close
        # to a whole sentence, or once it's grown long enough that waiting for
        # a pause would make latency unbounded.
        should_finalize = duration >= MAX_CHUNK_SECONDS
        if not should_finalize and duration >= MIN_CHUNK_SECONDS:
            should_finalize = transcriber.has_trailing_silence(buffer.peek_bytes())

        if should_finalize:
            busy = True
            pcm_bytes = buffer.take_and_clear()
            last_partial_text = ""
            last_partial_at = 0.0
            try:
                text = await run_model(pcm_bytes, final=True)
                if text:
                    await websocket.send(json.dumps({"type": "final", "text": text}))
            finally:
                busy = False
            return

        # Still mid-sentence: periodically re-transcribe the whole open segment
        # so far and show it as a correctable preview (GPU headroom makes a
        # full re-decode each tick cheap enough — no need for the incremental
        # confirmed-prefix bookkeeping that CPU-bound streaming setups use).
        if time.monotonic() - last_partial_at < PARTIAL_INTERVAL_SECONDS:
            return
        busy = True
        try:
            text = await run_model(buffer.peek_bytes(), final=False)
            last_partial_at = time.monotonic()
            if text and text != last_partial_text:
                last_partial_text = text
                await websocket.send(json.dumps({"type": "partial", "text": text}))
        finally:
            busy = False

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                buffer.append(message)
                logger.info(
                    "Audio received: %d bytes (buffer duration: %.2fs)",
                    len(message),
                    buffer.duration_seconds(),
                )
                asyncio.create_task(maybe_transcribe())
            else:
                try:
                    control = json.loads(message)
                except json.JSONDecodeError:
                    logger.warning("Ignoring non-JSON text message: %s", message)
                    continue

                msg_type = control.get("type")
                if msg_type == "start":
                    logger.info("Subtitle session started")
                    buffer.clear()
                    last_partial_text = ""
                    last_partial_at = 0.0
                elif msg_type == "stop":
                    logger.info(
                        "Subtitle session stopped (total buffered: %.2fs)",
                        buffer.duration_seconds(),
                    )
                    buffer.clear()
                else:
                    logger.warning("Unknown control message: %s", control)
    except websockets.ConnectionClosed as exc:
        logger.info("WebSocket disconnected: %s", exc)
    except Exception:
        logger.exception("Error while handling WebSocket connection")


async def start_server():
    logger.info("Starting server on ws://%s:%d", HOST, PORT)
    async with websockets.serve(handler, HOST, PORT, max_size=None):
        await asyncio.Future()  # run forever
