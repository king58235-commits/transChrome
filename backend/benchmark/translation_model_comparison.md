# Stage 2B Translation Model Benchmark

Fixed 70-sentence dataset (`translation_dataset.py`), same 5-category split (A general / B casual-elliptical / C katakana-loanword / D long-transition / E interjection) plus 5 explicitly tracked known-failure cases. Each model loaded alone (production Kotoba+NLLB pipeline stopped during this benchmark, restarted after — **not modified**). Raw model output → OpenCC `s2twp` for all three, for a fair comparison.

## Comparison table

| Model | Meaning Accuracy | Omission | Hallucination | Katakana/Terms | Casual JA | Short Utterance | Fluency | Avg Latency | VRAM (delta/peak) |
|---|---|---|---|---|---|---|---|---|---|
| **NLLB 600M** (baseline) | Medium | **High** — regularly drops the second half of long/transition sentences | Low, but not zero (1 repetition case: D03) | Poor — katakana loanwords ("ダンジョン"→"丹") and proper nouns often mistranslated | Medium | Poor — gets the *meaning* of short exclamations wrong (not garbled, just wrong) | High — always grammatically clean | 108ms | 1868 / 4826 MiB |
| **NLLB 1.3B** | Medium (not clearly better than 600M) | High (same pattern as 600M) | **Medium** — 2 cases degenerated into pure `,,,,,,,` output | Poor-Medium, no clear improvement | Medium | Poor, similar to 600M | High | 198ms (~2x) | 3865 / 6872 MiB (~2x) |
| **MADLAD-400 3B** (int8) | **Medium-High** — clearly best on long/transition sentences | **Low** — the one model that preserved a full but/however transition (CASE4) | **High** — frequent repetition loops, one catastrophic 50x-repeat case (D08) | Medium-Good — got "dungeon"→"地牢" right where both NLLB models failed | Medium | **Very Poor** — loops on short/simple inputs specifically (worse UX than "just wrong") | Medium — loops actively hurt readability | 422ms (~4x) | 4208 / 7222 MiB (~2.3x) |

**Critical VRAM finding**: production Kotoba-whisper alone uses ~2.1GB. Adding NLLB 1.3B (+3.9GB) or MADLAD 3B (+4.2GB) would push combined usage to ~9-9.5GB on an **8GB card — over budget** even before accounting for background app usage (~3GB baseline observed). Neither upgrade candidate fits alongside the current STT model without other changes, independent of the quality findings below.

## Known failure cases (as given)

| Case | JA | Reference | 600M | 1.3B | MADLAD 3B |
|---|---|---|---|---|---|
| 1 | ダンジョンから出たくない気持ちもある | 也有不想離開地下城的心情 | 我不願意離開**丹** ❌ | 我覺得自己不想離開**牢房** ❌ | 有時候我不想離開**地牢** ✅ |
| 2 | あったかいめしあったかい風呂 | 熱騰騰的飯、熱騰騰的澡 | 水很熱,很熱 ❌ (drops 飯) | `,,,,,,,,,,,,,,` ❌❌ (degenerate) | 溫暖舒適的溫暖的浴室 △ (still drops 飯, but not degenerate) |
| 3 | うわー | 哇！ | ,我知道 ❌ | 沒有人知道 ❌ | 哇，哇，哇，哇，哇，哇 △ (right word, loops) |
| 4 | 長い旅路だったようで今思い返すと短かったかも | 感覺是一段很長的旅程，但現在回想起來，也許其實很短 | 我覺得這是一段漫長的旅程 ❌ (drops 2nd half) | 我覺得這是一段漫長的旅程 ❌ (same) | 看起來是一段漫長的旅程，但回想起來，也許是短暫的 ✅ |
| 5 | てか、こんなに種類あるとこないのかな、ペンライト | 話說，應援棒的種類有這麼多喔 | 光,你知道嗎? ❌ | 現在,我們需要更多的時間 ❌ | 還有，筆燈有這麼多種類嗎？ ✅ |

## Top 5 clearest errors per model

**NLLB 600M**: CASE1 (dungeon→丹), D03 (repeats "我希望我能問你" 3x), CASE2 (drops 飯), E01 (うわー→,我知道), C08 (レッツ→現在,我們要做什麼?)

**NLLB 1.3B**: D08+D09/CASE2 (both degenerate into `,,,,,,,`), A04 (この土地に降り立った → 讓我們來看看, unrelated), C01 (dungeon→牢房), E05 (おっ→沒有人知道)

**MADLAD 3B**: D08 (catastrophic ~50x "哈" repetition loop), E04/E05/E06/E07 (all loop 3-12x on short inputs), A06/A07/A09 (loops even on simple general sentences), C11 (loops on an already-STT-uncertain input)

## Top 5 wins vs. baseline (600M) per model

**NLLB 1.3B**: honestly, none clearly better — outputs are comparable-or-worse across the sample, with the two degenerate comma cases being a net regression.

**MADLAD 3B**: CASE4/D01 (only model to preserve the full but/perhaps transition), C01 (地牢 correct vs. both NLLB wrong), C02/CASE5 (captures 種類/ペンライト/question form, both NLLB lost it), D02 (preserves the full complex sentence better), D10 (preserves more of the long conditional clause)

## Latency / VRAM summary

| Model | Avg | P50 | P95 | Max | Load time | VRAM delta | VRAM peak |
|---|---|---|---|---|---|---|---|
| NLLB 600M | 108ms | 96ms | 219ms | 329ms | 2.7s | 1868 MiB | 4826 MiB |
| NLLB 1.3B | 198ms | 167ms | 375ms | 920ms | 35.0s | 3865 MiB | 6872 MiB |
| MADLAD 3B (int8) | 422ms | 403ms | 721ms | 1520ms | 33.7s | 4208 MiB | 7222 MiB |

## Live-test worthiness (not a final recommendation)

- **NLLB 1.3B**: does not appear worth a live test on its own — no clear quality win over 600M found in this sample, at ~2x latency/VRAM cost, plus two observed degenerate outputs 600M didn't produce.
- **MADLAD 3B**: genuinely better on long/transitional sentences and some katakana/proper-noun cases — the exact categories flagged as weak points for NLLB 600M — but its short-utterance repetition-loop problem is a new, serious failure mode (and a catastrophic one in D08) that would need mitigation (e.g. a repetition penalty / no-repeat-ngram setting, not yet tried) before it's usable as-is. Also currently exceeds available VRAM alongside Kotoba-whisper on this 8GB card.
- **NLLB 600M**: remains the only one that fits VRAM headroom comfortably and never produces a fully degenerate output in this sample; its main weakness (dropping the second half of long sentences, mistranslating loanwords) is consistent and at least predictable.

No model swap has been made — production `config.py` is untouched. Full raw/opencc output for every sentence is in `benchmark/translate_bench_*.json`; this file is the summary.
