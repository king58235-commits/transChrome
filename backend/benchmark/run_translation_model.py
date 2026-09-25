"""Stage 2B translation model benchmark: runs the fixed 70-sentence dataset
through ONE translation model (NLLB-style tokenizer+prefix, or MADLAD-style
sentencepiece+prompt), records raw + OpenCC output, latency, VRAM.

Only one model loaded per process run (by design — see brief) for clean VRAM
comparisons. Does NOT touch the production Kotoba+NLLB pipeline at all.

Usage:
    venv\\Scripts\\python.exe benchmark\\run_translation_model.py <config_name> <out_json>

config_name is one of: nllb600m, nllb1_3b, madlad3b
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
import subprocess
import time

# --- CUDA DLL path registration (same fix as transcriber.py/translator.py) ---
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
from huggingface_hub import snapshot_download
from translation_dataset import DATASET

MODEL_CONFIGS = {
    "nllb600m": {
        "type": "nllb",
        "repo": "JustFrederik/nllb-200-distilled-600M-ct2-float16",
        "compute_type": "float16",
        "src_lang": "jpn_Jpan",
        "tgt_lang": "zho_Hans",
    },
    "nllb1_3b": {
        "type": "nllb",
        "repo": "JustFrederik/nllb-200-distilled-1.3B-ct2-float16",
        "compute_type": "float16",
        "src_lang": "jpn_Jpan",
        "tgt_lang": "zho_Hans",
    },
    "madlad3b": {
        "type": "madlad",
        "repo": "Heng666/madlad400-3b-mt-ct2-int8",
        "compute_type": "int8_float16",
        "tgt_token": "<2zh>",
    },
}


def gpu_mem_mb():
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True,
    ).stdout.strip()
    return int(out.splitlines()[0])


def load_nllb(cfg):
    from transformers import AutoTokenizer
    model_dir = snapshot_download(cfg["repo"])
    tokenizer = AutoTokenizer.from_pretrained(model_dir, src_lang=cfg["src_lang"])

    def translate_one(translator, text):
        source = tokenizer.convert_ids_to_tokens(tokenizer.encode(text))
        results = translator.translate_batch([source], target_prefix=[[cfg["tgt_lang"]]])
        target_tokens = results[0].hypotheses[0][1:]
        target_ids = tokenizer.convert_tokens_to_ids(target_tokens)
        return tokenizer.decode(target_ids, skip_special_tokens=True)

    return model_dir, translate_one


def load_madlad(cfg):
    import sentencepiece as spm
    model_dir = snapshot_download(cfg["repo"])
    sp = spm.SentencePieceProcessor()
    sp.load(os.path.join(model_dir, "spiece.model"))

    def translate_one(translator, text):
        prompt = f"{cfg['tgt_token']} {text}"
        source = sp.encode(prompt, out_type=str)
        results = translator.translate_batch([source], beam_size=4)
        target_tokens = results[0].hypotheses[0]
        return sp.decode(target_tokens)

    return model_dir, translate_one


def main():
    config_name = sys.argv[1]
    out_path = sys.argv[2]
    cfg = MODEL_CONFIGS[config_name]

    print(f"=== Benchmarking {config_name}: {cfg['repo']} ===")
    vram_before = gpu_mem_mb()
    print(f"VRAM before load: {vram_before} MiB")

    t0 = time.monotonic()
    if cfg["type"] == "nllb":
        model_dir, translate_one = load_nllb(cfg)
    else:
        model_dir, translate_one = load_madlad(cfg)
    load_time = time.monotonic() - t0

    device_used = "cuda"
    try:
        translator = ctranslate2.Translator(model_dir, device="cuda", compute_type=cfg["compute_type"])
        translate_one(translator, "テスト")  # warm-up + catch CUDA runtime issues early
    except Exception as e:
        print(f"CUDA failed ({e}), falling back to CPU", file=sys.stderr)
        translator = ctranslate2.Translator(model_dir, device="cpu", compute_type="int8")
        device_used = "cpu"

    vram_after_load = gpu_mem_mb()
    print(f"Loaded on {device_used} in {load_time:.1f}s. VRAM after load: {vram_after_load} MiB "
          f"(delta {vram_after_load - vram_before} MiB)")

    converter = opencc.OpenCC("s2twp")

    results = []
    vram_peak = vram_after_load
    for entry in DATASET:
        t1 = time.monotonic()
        error = None
        raw = ""
        try:
            raw = translate_one(translator, entry["ja"])
        except Exception as e:
            error = str(e)
        elapsed_ms = (time.monotonic() - t1) * 1000
        opencc_out = converter.convert(raw) if raw else ""
        vram_peak = max(vram_peak, gpu_mem_mb())

        results.append({
            "id": entry["id"],
            "category": entry["category"],
            "ja_source": entry["ja"],
            "reference_zh_tw": entry["ref"],
            "stt_uncertain": entry["stt_uncertain"],
            "model": config_name,
            "raw_output": raw,
            "opencc_output": opencc_out,
            "latency_ms": round(elapsed_ms, 1),
            "error": error,
        })
        flag = " [ERR]" if error else ""
        print(f"[{entry['id']}] ({elapsed_ms:.0f}ms){flag} {entry['ja'][:20]} -> {opencc_out[:40]}")

    latencies = [r["latency_ms"] for r in results if not r["error"]]
    latencies_sorted = sorted(latencies)
    n = len(latencies_sorted)

    def pct(p):
        return latencies_sorted[min(int(n * p), n - 1)] if n else 0

    summary = {
        "config_name": config_name,
        "repo": cfg["repo"],
        "device": device_used,
        "compute_type": cfg["compute_type"],
        "load_time_s": round(load_time, 1),
        "vram_before_mb": vram_before,
        "vram_after_load_mb": vram_after_load,
        "vram_model_delta_mb": vram_after_load - vram_before,
        "vram_peak_mb": vram_peak,
        "num_sentences": len(results),
        "num_errors": sum(1 for r in results if r["error"]),
        "avg_latency_ms": round(sum(latencies) / n, 1) if n else 0,
        "p50_latency_ms": pct(0.50),
        "p95_latency_ms": pct(0.95),
        "max_latency_ms": max(latencies) if latencies else 0,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, ensure_ascii=False, indent=2)

    print("\n=== SUMMARY ===")
    for k, v in summary.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
