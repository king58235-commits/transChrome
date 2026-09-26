"""Translation-side regression check on the live-session set
(translation_dataset_live.py) plus the original 71-sentence set
(translation_dataset.py), for trying MADLAD decoding changes offline.

Uses translator.py itself (same model, device, tokenizer, OpenCC, glossary
and production decoding kwargs), so the "production" config here is exactly what
the live backend ran. Other configs only add/override decoding kwargs.
Does NOT touch the production pipeline.

Usage (from backend/, with the live backend stopped to free VRAM):
    venv\\Scripts\\python.exe benchmark\\run_live_regression.py [config ...]
With no args, runs "live_0926" (must reproduce the live output 70/70) and "production".
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, ".")
sys.path.insert(0, "benchmark")

import json
import math
import time

import glossary
import translator  # registers the NVIDIA DLL dirs before ctranslate2 loads
from config import (
    TRANSLATION_BEAM_SIZE,
    TRANSLATION_DROP_REPEATED_CLAUSES,
    TRANSLATION_LENGTH_PENALTY,
    TRANSLATION_NO_REPEAT_NGRAM_SIZE,
    TRANSLATION_TGT_TOKEN,
)
from translation_dataset import DATASET
from translation_dataset_live import LIVE_DATASET

PRODUCTION_KWARGS = dict(
    beam_size=TRANSLATION_BEAM_SIZE,
    no_repeat_ngram_size=TRANSLATION_NO_REPEAT_NGRAM_SIZE,
    length_penalty=TRANSLATION_LENGTH_PENALTY,
)

# Length limit = ceil(src_tokens * ratio) + offset, where src_tokens excludes
# the target-language token. Measured on the production output: acceptable
# translations stay at <= ~1.33x, padded/duplicated ones median ~1.86x.
#   hard_cap: pass the limit as max_decoding_length (truncates mid-sentence).
#   nbest:    ask beam search for all beam_size finished hypotheses and take
#             the best-scored one within the limit (falls back to the top one),
#             so the output is always a complete sentence.
CONFIGS = {
    "production": {},
    # decoding the 2026-09-26 live session actually ran (before length_penalty=0.5)
    "live_0926": {"kwargs": {"length_penalty": 1.0}, "glossary": False, "dedup": False},
    "no_dedup": {"dedup": False},
    "no_glossary": {"glossary": False},
    "hard_cap_1.5": {"hard_cap": (1.5, 2)},
    "nbest_1.5": {"nbest": (1.5, 2)},
    "nbest_1.3": {"nbest": (1.3, 2)},
    "lenpen_0": {"kwargs": {"length_penalty": 0.0}},
    "lenpen_0.5": {"kwargs": {"length_penalty": 0.5}},
    "lenpen_0.5_nbest_1.5": {"kwargs": {"length_penalty": 0.5}, "nbest": (1.5, 2)},
    "lenpen_0_nbest_1.5": {"kwargs": {"length_penalty": 0.0}, "nbest": (1.5, 2)},
}


def run_one(tr, sp, conv, ja, cfg):
    if cfg.get("glossary", True):  # production applies these too (translator.translate)
        fixed = glossary.fixed(ja)
        if fixed is not None:
            return {"zh": fixed, "src_tokens": 0, "out_tokens": 0, "ms": 0.0}
        ja = glossary.apply(ja)
    source = sp.encode(f"{TRANSLATION_TGT_TOKEN} {ja}", out_type=str)
    src_len = len(source) - 1
    kw = dict(PRODUCTION_KWARGS, **cfg.get("kwargs", {}))
    if "hard_cap" in cfg:
        ratio, offset = cfg["hard_cap"]
        kw["max_decoding_length"] = math.ceil(src_len * ratio) + offset
    if "nbest" in cfg:
        kw["num_hypotheses"] = kw["beam_size"]
    t0 = time.monotonic()
    hyps = tr.translate_batch([source], **kw)[0].hypotheses
    ms = (time.monotonic() - t0) * 1000
    hyp = hyps[0]
    if "nbest" in cfg:
        ratio, offset = cfg["nbest"]
        limit = math.ceil(src_len * ratio) + offset
        hyp = next((h for h in hyps if len(h) <= limit), hyps[0])
    zh = conv.convert(sp.decode(hyp))
    if cfg.get("dedup", TRANSLATION_DROP_REPEATED_CLAUSES):  # production applies this too
        zh = translator.drop_repeated_clauses(zh)
    return {"zh": zh, "src_tokens": src_len, "out_tokens": len(hyp), "ms": round(ms, 1)}


def main():
    names = sys.argv[1:] or ["live_0926", "production"]
    unknown = [n for n in names if n not in CONFIGS]
    if unknown:
        sys.exit(f"Unknown config(s): {unknown}. Known: {list(CONFIGS)}")

    translator.load_model()
    tr, sp, conv = translator._translator, translator._sp, translator._converter

    out = {}
    for name in names:
        cfg = CONFIGS[name]
        print(f"\n=== {name}  {cfg} ===")
        live = [dict(id=d["id"], ja=d["ja"], **run_one(tr, sp, conv, d["ja"], cfg)) for d in LIVE_DATASET]
        base = [dict(id=d["id"], ja=d["ja"], **run_one(tr, sp, conv, d["ja"], cfg)) for d in DATASET]
        out[name] = {"live": live, "original": base}

        same = sum(r["zh"] == d["baseline_zh"] for r, d in zip(live, LIVE_DATASET))
        print(f"live set: {same}/{len(live)} identical to the live-session output")
        for r, d in zip(live, LIVE_DATASET):
            if r["zh"] != d["baseline_zh"]:
                print(f"  [{r['id']}] {r['ja']}\n     live: {d['baseline_zh']}\n     now : {r['zh']}")
        lat = sorted(r["ms"] for r in live + base)
        print(f"latency avg={sum(lat)/len(lat):.0f}ms p95={lat[int(len(lat)*0.95)]:.0f}ms")

    with open("benchmark/live_regression.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\nSaved benchmark/live_regression.json")


if __name__ == "__main__":
    main()
