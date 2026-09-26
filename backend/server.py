import asyncio
import json
import logging
import os
import re
import time
import wave

import websockets

import transcriber
import translator
from audio_buffer import BYTES_PER_SECOND, AudioBuffer
from config import (
    AUDIO_GAP_LOG_S,
    CHANNELS,
    HOST,
    MAX_CHUNK_SECONDS,
    MIN_CHUNK_SECONDS,
    PARTIAL_INTERVAL_SECONDS,
    PARTIAL_MIN_SECONDS,
    PORT,
    SAMPLE_RATE,
    SAMPLE_WIDTH_BYTES,
    SAVE_SESSION_AUDIO,
    SESSION_AUDIO_DIR,
    STT_HALLUCINATION_MAX_SPEECH_S,
    STT_HALLUCINATION_TEXTS,
    TRANSCRIBE_TIMEOUT_SECONDS,
    TRANSLATION_BOUNDARY_SILENCE_MS,
    TRANSLATION_IDLE_FLUSH_S,
    TRANSLATION_JOIN_CONTINUATION,
    TRANSLATION_JOIN_MAX_GAP_S,
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

_HALLUCINATION_STRIP_RE = re.compile(r"[\s、。,.!?！？…~〜ー]+")


def is_hallucination(text, speech_start_s, speech_end_s):
    """True for a known Whisper hallucination on a nearly speechless chunk,
    see config.STT_HALLUCINATION_TEXTS."""
    if _HALLUCINATION_STRIP_RE.sub("", text) not in STT_HALLUCINATION_TEXTS:
        return False
    speech_s = 0.0 if speech_start_s is None else speech_end_s - speech_start_s
    return speech_s < STT_HALLUCINATION_MAX_SPEECH_S


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


def open_session_recording():
    """WAV writer for this session's received audio (SAVE_SESSION_AUDIO)."""
    audio_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), SESSION_AUDIO_DIR)
    os.makedirs(audio_dir, exist_ok=True)
    path = os.path.join(audio_dir, time.strftime("session_%Y%m%d_%H%M%S.wav"))
    wav = wave.open(path, "wb")
    wav.setnchannels(CHANNELS)
    wav.setsampwidth(SAMPLE_WIDTH_BYTES)
    wav.setframerate(SAMPLE_RATE)
    logger.info("Recording session audio to %s", path)
    return wav


