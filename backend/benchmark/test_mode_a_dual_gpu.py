"""Mode A test: Kotoba GPU + MADLAD GPU loaded simultaneously. If this OOMs
on the RTX 3050 8GB, record exactly where and at what VRAM — do NOT attempt
any workaround (no quantization change, no closing other apps)."""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, ".")
sys.path.insert(0, "benchmark")

import importlib.util
import os
import subprocess

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
        ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
        capture_output=True, text=True,
    ).stdout.strip()
    used, total = out.split(",")
    return int(used), int(total)


used, total = gpu_mem_mb()
print(f"Step 0 - baseline (nothing loaded): {used}/{total} MiB")

import transcriber
print("\nStep 1 - loading Kotoba-whisper on GPU...")
try:
    transcriber.load_model()
    used, total = gpu_mem_mb()
    print(f"Step 1 OK - Kotoba loaded: {used}/{total} MiB")
except Exception as e:
    used, total = gpu_mem_mb()
    print(f"Step 1 FAILED at {used}/{total} MiB: {e}")
    sys.exit(1)

print("\nStep 2 - loading MADLAD-400 3B on GPU (on top of Kotoba)...")
import ctranslate2
from huggingface_hub import snapshot_download

try:
    model_dir = snapshot_download("Heng666/madlad400-3b-mt-ct2-int8")
    used, total = gpu_mem_mb()
    print(f"  (model downloaded/cached, VRAM unchanged: {used}/{total} MiB)")
    madlad = ctranslate2.Translator(model_dir, device="cuda", compute_type="int8_float16")
    used, total = gpu_mem_mb()
    print(f"Step 2 OK - MADLAD loaded: {used}/{total} MiB")

    print("\nStep 3 - running one real translation to confirm actual inference works (not just allocation)...")
    import sentencepiece as spm
    sp = spm.SentencePieceProcessor()
    sp.load(os.path.join(model_dir, "spiece.model"))
    source = sp.encode("<2zh> テスト", out_type=str)
    result = madlad.translate_batch([source], beam_size=4, no_repeat_ngram_size=3)
    text = sp.decode(result[0].hypotheses[0])
    used, total = gpu_mem_mb()
    print(f"Step 3 OK - inference result: {text!r}. VRAM: {used}/{total} MiB")
    print("\n=== MODE A: BOTH MODELS LOADED AND WORKING SIMULTANEOUSLY ===")
except Exception as e:
    used, total = gpu_mem_mb()
    print(f"Step 2/3 FAILED at {used}/{total} MiB")
    print(f"Exception type: {type(e).__name__}")
    print(f"Exception message: {e}")
    print("\n=== MODE A: FAILED (see above for exact failure point and VRAM) ===")
