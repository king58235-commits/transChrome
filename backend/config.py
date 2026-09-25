HOST = "127.0.0.1"
PORT = 8765

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2  # PCM16

# Model name centralized here (not hardcoded per-file) so switching is a
# one-line change — useful for debugging (benchmark results for each preset
# are in backend/benchmark/result_*.json).
STT_MODEL_PRESETS = {
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "kotoba": "kotoba-tech/kotoba-whisper-v2.0-faster",
}
STT_MODEL = "kotoba"  # active preset key, see STT_MODEL_PRESETS above
WHISPER_LANGUAGE = "ja"

# Hardware preset: the single source of truth for which device each model
# runs on. Centralized here (not hardcoded per-file in transcriber.py/
# translator.py) — see backend/benchmark/hardware_compat_matrix.md for the
# benchmark this is based on. Only two presets exist right now; a "low"
# (CPU-only) preset was explicitly ruled out as not viable (Kotoba on CPU
# measured at realtime factor 2.622 — can't keep up with live audio at all).
HARDWARE_PRESET = "balanced"

HARDWARE_PRESETS = {
    # RTX 3050 8GB-class cards: VRAM is too tight for both models on GPU at
    # once (benchmarked peak 7533/8192 MiB with only ~660MB headroom) —
    # Kotoba stays on GPU (STT responsiveness matters most), MADLAD moves to
    # CPU (benchmarked: 1.6s avg / 2.9s P95 latency, well within budget).
    "balanced": {"stt_device": "cuda", "translation_device": "cpu"},
    # RTX 4070 Ti-class cards (12GB+): both models fit on GPU with real
    # headroom to spare; translation latency drops ~3x (528ms vs 1597ms avg).
    "high": {"stt_device": "cuda", "translation_device": "cuda"},
}

if HARDWARE_PRESET not in HARDWARE_PRESETS:
    valid_values = "\n".join(HARDWARE_PRESETS)
    raise ValueError(
        f"Invalid HARDWARE_PRESET {HARDWARE_PRESET!r} in config.py. Valid values:\n{valid_values}"
    )

STT_DEVICE = HARDWARE_PRESETS[HARDWARE_PRESET]["stt_device"]
TRANSLATION_DEVICE = HARDWARE_PRESETS[HARDWARE_PRESET]["translation_device"]

# Streaming: while a sentence is still being spoken, periodically re-transcribe
# the whole open segment and show it as a correctable "partial" preview.
# Finalize (commit and clear) at a natural pause, so a segment lands close to
# a whole sentence instead of being cut mid-word at an arbitrary boundary.
MIN_CHUNK_SECONDS = 1.0  # never finalize before this much audio, even if silent
MAX_CHUNK_SECONDS = 8.0  # force a finalize after this much regardless of VAD, so
# uninterrupted speech doesn't grow latency unboundedly
SILENCE_TRIGGER_MS = 300  # trailing silence needed to count as "a pause happened"

PARTIAL_MIN_SECONDS = 0.5  # don't bother transcribing a shorter open segment
PARTIAL_INTERVAL_SECONDS = 0.75  # how often to refresh the partial preview

# Safety net: a chunk with no clear speech can occasionally make Whisper's
# decoder loop far longer than normal (see transcriber.py). Give up and move on
# rather than blocking all future transcription for the rest of the session.
TRANSCRIBE_TIMEOUT_SECONDS = 12

# Japanese -> Traditional Chinese translation of finalized text only.
# MADLAD-400 3B (ctranslate2, int8) — chosen over NLLB 600M/1.3B after the
# Stage 2B translation model benchmark (backend/benchmark/
# translation_model_comparison.md) for clearly better long/transitional-
# sentence and katakana/loanword handling. no_repeat_ngram_size=3 (calibrated
# in benchmark/madlad_decoding_sweep.md) eliminates the short-utterance
# repetition-loop failure mode MADLAD showed at default decoding settings,
# with zero measured cost to long-sentence quality (byte-identical output on
# the tracked long-sentence/katakana test cases).
TRANSLATION_MODEL_REPO = "Heng666/madlad400-3b-mt-ct2-int8"
TRANSLATION_TGT_TOKEN = "<2zh>"  # MADLAD has a native <2zh_Hant> too, but sticking to
# Simplified + OpenCC for consistency with how it was benchmarked
TRANSLATION_COMPUTE_TYPE_GPU = "int8_float16"
TRANSLATION_COMPUTE_TYPE_CPU = "int8"
TRANSLATION_BEAM_SIZE = 4
TRANSLATION_NO_REPEAT_NGRAM_SIZE = 3
OPENCC_CONFIG = "s2twp"  # Simplified -> Taiwan Traditional with phrase conversion

# Translation Sentence Buffer (server.py) v2: merges consecutive STT final
# segments before sending to the translation model, so a sentence split across multiple STT
# finals (e.g. a mid-sentence breath pause under SILENCE_TRIGGER_MS) doesn't
# get translated as disconnected fragments that lose all context. This ONLY
# affects when translation happens — Japanese partial/final display stays on
# its existing immediate timing, untouched.
#
# v1 used the wall-clock arrival gap between STT final *messages* as the merge
# signal. Verified empirically that's unreliable: that gap is inflated by
# MIN_CHUNK_SECONDS, audio buffering, STT inference latency, and asyncio
# scheduling — none of which reflect when the speaker actually paused. v2
# instead uses the real audio-timeline speech gap (via VAD start/end
# timestamps carried on each finalized segment, see transcriber.get_speech_span
# and server.py), and drops the old fixed extra-wait timers entirely — a unit
# now finalizes the instant a real silence gap is observed, not after a fixed
# 1.4-2.2s delay tacked onto every single translation regardless of need.
TRANSLATION_BOUNDARY_SILENCE_MS = 800  # real audio gap needed to end a translation unit
TRANSLATION_MAX_AUDIO_SECONDS = 7.0  # force-flush once the unit's speech span exceeds this
TRANSLATION_MAX_CHARS = 70  # force-flush once buffered text reaches this many JA characters
# Pure safety net for "no further STT final ever arrives" (speaker stopped
# talking / stream ended) — NOT the primary boundary decision (the real-audio
# gap above is); this only prevents a pending unit from waiting forever with
# nothing left to compare it against. In practice this fires far more often
# than the real-gap check on typical content (see benchmark sweep below), so
# it's also the dominant latency contributor — calibrated via a 4-point sweep
# on test_clip.wav (0.9/1.2/1.5/2.0s): 1.2s hit the ~1.5-2.5s target avg
# latency (2088ms measured) without producing obviously-wrong merges, while
# shorter values (0.9s) suppressed merging almost entirely and longer values
# (1.5s+) pushed latency over target for only marginal merge-quality gains.
TRANSLATION_IDLE_FLUSH_S = 1.2
