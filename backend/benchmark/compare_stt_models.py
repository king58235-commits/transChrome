"""Compare STT models on recorded sessions (SAVE_SESSION_AUDIO wavs).

Splits each recording into speech chunks with the production pause detection
(same as test_stt_hotwords.py), transcribes every chunk with each model using
the production final settings, and writes a side-by-side text file plus a
speed/VRAM summary. Offline, not real-time. Does NOT touch the production
pipeline; models other than the configured one are downloaded on first use.

Usage (from backend/):
    venv\\Scripts\\python.exe benchmark\\compare_stt_models.py <out.txt> <wav> [<wav> ...]
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, ".")
sys.path.insert(0, "benchmark")

import subprocess
import time
import wave

import numpy as np

import transcriber  # registers the NVIDIA DLL dirs before faster_whisper loads
from config import SAMPLE_RATE, STT_MODEL_PRESETS, WHISPER_LANGUAGE
from faster_whisper import WhisperModel
from test_stt_hotwords import chunks

MODELS = {
    "kotoba": STT_MODEL_PRESETS["kotoba"],
    "turbo": "large-v3-turbo",
    # CT2 conversion of litagin/anime-whisper (kotoba fine-tuned on galgame
    # dialogue). 09-26 test: worse than kotoba on stream audio (adds …/あはは,
    # stutters, more misheard words), not adopted.
    "anime": "quantumcookie/anime-whisper-ct2",
}


def gpu_mb():
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True).stdout
    return int(out.split()[0])


def load_chunks(path):
    wav = wave.open(path, "rb")
    audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    return [c for c in chunks(audio) if len(c) >= SAMPLE_RATE // 2]


def main():
    out_path, wavs = sys.argv[1], sys.argv[2:]
    parts = [(w, i, c) for w in wavs for i, c in enumerate(load_chunks(w))]
    audio_s = sum(len(c) for _, _, c in parts) / SAMPLE_RATE
    print(f"{len(parts)} chunks, {audio_s:.0f}s of speech")

    texts, summary = {}, []
    for name, repo in MODELS.items():
        before = gpu_mb()
        model = WhisperModel(repo, device="cuda", compute_type="float16")
        loaded = gpu_mb()
        out, t0 = [], time.monotonic()
        for _, _, c in parts:
            segments, _ = model.transcribe(c, language=WHISPER_LANGUAGE, **transcriber.FINAL_KWARGS)
            out.append("".join(s.text for s in segments).strip())
        elapsed = time.monotonic() - t0
        texts[name] = out
        summary.append(f"{name}: {elapsed:.1f}s for {audio_s:.0f}s speech (RTF {elapsed/audio_s:.3f}), "
                       f"avg {elapsed/len(parts)*1000:.0f}ms/chunk, VRAM +{loaded-before} MiB")
        print(summary[-1])
        del model

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(summary) + "\n\n")
        for k, (w, i, _) in enumerate(parts):
            f.write(f"[{w.split('/')[-1]} #{i}]\n")
            for name in MODELS:
                f.write(f"  {name:6s}: {texts[name][k]}\n")
    print(f"written {out_path}")


if __name__ == "__main__":
    main()
