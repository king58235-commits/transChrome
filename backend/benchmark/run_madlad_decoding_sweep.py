"""MADLAD-400 3B decoding-parameter sweep: does repetition_penalty /
no_repeat_ngram_size / max_decoding_length fix the short-utterance repetition
loops seen in the baseline run? Loads MADLAD ONCE (model doesn't change,
only decoding kwargs do) and runs the full 70-sentence dataset once per
config. Does NOT touch the production pipeline.
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, ".")
sys.path.insert(0, "benchmark")

import importlib.util
import json
import os
import re
import subprocess
import time

if sys.platform == "win32":
    spec = importlib.util.find_spec("nvidia")
    if spec and spec.submodule_search_locations:
        dirs = []
        for base in spec.submodule_search_locations:
            for pkg in ("cublas", "cudnn", "cuda_nvrtc"):
                bin_dir = os.path.join(base, pkg, "bin")
                if os.path.isdir(bin_dir):
                    dirs.append(bin_dir)
                    os.add_dll_directory(bin_dir)
        if dirs:
            os.environ["PATH"] = os.pathsep.join(dirs) + os.pathsep + os.environ.get("PATH", "")

import ctranslate2
import opencc
import sentencepiece as spm
from huggingface_hub import snapshot_download
from translation_dataset import DATASET

REPO = "Heng666/madlad400-3b-mt-ct2-int8"
TGT_TOKEN = "<2zh>"

TRACKED_IDS = {"E01", "E02", "E05", "CASE1", "CASE2", "CASE3", "CASE4", "CASE5"}
# うわー/え？/おっ/うん map to E01/E02/E05/(no "うん" in dataset — add ad hoc below)
EXTRA_TRACKED = [{"id": "EXTRA_un", "category": "E_short", "ja": "うん",
                  "ref": "嗯", "stt_uncertain": False}]


def gpu_mem_mb():
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True,
    ).stdout.strip()
    return int(out.splitlines()[0])


_repeat_re = re.compile(r"(.{1,4}?)\1{2,}")  # a short chunk (1-4 chars) repeated 3+ times


def count_repetition(text):
    """Returns (loop_count, is_catastrophic). A 'loop' is a chunk of 1-4
    chars immediately repeated 3+ times (e.g. "哇，哇，哇" or "哈"x50).
    Catastrophic = any single repeated run of 10+."""
    matches = _repeat_re.findall(text)
    max_run = 0
    for m in re.finditer(_repeat_re, text):
        run_text = m.group(0)
        chunk = m.group(1)
        run_len = len(run_text) // max(len(chunk), 1)
        max_run = max(max_run, run_len)
    return len(matches), max_run >= 10


CONFIGS = [
    {"name": "A_baseline", "kwargs": dict(beam_size=4)},
    {"name": "B_rep1.05", "kwargs": dict(beam_size=4, repetition_penalty=1.05)},
    {"name": "B_rep1.10", "kwargs": dict(beam_size=4, repetition_penalty=1.10)},
    {"name": "B_rep1.20", "kwargs": dict(beam_size=4, repetition_penalty=1.20)},
    {"name": "C_noRepeat2", "kwargs": dict(beam_size=4, no_repeat_ngram_size=2)},
    {"name": "C_noRepeat3", "kwargs": dict(beam_size=4, no_repeat_ngram_size=3)},
    {"name": "D_maxlen_dynamic", "kwargs": dict(beam_size=4), "dynamic_max_len": True},
]


def main():
    print(f"Loading MADLAD tokenizer + model from {REPO} ...")
    t0 = time.monotonic()
    model_dir = snapshot_download(REPO)
    sp = spm.SentencePieceProcessor()
    sp.load(os.path.join(model_dir, "spiece.model"))

    vram_before = gpu_mem_mb()
    translator = ctranslate2.Translator(model_dir, device="cuda", compute_type="int8_float16")
    vram_after_load = gpu_mem_mb()
    print(f"Loaded in {time.monotonic()-t0:.1f}s. VRAM: {vram_before} -> {vram_after_load} MiB")

    converter = opencc.OpenCC("s2twp")
    dataset = DATASET + EXTRA_TRACKED

    all_results = {}
    for cfg in CONFIGS:
        print(f"\n=== Config: {cfg['name']} ({cfg['kwargs']}) ===")
        results = []
        vram_peak = vram_after_load
        for entry in dataset:
            source = sp.encode(f"{TGT_TOKEN} {entry['ja']}", out_type=str)
            kwargs = dict(cfg["kwargs"])
            if cfg.get("dynamic_max_len"):
                kwargs["max_decoding_length"] = max(16, len(source) * 4)

            t1 = time.monotonic()
            error = None
            raw = ""
            try:
                res = translator.translate_batch([source], **kwargs)
                raw = sp.decode(res[0].hypotheses[0])
            except Exception as e:
                error = str(e)
            elapsed_ms = (time.monotonic() - t1) * 1000
            opencc_out = converter.convert(raw) if raw else ""
            vram_peak = max(vram_peak, gpu_mem_mb())

            loop_count, catastrophic = count_repetition(opencc_out)
            degenerate = (not opencc_out.strip()) or bool(re.fullmatch(r"[,，。.\s]+", opencc_out or ""))

            entry_result = {
                "id": entry["id"], "category": entry["category"], "ja_source": entry["ja"],
                "reference_zh_tw": entry["ref"], "stt_uncertain": entry["stt_uncertain"],
                "opencc_output": opencc_out, "latency_ms": round(elapsed_ms, 1),
                "loop_count": loop_count, "catastrophic": catastrophic, "degenerate": degenerate,
                "error": error,
            }
            results.append(entry_result)
            if entry["id"] in TRACKED_IDS or entry["id"] == "EXTRA_un":
                flag = " [LOOP]" if loop_count else ""
                flag += " [CATASTROPHIC]" if catastrophic else ""
                flag += " [DEGENERATE]" if degenerate else ""
                print(f"  [{entry['id']}]{flag} ({elapsed_ms:.0f}ms) {entry['ja'][:15]} -> {opencc_out[:50]}")

        lat = [r["latency_ms"] for r in results if not r["error"]]
        lat_sorted = sorted(lat)
        n = len(lat_sorted)
        summary = {
            "config": cfg["name"], "kwargs": {k: v for k, v in cfg["kwargs"].items()},
            "dynamic_max_len": cfg.get("dynamic_max_len", False),
            "avg_latency_ms": round(sum(lat) / n, 1) if n else 0,
            "p95_latency_ms": lat_sorted[min(int(n * 0.95), n - 1)] if n else 0,
            "total_loops": sum(r["loop_count"] for r in results),
            "sentences_with_loops": sum(1 for r in results if r["loop_count"] > 0),
            "catastrophic_count": sum(1 for r in results if r["catastrophic"]),
            "degenerate_count": sum(1 for r in results if r["degenerate"]),
            "vram_peak_mb": vram_peak,
        }
        print(f"  Summary: loops={summary['sentences_with_loops']}/{len(results)} "
              f"catastrophic={summary['catastrophic_count']} degenerate={summary['degenerate_count']} "
              f"avg_latency={summary['avg_latency_ms']}ms")
        all_results[cfg["name"]] = {"summary": summary, "results": results}

    with open("benchmark/madlad_decoding_sweep.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print("\nSaved benchmark/madlad_decoding_sweep.json")


if __name__ == "__main__":
    main()
