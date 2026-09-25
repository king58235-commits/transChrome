"""Mode A full run: Kotoba GPU + MADLAD GPU both loaded, run the full
translation dataset through MADLAD (no_repeat_ngram_size=3) while Kotoba
sits loaded in the same process (simulating both being resident, as in
production), to get real latency/VRAM-peak numbers under this configuration.
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


def gpu_mem_mb():
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True,
    ).stdout.strip()
    return int(out.splitlines()[0])


import transcriber
import ctranslate2
import opencc
import sentencepiece as spm
from huggingface_hub import snapshot_download
from translation_dataset import DATASET

print(f"VRAM baseline: {gpu_mem_mb()} MiB")
transcriber.load_model()
print(f"VRAM after Kotoba load: {gpu_mem_mb()} MiB")

model_dir = snapshot_download("Heng666/madlad400-3b-mt-ct2-int8")
sp = spm.SentencePieceProcessor()
sp.load(os.path.join(model_dir, "spiece.model"))
madlad = ctranslate2.Translator(model_dir, device="cuda", compute_type="int8_float16")
vram_after_both = gpu_mem_mb()
print(f"VRAM after MADLAD load (both resident): {vram_after_both} MiB")

converter = opencc.OpenCC("s2twp")
vram_peak = vram_after_both
latencies = []
for entry in DATASET:
    source = sp.encode(f"<2zh> {entry['ja']}", out_type=str)
    t0 = time.monotonic()
    result = madlad.translate_batch([source], beam_size=4, no_repeat_ngram_size=3)
    raw = sp.decode(result[0].hypotheses[0])
    elapsed_ms = (time.monotonic() - t0) * 1000
    latencies.append(elapsed_ms)
    vram_peak = max(vram_peak, gpu_mem_mb())

lat_sorted = sorted(latencies)
n = len(lat_sorted)
print(f"\n=== Mode A (Kotoba GPU + MADLAD GPU, both resident) translation stats ===")
print(f"Sentences: {n}")
print(f"Avg latency: {sum(latencies)/n:.1f}ms")
print(f"P50: {lat_sorted[n//2]:.1f}ms")
print(f"P95: {lat_sorted[min(int(n*0.95), n-1)]:.1f}ms")
print(f"Max: {max(latencies):.1f}ms")
print(f"VRAM after load: {vram_after_both} MiB")
print(f"VRAM peak during inference: {vram_peak} MiB")
print(f"VRAM total: 8192 MiB, headroom: {8192 - vram_peak} MiB")
