import importlib.util
import logging
import os
import sys


def _register_nvidia_dll_dirs():
    # ctranslate2's native loader on Windows uses the classic LoadLibrary search
    # order, which os.add_dll_directory() alone does not affect — only
    # prepending PATH actually gets cublas64_12.dll/cudnn64_9.dll found. These
    # DLLs come from the pip-installed nvidia-cublas-cu12/nvidia-cudnn-cu12
    # wheels (no full CUDA Toolkit install needed). Must run before ctranslate2
    # (imported transitively by faster_whisper below) is ever imported.
    if sys.platform != "win32":
        return
    spec = importlib.util.find_spec("nvidia")
    if spec is None or not spec.submodule_search_locations:
        return
    dirs = []
    for base in spec.submodule_search_locations:
        for pkg in ("cublas", "cudnn", "cuda_nvrtc"):
            bin_dir = os.path.join(base, pkg, "bin")
            if os.path.isdir(bin_dir):
                dirs.append(bin_dir)
                os.add_dll_directory(bin_dir)
    if dirs:
        os.environ["PATH"] = os.pathsep.join(dirs) + os.pathsep + os.environ.get("PATH", "")


_register_nvidia_dll_dirs()

import numpy as np
from faster_whisper import WhisperModel
from faster_whisper.vad import VadOptions, get_speech_timestamps

from config import SAMPLE_RATE, SILENCE_TRIGGER_MS, STT_MODEL, STT_MODEL_PRESETS, WHISPER_LANGUAGE

MODEL_REPO = STT_MODEL_PRESETS[STT_MODEL]

logger = logging.getLogger("transcriber")

_model = None
_silence_vad_options = VadOptions(min_silence_duration_ms=SILENCE_TRIGGER_MS, speech_pad_ms=0)


def _pcm16_to_float32(pcm16_bytes: bytes) -> np.ndarray:
    return np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0

# A chunk with no clear speech (silence/music/a word cut off at a boundary) can
# occasionally make Whisper's decoder fall into a runaway repetition loop,
# taking 10-100x longer than normal instead of erroring out.
# condition_on_previous_text=False stops it compounding across chunks, and
# vad_filter=True (faster-whisper's built-in Silero VAD, not a reimplementation)
# skips non-speech audio before it ever reaches the decoder.
#
# Partial previews (re-run every PARTIAL_INTERVAL_SECONDS while a sentence is
# still open) use beam_size=1 (greedy) to stay fast and frequent. The final
# pass for a segment runs once per sentence, so GPU headroom (see benchmark:
# ~130ms for 5s of audio) affords a higher beam_size there for better accuracy.
PARTIAL_KWARGS = dict(beam_size=1, condition_on_previous_text=False, vad_filter=True)
FINAL_KWARGS = dict(beam_size=5, condition_on_previous_text=False, vad_filter=True)


def load_model():
    # No silent model-level fallback: if MODEL_REPO itself is bad (typo'd repo
    # id, no internet, etc.) rather than just "CUDA is unusable", the CPU
    # attempt below fails too and the exception propagates out of this
    # function uncaught — main.py has no try/except around this call, so
    # that's a loud startup crash with a full traceback, not a silent
    # downgrade to a different STT model.
    global _model
    logger.info("Loading STT model '%s' (preset '%s')", MODEL_REPO, STT_MODEL)
    try:
        candidate = WhisperModel(MODEL_REPO, device="cuda", compute_type="float16")
        # get_cuda_device_count() only checks the CUDA driver; it doesn't confirm
        # the cuBLAS/cuDNN runtime DLLs used during actual inference are present.
        # Run one real (tiny) inference to catch that before committing to CUDA.
        # vad_filter must be off here: the dummy audio is silence, and with VAD
        # on it would be filtered out before ever reaching the GPU encoder,
        # making this check pass even when CUDA is actually unusable.
        list(candidate.transcribe(np.zeros(16000, dtype=np.float32), language=WHISPER_LANGUAGE, beam_size=1)[0])
        _model = candidate
        logger.info("STT model '%s' loaded on CUDA (float16)", MODEL_REPO)
    except Exception:
        logger.warning(
            "'%s' failed on CUDA (could be a missing cuBLAS/cuDNN runtime, or a real "
            "model problem — see traceback below); retrying on CPU. If this ALSO "
            "fails, that error will propagate and crash startup rather than "
            "silently trying a different model.",
            MODEL_REPO,
            exc_info=True,
        )
        _model = WhisperModel(MODEL_REPO, device="cpu", compute_type="int8")
        logger.info("STT model '%s' loaded on CPU (int8)", MODEL_REPO)
    return _model


def transcribe(pcm16_bytes: bytes, final: bool = False) -> str:
    if _model is None:
        raise RuntimeError("Whisper model not loaded; call load_model() first")

    audio = _pcm16_to_float32(pcm16_bytes)
    kwargs = FINAL_KWARGS if final else PARTIAL_KWARGS
    segments, _info = _model.transcribe(audio, language=WHISPER_LANGUAGE, **kwargs)
    return "".join(segment.text for segment in segments).strip()


def has_trailing_silence(pcm16_bytes: bytes) -> bool:
    """True if the buffered audio currently ends in a speech pause (or has no
    detected speech at all), meaning now is a safe/natural point to cut a
    chunk instead of splitting mid-word/mid-sentence."""
    audio = _pcm16_to_float32(pcm16_bytes)
    segments = get_speech_timestamps(audio, _silence_vad_options, sampling_rate=SAMPLE_RATE)
    if not segments:
        return True
    trailing_samples = len(audio) - segments[-1]["end"]
    trailing_ms = trailing_samples / SAMPLE_RATE * 1000
    return trailing_ms >= SILENCE_TRIGGER_MS


def get_speech_span(pcm16_bytes: bytes):
    """Returns (first_speech_start_s, last_speech_end_s), both in seconds
    relative to the start of this chunk — the real VAD-detected speech
    envelope, for computing actual audio-timeline gaps between segments (see
    server.py's sentence_buffer_worker). Returns (None, None) if no speech
    was detected in this chunk at all."""
    audio = _pcm16_to_float32(pcm16_bytes)
    segments = get_speech_timestamps(audio, _silence_vad_options, sampling_rate=SAMPLE_RATE)
    if not segments:
        return None, None
    return segments[0]["start"] / SAMPLE_RATE, segments[-1]["end"] / SAMPLE_RATE
