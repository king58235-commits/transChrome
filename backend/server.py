import asyncio
import json
import logging
import re
import time

import websockets

import transcriber
import translator
from audio_buffer import BYTES_PER_SECOND, AudioBuffer
from config import (
    HOST,
    MAX_CHUNK_SECONDS,
    MIN_CHUNK_SECONDS,
    PARTIAL_INTERVAL_SECONDS,
    PARTIAL_MIN_SECONDS,
    PORT,
    TRANSCRIBE_TIMEOUT_SECONDS,
    TRANSLATION_BOUNDARY_SILENCE_MS,
    TRANSLATION_IDLE_FLUSH_S,
    TRANSLATION_MAX_AUDIO_SECONDS,
    TRANSLATION_MAX_CHARS,
)

logger = logging.getLogger("server")

# Threshold picked to match the user's own hallucination examples ("まままままま"
# = 6 chars) while staying conservative: a 3-4 char elongated sound ("えーー")
# is normal casual speech and must NOT be rejected — only clear 6+ repeat runs.
_REPEATED_CHAR_RE = re.compile(r"(.)\1{5,}")
_WORD_CHAR_RE = re.compile(r"[^\W_]", re.UNICODE)

TRANSLATION_BOUNDARY_SILENCE_S = TRANSLATION_BOUNDARY_SILENCE_MS / 1000


def should_translate(text: str) -> tuple[bool, str]:
    """Conservative translation gate. Returns (ok, reason_if_rejected).
    Deliberately does NOT reject on short length — live speech is full of
    valid short utterances ("何色?", "赤。", "え？", "うん。") that must not
    be silently dropped just for being short."""
    stripped = text.strip()
    if not stripped:
        return False, "empty"
    if not _WORD_CHAR_RE.search(stripped):
        return False, "punctuation-only"
    if _REPEATED_CHAR_RE.search(stripped):
        return False, "repeated-char hallucination pattern"
    return True, ""


