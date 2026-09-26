# Sakura-7B selection and follow-up experiments (2026-09-26)

Test machine: RTX 4070 Ti 12GB, llama.cpp b11200 (Windows CUDA 12.4 build),
greedy decoding (temperature 0) for every model. The raw per-sentence outputs
lived in a temporary folder and were not kept; this file is the summary.

## 1. Translation model benchmark

Dataset: the two fixed sets in this folder (`translation_dataset.py`, 65
sentences without the duplicated CASE rows, and `translation_dataset_live.py`,
70 live units including every MADLAD failure), each sentence in two modes:
raw (no glossary) and glossary-assisted (production pre/post-processing).
Meaning accuracy was judged by hand by one rater, excluding STT-uncertain rows
and rows answered by the fixed-utterance table.

Latency gate (14 representative sentences):

| Model | Avg | P95 | Max | TTFT | Result |
|---|---|---|---|---|---|
| MADLAD-400 3B int8 (baseline) | 705ms | 1191ms | 1260ms | n/a (beam) | baseline |
| Sakura-1.5B fp16 | 136ms | 268ms | 291ms | 15ms | pass |
| Sakura-7B iq4xs | 177ms | 367ms | 375ms | 22ms | pass |
| Qwen2.5-7B-Instruct q4_k_m | 221ms | 447ms | 457ms | 22ms | pass |

Full run (135 sentences x 2 modes):

| | MADLAD 3B | Sakura-1.5B | **Sakura-7B** | Qwen2.5-7B |
|---|---|---|---|---|
| Meaning OK, general set | 19/48 | 40/48 | **42/48** | 35/48 |
| Meaning OK, MADLAD failure cases | ~1/26 | 20/26 | **21/26** | 12/26 |
| Unwanted output | 0 | 1 runaway repetition | **0** | 8 garbage-token outputs |
| Avg / P95 latency | 507 / 839ms | 101 / 189ms | 110 / 241ms | 129 / 302ms |
| VRAM | 3.6GB | 3.3GB | 4.2GB | 4.6GB |

Decision: Sakura-7B (`SakuraLLM/Sakura-7B-Qwen2.5-v1.0-GGUF`, iq4xs).
TranslateGemma 4B was dropped before testing (gated model, not pursued).
License note: Sakura models are CC BY-NC-SA 4.0 (no commercial use).

## 2. Member names (`test_sakura_names.py`)

Every glossary member in 3 sentences (259): names replaced with Chinese inside
the Japanese text (the MADLAD method) 203/259, names passed as Sakura
glossary-prompt entries 240/259, no glossary 26/259. Replacing in the text made
Sakura translate the name as a word (白上フブキ -> 吹雪 -> "暴風雪").

## 3. Fan names

Japanese fan names given as glossary entries survived 6-8 of 14 (すこん部 ->
"斯空部"); swapped for FAN1, FAN2... placeholders and restored after
translation, 16 of 17. Production uses placeholders.

## 4. Context experiments (not adopted)

Units of 6 live sessions (257 with a previous unit):

| Variant | Problem | Latency median / P95 |
|---|---|---|
| Single sentence (production) | - | 106 / 250ms |
| Previous 3 units as chat history | ~10% output the previous line's translation | 110 / 250ms |
| Previous 3 units as a "reference" block | 35% also translated the reference | 154 / 468ms |
| Previous 1-2 units + current translated as lines, last line kept | ~15 better / ~15 worse of 120 changed; errors spread when STT misheard several lines in a row | 187-266 / 410-510ms |

Decision: keep single-sentence translation.
