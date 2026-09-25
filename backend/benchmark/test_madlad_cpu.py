"""MADLAD-400 3B on CPU (int8), sequential one-sentence-at-a-time (no batching
— matches live production, per the brief). Tracks CPU% and RAM alongside
latency. no_repeat_ngram_size=3 fixed (the calibrated decoding setting).
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, ".")
sys.path.insert(0, "benchmark")

import os
import time
import psutil

import ctranslate2
import opencc
import sentencepiece as spm
from huggingface_hub import snapshot_download
from translation_dataset import DATASET

proc = psutil.Process()
proc.cpu_percent()  # prime the counter (first call always returns 0)

print("Loading MADLAD (CPU, int8)...")
t0 = time.monotonic()
model_dir = snapshot_download("Heng666/madlad400-3b-mt-ct2-int8")
sp = spm.SentencePieceProcessor()
sp.load(os.path.join(model_dir, "spiece.model"))
translator = ctranslate2.Translator(model_dir, device="cpu", compute_type="int8")
load_time = time.monotonic() - t0
ram_after_load_mb = proc.memory_info().rss / 1e6
print(f"Loaded in {load_time:.1f}s. RAM (process RSS): {ram_after_load_mb:.0f} MB. "
      f"Logical CPUs: {psutil.cpu_count()}")

converter = opencc.OpenCC("s2twp")
results = []
cpu_samples = []
for entry in DATASET:
    source = sp.encode(f"<2zh> {entry['ja']}", out_type=str)
    t1 = time.monotonic()
    result = translator.translate_batch([source], beam_size=4, no_repeat_ngram_size=3)
    raw = sp.decode(result[0].hypotheses[0])
    elapsed_ms = (time.monotonic() - t1) * 1000
    cpu_pct = proc.cpu_percent()  # % since last call, can exceed 100 (multi-core)
    cpu_samples.append(cpu_pct)
    opencc_out = converter.convert(raw)
    results.append({"id": entry["id"], "latency_ms": elapsed_ms, "cpu_pct": cpu_pct})
    print(f"[{entry['id']}] {elapsed_ms:.0f}ms cpu={cpu_pct:.0f}% -> {opencc_out[:30]}")

ram_final_mb = proc.memory_info().rss / 1e6
lat = [r["latency_ms"] for r in results]
lat_sorted = sorted(lat)
n = len(lat_sorted)
print(f"\n=== MADLAD CPU summary ===")
print(f"Load time: {load_time:.1f}s")
print(f"RAM after load: {ram_after_load_mb:.0f} MB, RAM final: {ram_final_mb:.0f} MB "
      f"(delta {ram_final_mb - ram_after_load_mb:.0f} MB)")
print(f"Sentences: {n}")
print(f"Avg latency: {sum(lat)/n:.0f}ms")
print(f"P50: {lat_sorted[n//2]:.0f}ms")
print(f"P95: {lat_sorted[min(int(n*0.95), n-1)]:.0f}ms")
print(f"Max: {max(lat):.0f}ms")
print(f"Avg CPU%% (of one core's worth; system has {psutil.cpu_count()} logical cores): "
      f"{sum(cpu_samples)/len(cpu_samples):.0f}%")
print(f"Peak CPU%%: {max(cpu_samples):.0f}%")