async def handler(websocket):
    logger.info("WebSocket connected: %s", websocket.remote_address)
    buffer = AudioBuffer()
    loop = asyncio.get_running_loop()

    busy = False
    last_partial_text = ""
    last_partial_at = 0.0
    next_segment_id = 0  # STT final segment ids
    next_unit_id = 0  # translation unit ids — deliberately a separate counter

    # Audio-timeline bookkeeping (NOT wall-clock): audio_position_s is total
    # seconds of audio received since "start"; segment_start_audio_pos is
    # where the currently-accumulating STT buffer began on that timeline.
    # session_start_wallclock anchors the two together so a translation
    # latency can be measured from when the speaker actually stopped talking
    # (audio-timeline) rather than from an STT/translation message's arrival.
    audio_position_s = 0.0
    segment_start_audio_pos = 0.0
    session_start_wallclock = time.monotonic()

    stt_final_queue = asyncio.Queue()  # (segment_id, text, speech_start_s, speech_end_s)
    translation_queue = asyncio.Queue()  # (unit_id, source_segments, text, last_speech_end_s)

    async def translation_worker():
        # Single FIFO consumer: this alone guarantees translations are sent in
        # the same order units were produced (no explicit reordering logic
        # needed), and runs fully independently of maybe_transcribe()'s `busy`
        # flag, so a slow translation can never block partial/final STT.
        while True:
            unit_id, source_segments, japanese_text, last_speech_end_s = await translation_queue.get()
            try:
                qsize = translation_queue.qsize()
                if qsize > 3:
                    logger.warning("[TRANSLATE QUEUE] backlog: %d pending", qsize)
                logger.info("[TRANSLATE START #%d]", unit_id)
                started = time.monotonic()
                result = await loop.run_in_executor(None, translator.translate, japanese_text)
                elapsed_ms = (time.monotonic() - started) * 1000
                if result.final:
                    logger.info("[NLLB RAW #%d]\n%s", unit_id, result.raw)
                    logger.info("[ZH-TW #%d]\n%s", unit_id, result.final)
                    if last_speech_end_s is not None:
                        speech_end_wallclock = session_start_wallclock + last_speech_end_s
                        speech_to_ready_ms = (time.monotonic() - speech_end_wallclock) * 1000
                        logger.info(
                            "[LATENCY #%d] speech_end_to_translation_ready=%.0fms", unit_id, speech_to_ready_ms
                        )
                    await websocket.send(json.dumps({
                        "type": "translation",
                        "unit_id": unit_id,
                        "source_segments": source_segments,
                        "source_text": japanese_text,
                        "text": result.final,
                    }))
                else:
                    logger.info("[ZH-TW #%d]\n(translation unavailable)", unit_id)
                logger.info("[TRANSLATE DONE #%d]\nlatency=%.0f ms", unit_id, elapsed_ms)
            except websockets.ConnectionClosed:
                break
            except Exception:
                logger.exception("[TRANSLATE #%d] worker error", unit_id)
            finally:
                translation_queue.task_done()

    async def sentence_buffer_worker():
        nonlocal next_unit_id
        # Merges consecutive STT finals into one translation unit, using the
        # REAL audio-timeline gap between one segment's detected speech end
        # and the next one's detected speech start (both from VAD) — NOT the
        # wall-clock arrival gap between STT final messages, which is
        # inflated by MIN_CHUNK_SECONDS/buffering/inference/scheduling and
        # doesn't reflect when the speaker actually paused (verified
        # empirically). A unit finalizes the instant a real pause is seen, or
        # once the safety caps below are hit — no fixed extra wait tacked on.
        seg_ids = []
        texts = []
        unit_start_audio_s = None
        last_speech_end_s = None

        async def flush(reason):
            nonlocal seg_ids, texts, unit_start_audio_s, last_speech_end_s, next_unit_id
            if not texts:
                return
            merged = "".join(texts)
            unit_id = next_unit_id
            next_unit_id += 1
            span_s = (last_speech_end_s - unit_start_audio_s) if unit_start_audio_s is not None else 0.0
            logger.info(
                "[TRANSLATION BUFFER #%d]\nsegments=%s\ntext=%s\naudio_span=%.2fs reason=%s",
                unit_id, seg_ids, merged, span_s, reason,
            )
            translation_queue.put_nowait((unit_id, seg_ids.copy(), merged, last_speech_end_s))
            seg_ids = []
            texts = []
            unit_start_audio_s = None
            last_speech_end_s = None

        while True:
            try:
                segment_id, text, speech_start_s, speech_end_s = await asyncio.wait_for(
                    stt_final_queue.get(), timeout=(TRANSLATION_IDLE_FLUSH_S if texts else None)
                )
            except asyncio.TimeoutError:
                await flush("idle_timeout")
                continue

            if speech_start_s is None or speech_end_s is None:
                # No speech detected by VAD in this chunk (shouldn't normally
                # happen — text was non-empty — but guard defensively): treat
                # it as immediately following whatever came before.
                speech_start_s = last_speech_end_s if last_speech_end_s is not None else 0.0
                speech_end_s = speech_start_s

            if texts and last_speech_end_s is not None:
                gap_ms = (speech_start_s - last_speech_end_s) * 1000
                if gap_ms >= TRANSLATION_BOUNDARY_SILENCE_MS:
                    await flush("real_silence_gap")

            if not texts:
                unit_start_audio_s = speech_start_s
            seg_ids.append(segment_id)
            texts.append(text)
            last_speech_end_s = speech_end_s

            span_s = last_speech_end_s - unit_start_audio_s
            char_count = sum(len(t) for t in texts)
            if span_s >= TRANSLATION_MAX_AUDIO_SECONDS or char_count >= TRANSLATION_MAX_CHARS:
                await flush("max_cap")

    translation_worker_task = asyncio.create_task(translation_worker())
    sentence_buffer_task = asyncio.create_task(sentence_buffer_worker())

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
            return None, 0.0
        except Exception:
            logger.exception("%s transcription failed", kind)
            return None, 0.0
        return text, (time.monotonic() - started) * 1000

    async def maybe_transcribe():
        nonlocal busy, last_partial_text, last_partial_at, next_segment_id, segment_start_audio_pos
        if busy:
            return
        duration = buffer.duration_seconds()
        if duration < PARTIAL_MIN_SECONDS:
            return

        # Finalize (commit + clear) at a natural pause so a segment lands close
        # to a whole sentence, or once it's grown long enough that waiting for
        # a pause would make latency unbounded. This threshold stays small
        # (~300ms) on purpose — it's tuned for Japanese display responsiveness.
        # Sentence-level context for translation is handled separately by
        # sentence_buffer_worker above, using real audio timing, not this.
        should_finalize = duration >= MAX_CHUNK_SECONDS
        if not should_finalize and duration >= MIN_CHUNK_SECONDS:
            should_finalize = transcriber.has_trailing_silence(buffer.peek_bytes())

        if should_finalize:
            busy = True
            pcm_bytes = buffer.take_and_clear()
            chunk_start_audio_pos = segment_start_audio_pos
            segment_start_audio_pos = audio_position_s  # next chunk starts from here
            last_partial_text = ""
            last_partial_at = 0.0
            try:
                text, latency_ms = await run_model(pcm_bytes, final=True)
                if text:
                    segment_id = next_segment_id
                    next_segment_id += 1
                    logger.info("[FINAL JA #%d] (%.0fms)\n%s", segment_id, latency_ms, text)
                    await websocket.send(json.dumps({"type": "final", "segment_id": segment_id, "text": text}))

                    ok, reason = should_translate(text)
                    if ok:
                        start_off, end_off = transcriber.get_speech_span(pcm_bytes)
                        speech_start_s = chunk_start_audio_pos + start_off if start_off is not None else None
                        speech_end_s = chunk_start_audio_pos + end_off if end_off is not None else None
                        stt_final_queue.put_nowait((segment_id, text, speech_start_s, speech_end_s))
                    else:
                        logger.info("[TRANSLATE SKIPPED #%d] reason=%s", segment_id, reason)
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
            text, latency_ms = await run_model(buffer.peek_bytes(), final=False)
            last_partial_at = time.monotonic()
            if text and text != last_partial_text:
                last_partial_text = text
                logger.info("[PARTIAL JA] (%.0fms)\n%s", latency_ms, text)
                await websocket.send(json.dumps({"type": "partial", "text": text}))
        finally:
            busy = False

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                buffer.append(message)
                audio_position_s += len(message) / BYTES_PER_SECOND
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
                    next_segment_id = 0
                    next_unit_id = 0
                    audio_position_s = 0.0
                    segment_start_audio_pos = 0.0
                    session_start_wallclock = time.monotonic()
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
    finally:
        translation_worker_task.cancel()
        sentence_buffer_task.cancel()


async def start_server():
    logger.info("Starting server on ws://%s:%d", HOST, PORT)
    async with websockets.serve(handler, HOST, PORT, max_size=None):
        await asyncio.Future()  # run forever
