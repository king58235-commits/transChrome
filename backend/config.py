VERSION = "1.0.0"  # shown at startup; keep in sync with extension/manifest.json

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
HARDWARE_PRESET = "high"

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

# VAD fallback: Silero VAD sometimes hears no speech at all in loud speech
# mixed with game audio or cooking noise (0.0s detected in 12s of continuous
# talking in a 09-26 live test), so that audio was thrown away and subtitles
# stopped. When VAD finds under VAD_FALLBACK_MAX_SPEECH_S of speech but the
# audio is at least VAD_FALLBACK_MIN_RMS loud, it is transcribed without
# Whisper's VAD filter, and a pause is only assumed once the audio also gets
# quiet. Replaying 4 recordings: 12 and 25 real lines recovered in the game
# and cooking streams, 1-3 extra short lines in the quiet/music ones, no
# invented text; ZH latency +0.1s median where it kicks in. Missed speech
# measured RMS 0.04-0.13, near-silent chunks (where Kotoba hallucinates
# ごめん) 0.003-0.026. False turns it off.
VAD_FALLBACK_ENABLED = True
VAD_FALLBACK_MIN_RMS = 0.04
VAD_FALLBACK_MAX_SPEECH_S = 0.3

PARTIAL_MIN_SECONDS = 0.5  # don't bother transcribing a shorter open segment
PARTIAL_INTERVAL_SECONDS = 0.75  # how often to refresh the partial preview

# Safety net: a chunk with no clear speech can occasionally make Whisper's
# decoder loop far longer than normal (see transcriber.py). Give up and move on
# rather than blocking all future transcription for the rest of the session.
TRANSCRIBE_TIMEOUT_SECONDS = 12

# Whisper hallucination filter: a final whose whole text is one of these AND
# whose chunk had less than STT_HALLUCINATION_MAX_SPEECH_S of VAD-detected
# speech is dropped (not shown, not translated). A chunk that is nearly all
# noise (cooking, eating, game sounds) gets finalized once it passes
# MIN_CHUNK_SECONDS with a trailing pause, and Kotoba then invents a word. In
# every live log up to 2026-09-26, all 17 ごめん finals had under 0.2s of
# speech and none of the 471 finals with 0.3s+ was ごめん (saying it takes
# ~0.4s). Both conditions are required: real short lines like 普通にうまい!
# also showed up with under 0.2s measured speech.
STT_HALLUCINATION_TEXTS = {"ごめん"}
STT_HALLUCINATION_MAX_SPEECH_S = 0.3

# Debug/benchmark aid: also save each subtitle session's received audio
# (exactly what STT saw, 16kHz mono PCM16) as a WAV in SESSION_AUDIO_DIR
# (relative to backend/), so a live session can be replayed offline for STT /
# Translation Buffer tuning. About 115MB per hour. It is the stream's audio,
# so it stays local (git-ignored). Doesn't affect subtitles either way.
SAVE_SESSION_AUDIO = False
SESSION_AUDIO_DIR = "recordings"

# Also write the console log to LOG_DIR (relative to backend/), one file per
# backend start, so a live session can be analyzed without copy-pasting the
# console. About 3MB per hour (mostly the per-chunk "Audio received" lines).
# Git-ignored.
LOG_TO_FILE = True
LOG_DIR = "logs"

# Stall diagnostics (log only, no behavior change): when no audio arrives
# from the extension for this long, log a [GAP] line with what the backend
# was doing (event loop lag, STT busy, translation in flight). The extension
# reports its own side ([CLIENT DIAG]: capture gaps, WebSocket send backlog).
AUDIO_GAP_LOG_S = 1.0

# Japanese -> Traditional Chinese translation of finalized text only.
# "sakura" (production): Sakura-7B via a llama.cpp server started once at
# backend startup and kept loaded on the GPU. Picked over MADLAD, Sakura-1.5B
# and Qwen2.5-7B in the 09-26 offline benchmark on the fixed live/original
# datasets: clearly better meaning accuracy (42/48 and 21/26 on MADLAD's
# failure cases vs 19/48 and ~1/26 for MADLAD), no padding, and 4-5x faster
# (110ms avg / 241ms P95 per sentence vs 507 / 839ms).
# "madlad" (legacy, kept for rollback): the settings below this block.
TRANSLATION_BACKEND = "sakura"