async def handler(websocket):
    logger.info("WebSocket connected: %s", websocket.remote_address)
    buffer = AudioBuffer()
    loop = asyncio.get_running_loop()
    recording = None  # wave writer while SAVE_SESSION_AUDIO is on

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

    # Stall diagnostics, see AUDIO_GAP_LOG_S. Only read for logging.
    diag = {"last_audio_at": None, "max_loop_lag": 0.0, "translating": None}

    stt_final_queue = asyncio.Queue()  # (segment_id, text, speech_start_s, speech_end_s)
    translation_queue = asyncio.Queue()  # (unit_id, source_segments, text, speech_start_s, last_speech_end_s)

    async def translation_worker():
        # Single FIFO consumer: this alone guarantees translations are sent in
        # the same order units were produced (no explicit reordering logic
        # needed), and runs fully independently of maybe_transcribe()'s `busy`
        # flag, so a slow translation can never block partial/final STT.
        # Previous unit, kept so a unit that finishes its sentence can be
        # translated together with it (see TRANSLATION_JOIN_CONTINUATION).
        # None after a joined unit: at most two units are joined.
        prev = None  # (unit_id, source_segments, text, last_speech_end_s)
        while True:
            unit_id, source_segments, japanese_text, speech_start_s, last_speech_end_s = await translation_queue.get()
            try:
                unit_text = japanese_text
                joined = False
                if (
                    TRANSLATION_JOIN_CONTINUATION
                    and prev is not None
                    and prev[3] is not None
                    and speech_start_s is not None
                    and 0 <= speech_start_s - prev[3] <= TRANSLATION_JOIN_MAX_GAP_S
                    and translator.continues(prev[2])
                ):
                    logger.info("[JOIN #%d] with #%d: %s + %s", unit_id, prev[0], prev[2], japanese_text)
                    source_segments = prev[1] + source_segments
                    japanese_text = prev[2] + japanese_text
                    joined = True
                prev = None if joined else (unit_id, source_segments, unit_text, last_speech_end_s)
                qsize = translation_queue.qsize()
                if qsize > 3:
                    logger.warning("[TRANSLATE QUEUE] backlog: %d pending", qsize)
                logger.info("[TRANSLATE START #%d]", unit_id)
                started = time.monotonic()
                diag["translating"] = (unit_id, started)
                result = await loop.run_in_executor(None, translator.translate, japanese_text)
                diag["translating"] = None
                elapsed_ms = (time.monotonic() - started) * 1000
                if result.final:
                    logger.info("[MODEL RAW #%d]\n%s", unit_id, result.raw)
                    logger.info("[ZH-TW #%d]\n%s", unit_id, result.final)
                    if last_speech_end_s is not None:
                        speech_end_wallclock = session_start_wallclock + last_speech_end_s
                        speech_to_ready_ms = (time.monotonic() - speech_end_wallclock) * 1000
                        logger.info(
                            "[LATENCY #%d] speech_end_to_translation_ready=%.0fms", unit_id, speech_to_ready_ms
                        )
                    send_started = time.monotonic()
                    await websocket.send(json.dumps({
                        "type": "translation",
                        "unit_id": unit_id,
                        "source_segments": source_segments,
                        "source_text": japanese_text,
                        "text": result.final,
                    }))
                    send_s = time.monotonic() - send_started
                    if send_s > 0.5:
                        logger.warning("[SLOW SEND #%d] sending the translation to the extension took %.1fs", unit_id, send_s)
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
            translation_queue.put_nowait((unit_id, seg_ids.copy(), merged, unit_start_audio_s, last_speech_end_s))
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

    async def loop_lag_monitor():
        # A 0.25s sleep that wakes much later means something blocked the
        # event loop (all audio handling, STT scheduling and sends stop too).
        while True:
            before = time.monotonic()
            await asyncio.sleep(0.25)
            lag = time.monotonic() - before - 0.25
            diag["max_loop_lag"] = max(diag["max_loop_lag"], lag)
            if lag > AUDIO_GAP_LOG_S:
                logger.warning("[LOOP LAG] backend event loop was blocked for %.1fs", lag)

    translation_worker_task = asyncio.create_task(translation_worker())
    loop_lag_task = asyncio.create_task(loop_lag_monitor())
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
                    start_off, end_off = transcriber.get_speech_span(pcm_bytes)
                    if is_hallucination(text, start_off, end_off):
                        logger.info("[STT HALLUCINATION] dropped %r (%.2fs of speech)", text,
                                    0.0 if start_off is None else end_off - start_off)
                        text = None
                    elif start_off is None:
                        # Kept text with no VAD speech (VAD fallback): the
                        # speech is somewhere in this chunk, so use the chunk
                        # itself as its span. Otherwise the sentence buffer
                        # timed it at 0s, logging a latency from the start of
                        # the session (73s) and breaking the join gap check.
                        start_off, end_off = 0.0, len(pcm_bytes) / BYTES_PER_SECOND
                if text:
                    segment_id = next_segment_id
                    next_segment_id += 1
                    logger.info("[FINAL JA #%d] (%.0fms)\n%s", segment_id, latency_ms, text)
                    await websocket.send(json.dumps({"type": "final", "segment_id": segment_id, "text": text}))

                    ok, reason = should_translate(text)
                    if ok:
                        speech_start_s = chunk_start_audio_pos + start_off if start_off is not None else None
                        speech_end_s = chunk_start_audio_pos + end_off if end_off is not None else None
                        stt_final_queue.put_nowait((segment_id, text, speech_start_s, speech_end_s))
                    else:
                        logger.info("[TRANSLATE SKIPPED #%d] reason=%s", segment_id, reason)
            except websockets.ConnectionClosed:
                pass  # the extension stopped while this final was in flight
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
        except websockets.ConnectionClosed:
            pass  # the extension stopped while this partial was in flight
        finally:
            busy = False

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                now = time.monotonic()
                if diag["last_audio_at"] is not None and now - diag["last_audio_at"] > AUDIO_GAP_LOG_S:
                    translating = diag["translating"]
                    logger.warning(
                        "[GAP] no audio from the extension for %.1fs | max event loop lag %.1fs | "
                        "STT busy=%s | translation queue=%d | translating=%s",
                        now - diag["last_audio_at"], diag["max_loop_lag"], busy, translation_queue.qsize(),
                        f"#{translating[0]} for {now - translating[1]:.1f}s" if translating else "no",
                    )
                diag["last_audio_at"] = now
                diag["max_loop_lag"] = 0.0
                buffer.append(message)
                if recording is not None:
                    recording.writeframes(message)
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
                if msg_type == "diag":
                    logger.warning("[CLIENT DIAG] %s", {k: v for k, v in control.items() if k != "type"})
                elif msg_type == "start":
                    logger.info("Subtitle session started")
                    buffer.clear()
                    last_partial_text = ""
                    last_partial_at = 0.0
                    next_segment_id = 0
                    next_unit_id = 0
                    audio_position_s = 0.0
                    segment_start_audio_pos = 0.0
                    session_start_wallclock = time.monotonic()
                    diag["last_audio_at"] = None
                    if recording is not None:
                        recording.close()
                    recording = open_session_recording() if SAVE_SESSION_AUDIO else None
                elif msg_type == "stop":
                    logger.info(
                        "Subtitle session stopped (total buffered: %.2fs)",
                        buffer.duration_seconds(),
                    )
                    buffer.clear()
                    if recording is not None:
                        recording.close()
                        recording = None
                else:
                    logger.warning("Unknown control message: %s", control)
    except websockets.ConnectionClosed as exc:
        logger.info("WebSocket disconnected: %s", exc)
    except Exception:
        logger.exception("Error while handling WebSocket connection")
    finally:
        translation_worker_task.cancel()
        sentence_buffer_task.cancel()
        loop_lag_task.cancel()
        if recording is not None:
            recording.close()


async def start_server():
    logger.info("Starting server on ws://%s:%d", HOST, PORT)
    async with websockets.serve(handler, HOST, PORT, max_size=None):
        await asyncio.Future()  # run forever
