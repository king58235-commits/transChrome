"""Stage 2A model A/B benchmark: replays a fixed WAV through the SAME
VAD-triggered finalize logic as server.py's maybe_transcribe(), for a given
Whisper model. Run once per model (fresh process each time for clean VRAM).

Usage:
    venv\\Scripts\\python.exe benchmark\\run_model.py <model_repo_or_size> <wav_path> <out_json>
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, ".")
from transcriber import _register_nvidia_dll_dirs  # noqa: E402 (registers CUDA DLL dirs on import)

import argparse
import json
import re
import subprocess
import time
import wave

import numpy as np
from faster_whisper import WhisperModel
from faster_whisper.vad import VadOptions, get_speech_timestamps

from config import (
    MAX_CHUNK_SECONDS,
    MIN_CHUNK_SECONDS,
    PARTIAL_MIN_SECONDS,
    SAMPLE_RATE,
    SILENCE_TRIGGER_MS,
    WHISPER_LANGUAGE,
)

BYTES_PER_SECOND = SAMPLE_RATE * 2  # PCM16 mono
CHUNK_BYTES = int(SAMPLE_RATE * 0.25) * 2  # 250ms, matching the extension's real cadence

# Same as transcriber.py's FINAL_KWARGS — this benchmark is specifically about
# finalized-caption quality (what actually gets shown/translated), not partials.
FINAL_KWARGS = dict(beam_size=5, condition_on_previous_text=False, vad_filter=True)

_vad_options = VadOptions(min_silence_duration_ms=SILENCE_TRIGGER_MS, speech_pad_ms=0)


def has_trailing_silence(pcm16_bytes: bytes) -> bool:
    audio = np.frombuffer(pcm16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    segments = get_speech_timestamps(audio, _vad_options, sampling_rate=SAMPLE_RATE)
    if not segments:
        return True
    trailing_samples = len(audio) - segments[-1]["end"]
    return (trailing_samples / SAMPLE_RATE * 1000) >= SILENCE_TRIGGER_MS


def gpu_mem_mb():
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True,
    ).stdout.strip()
    return int(out.splitlines()[0])


def transcribe_chunk(model, pcm_bytes):
    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    segs, _info = model.transcribe(audio, language=WHISPER_LANGUAGE, **FINAL_KWARGS)
    return "".join(s.text for s in segs).strip()


def flag_issues(text):
    flags = []
    if re.search(r"(.)\1{2,}", text):
        flags.append("repetitive_char")
    if len(text.replace("、", "").replace("。", "").replace(" ", "")) <= 3:
        flags.append("very_short")
    return flags


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model_repo")
    parser.add_argument("wav_path")
    parser.add_argument("out_json")
    args = parser.parse_args()

    vram_before = gpu_mem_mb()
    t0 = time.monotonic()
    device_used = "cuda"
    try:
        model = WhisperModel(args.model_repo, device="cuda", compute_type="float16")
        list(model.transcribe(np.zeros(16000, dtype=np.float32), language=WHISPER_LANGUAGE, beam_size=1)[0])
    except Exception as e:
        print(f"CUDA failed ({e}), falling back to CPU", file=sys.stderr)
        model = WhisperModel(args.model_repo, device="cpu", compute_type="int8")
        device_used = "cpu"
    load_time = time.monotonic() - t0
    vram_after_load = gpu_mem_mb()
    print(f"Loaded {args.model_repo} on {device_used} in {load_time:.2f}s (VRAM {vram_before}->{vram_after_load} MiB)")

    wav = wave.open(args.wav_path, "rb")
    all_bytes = wav.readframes(wav.getnframes())
    wav.close()
    audio_duration = len(all_bytes) / BYTES_PER_SECOND

    buffer = bytearray()
    segments_out = []
    total_infer_time = 0.0
    peak_vram = vram_after_load
    pos = 0
    n = len(all_bytes)

    def finalize(pcm_bytes, elapsed_since_start_s):
        nonlocal total_infer_time, peak_vram
        t1 = time.monotonic()
        text = transcribe_chunk(model, pcm_bytes)
        elapsed = time.monotonic() - t1
        total_infer_time += elapsed
        peak_vram = max(peak_vram, gpu_mem_mb())
        if text:
            entry = {
                "at_s": round(elapsed_since_start_s, 1),
                "chunk_duration_s": round(len(pcm_bytes) / BYTES_PER_SECOND, 2),
                "infer_ms": round(elapsed * 1000),
                "text": text,
                "flags": flag_issues(text),
            }
            segments_out.append(entry)
            flag_str = f" [{','.join(entry['flags'])}]" if entry["flags"] else ""
            print(f"[{elapsed_since_start_s:6.1f}s | {elapsed*1000:5.0f}ms]{flag_str} {text}")

    while pos < n:
        chunk = all_bytes[pos:pos + CHUNK_BYTES]
        pos += CHUNK_BYTES
        buffer.extend(chunk)
        duration = len(buffer) / BYTES_PER_SECOND
        if duration < PARTIAL_MIN_SECONDS:
            continue
        should_finalize = duration >= MAX_CHUNK_SECONDS
        if not should_finalize and duration >= MIN_CHUNK_SECONDS:
            should_finalize = has_trailing_silence(bytes(buffer))
        if should_finalize:
            finalize(bytes(buffer), pos / BYTES_PER_SECOND)
            buffer.clear()

    if len(buffer) / BYTES_PER_SECOND >= PARTIAL_MIN_SECONDS:
        finalize(bytes(buffer), n / BYTES_PER_SECOND)

    report = {
        "model_repo": args.model_repo,
        "device": device_used,
        "load_time_s": round(load_time, 2),
        "vram_before_mb": vram_before,
        "vram_after_load_mb": vram_after_load,
        "vram_model_delta_mb": vram_after_load - vram_before,
        "vram_peak_mb": peak_vram,
        "audio_duration_s": round(audio_duration, 1),
        "total_infer_time_s": round(total_infer_time, 2),
        "realtime_factor": round(total_infer_time / audio_duration, 4),
        "num_segments": len(segments_out),
        "num_flagged": sum(1 for s in segments_out if s["flags"]),
        "segments": segments_out,
    }
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n=== {args.model_repo} summary ===")
    print(f"device={device_used}  load={load_time:.1f}s  VRAM model delta={report['vram_model_delta_mb']}MiB  peak={peak_vram}MiB")
    print(f"realtime_factor={report['realtime_factor']}  segments={len(segments_out)}  flagged={report['num_flagged']}")


if __name__ == "__main__":
    main()