# Sakura-7B: the exact GGUF the benchmark used (don't swap quantization
# without re-benchmarking). Downloaded to the Hugging Face cache on first run.
SAKURA_MODEL_REPO = "SakuraLLM/Sakura-7B-Qwen2.5-v1.0-GGUF"
SAKURA_MODEL_FILE = "sakura-7b-qwen2.5-v1.0-iq4xs.gguf"
# llama.cpp release the benchmark used, installed by setup_llama.py into
# LLAMA_SERVER_DIR (relative to backend/, git-ignored). Always runs fully on
# the GPU (-ngl 99); HARDWARE_PRESET's translation_device only applies to
# the legacy MADLAD backend.
LLAMA_CPP_RELEASE = "b11200"
LLAMA_SERVER_DIR = "runtime/llama.cpp"
LLAMA_SERVER_PORT = 8790  # local only; 8765 is the backend, 8766 replay_session.py
# Output safety rail: at most this many output tokens per sentence (Sakura
# averaged ~8 tokens per unit in the benchmark; a 70-char unit needs well
# under 100), and generation stops early on a runaway repetition like
# "啊啊啊啊…" (Sakura-1.5B produced 160 of them once in the benchmark).
SAKURA_MAX_TOKENS_PER_CHAR = 2
SAKURA_MAX_TOKENS_MIN = 32
SAKURA_MAX_TOKENS_CAP = 320

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
# Below ctranslate2's default 1.0 = beam search leans toward shorter finished
# hypotheses. Cuts MADLAD's padding/duplication on short live utterances
# ("懐かしいね" -> "很想念, 很難忘, 太想念了") without touching CASE1/4/5;
# 0.0 over-shortened. Calibrated in benchmark/madlad_decoding_sweep.md
# (live-session section).
TRANSLATION_LENGTH_PENALTY = 0.5
# Drop a clause of the Chinese output that just repeats an earlier one in
# other words ("我太緊張了，我很緊張。" -> "我太緊張了。"); see
# translator.drop_repeated_clauses. False turns it off. Calibrated on and only
# applied to MADLAD output (Sakura didn't pad or restate in the benchmark).
TRANSLATION_DROP_REPEATED_CLAUSES = True
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
# How long a finished STT final waits for the next one before being
# translated on its own (the "no further STT final arrives" case). Was 1.2s
# (4-point sweep on test_clip.wav). Live High-preset sessions showed that wait
# almost never produced a merge (0 of 68 units in the recorded session), so it
# only delayed the Chinese line: it appeared 1.8s after the Japanese final,
# by which time the Japanese line had already moved to the next sentence 46%
# of the time. Replaying that recording (benchmark/replay_session.py) at 1.2 /
# 0.6 / 0.0s: Chinese ready 1.82 / 1.13 / 0.56s after the final, "late" 49% /
# 25% / 15%, and identical translations for every sentence both runs shared.
# 0.0 = translate as soon as a final arrives (units still merge if several
# finals are already queued, and the max caps above still apply).
TRANSLATION_IDLE_FLUSH_S = 0.0
# When the previous unit ended mid-sentence (…て, …けど, …と, see
# translator.continues) and this unit follows within TRANSLATION_JOIN_MAX_GAP_S
# of audio, translate both together; the Chinese line (which each translation
# replaces anyway) then shows the joined sentence. At most two units are
# joined. On 24 such pairs from the 09-26 logs the joined translation was
# better in ~15, about the same in ~6, worse in ~3 ("ズボン履いて / 上からスカート"
# -> "褲子和上面的裙子" instead of "身上長了毛髮" + "從上面的裙子裙子").
# Joining after a short last unit (no continuation ending) was net worse, so
# it isn't done. False turns it off.
TRANSLATION_JOIN_CONTINUATION = True
TRANSLATION_JOIN_MAX_GAP_S = 3.0
