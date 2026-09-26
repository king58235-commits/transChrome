# MADLAD-400 3B Decoding Parameter Sweep

Goal: can `ctranslate2.Translator.translate_batch`'s decoding parameters fix the short-utterance repetition-loop problem found in the Stage 2B translation model benchmark, without hurting the long-sentence/katakana quality wins MADLAD showed there? Production pipeline untouched throughout (stopped only to free VRAM for a clean test, restarted after).

Same MADLAD model loaded **once**; only decoding kwargs varied per config (model itself never changes, so no VRAM-comparison concern from reloading). Full 70-sentence dataset + "うん" (requested) run per config = 71 sentences × 7 configs.

## Comparison table

| Setting | Short sentence stability | Repetition (loops/71) | Long sentence quality | Katakana | Latency (avg/P95) | Degenerate outputs | Notes |
|---|---|---|---|---|---|---|---|
| A. Baseline (beam_size=4) | Poor | 14 loops, **2 catastrophic** | Good | Good | 585 / — ms | 0 | Known problem: うわー/おっ/うん all loop |
| B. repetition_penalty=1.05 | Poor-Medium | 9 loops, 2 catastrophic | Good (CASE4 unaffected) | Good | 567 ms | 0 | Barely moves the needle |
| B. repetition_penalty=1.10 | Medium | 6 loops, 0 catastrophic | Good | Good | 572 ms | 0 | Catastrophic case fixed, but loops remain |
| B. repetition_penalty=1.20 | **Good** | **0 loops, 0 catastrophic** | Good (CASE4 unaffected) | Good | 579 ms | 0 | Fixes loops but changes 55/71 outputs — short exclamations get *embellished* ("うわー"→"哇哦，真是太棒了", invents content not in source) |
| C. no_repeat_ngram_size=2 | **Good** | **0 loops, 0 catastrophic** | Good | Good | 584 ms | 0 | Changes 42/71 outputs, mild rewording |
| **C. no_repeat_ngram_size=3** | **Good** | **0 loops, 0 catastrophic** | **Best** | **Best (byte-identical to baseline)** | **549 ms (fastest)** | 0 | **CASE1/CASE4/CASE5 output identical to baseline. D08 (the 50x "哈" catastrophic case) recovered into a real, coherent translation.** Changes 33/71 outputs, all neutral-to-positive rewording, none show degradation |
| D. dynamic max_decoding_length | Poor | 14 loops, 1 catastrophic | Good | Good | 564 ms | 0 | Doesn't address the cause — just caps how long the garbage can get |

## Tracked cases across all 7 settings

| Input | A Baseline | B rep1.05 | B rep1.10 | B rep1.20 | C noRep2 | **C noRep3** | D dynlen |
|---|---|---|---|---|---|---|---|
| うわー (E01) | 哇，哇，哇，哇，哇，哇。**[LOOP]** | 哇，哇，哇，哇。[LOOP] | 哇，哇，哇，哇。[LOOP] | 哇哦，真是太棒了。 | 哦，哇哦。 | 哦，哇哦。 | 哇×6 [LOOP] |
| え？(E02) | 是嗎？是嗎？ | 是嗎？ | 是嗎？ | 是嗎？ | 是嗎？ | 是嗎？ | 是嗎？是嗎？ |
| おっ (E05) | 哦啊×11 **[CATASTROPHIC]** | 哦啊×10 [LOOP] | 哦啊×9 [LOOP] | 哦，噢！ | 哦，噢，哦。 | 哦，噢，哦，哦。 | 哦×8 [LOOP] |
| うん | 是的×4 [LOOP] | 是的，是的，是的。 | 是的，我知道。 | 是的，我知道。 | 是的，我知道。 | 是的，是的。 | 是的×4 [LOOP] |
| CASE1（ダンジョン） | 有時候我不想離開**地牢**。 | 同義 | 同義 | 同義 | 同義 | **完全相同** | 同義 |
| CASE2（めし+風呂） | 溫暖舒適的溫暖的浴室。 | 溫暖舒適的浴室。 | 溫暖舒適的浴室。 | 溫暖舒適的浴室。 | 溫暖舒適的浴室。 | 溫暖舒適的溫暖的浴室。 | 同baseline |
| CASE3（うわー） | 哇×6 [LOOP] | 哇×4 [LOOP] | 哇×4 [LOOP] | 哇哦，真是太棒了。 | 哦，哇哦。 | 哦，哇哦。 | 哇×6 [LOOP] |
| CASE4（長句轉折） | 看起來是一段漫長的旅程，但回想起來，也許是短暫的。 | 同baseline | 同baseline | 同baseline | 看起來這是一段漫長的旅程，但回頭看來也許是短暫的。 | **完全相同** | 同baseline |
| CASE5（ペンライト） | 還有，筆燈有這麼多種類嗎？ | 同baseline | 同baseline | 另外，筆燈有這麼多種類嗎？ | 同baseline | **完全相同** | 同baseline |
| D08（50x「哈」災難案例） | 哈×50 **[CATASTROPHIC]** | — | — | — | — | **波波羅也很高興收到這麼多的錢。**（恢復成正常翻譯） | — |

## 直接回答四個問題

**1. 是否有某組設定能明顯壓掉 repetition loop？**
有，三組：`repetition_penalty=1.20`、`no_repeat_ngram_size=2`、`no_repeat_ngram_size=3` 都做到 71 句裡 **0 次 loop、0 次 catastrophic、0 次 degenerate**。原本的 50 次「哈」災難案例（D08），用 `no_repeat_ngram_size=3` 不只不再重複，還恢復成一句正確的翻譯。

**2. 是否會傷害 CASE1 / CASE4 / CASE5？**
`no_repeat_ngram_size=3` **完全不會**——這三句輸出跟 baseline 一字不差。`repetition_penalty=1.20` 會動到更多句子（71句裡55句不同），而且會讓短感嘆詞「腦補」出原文沒有的內容（例：「うわー」被翻成「哇哦，真是太棒了」，比原文多講了東西），這是一個新的副作用，雖然不影響 CASE1/4/5，但代表這個參數對其他短句有輕微幻覺風險。`no_repeat_ngram_size=2` 也乾淨，但改動的句子比 =3 多（42句），沒有明顯優勢。

**3. 是否值得讓 MADLAD 進下一輪 live test？**
就翻譯品質而言，**值得**——`no_repeat_ngram_size=3` 看起來是目前找到的最佳單一設定，解決了短句重複問題且不犧牲長句/外來語品質，延遲甚至比 baseline 略快（549ms vs 585ms，因為不用再生成一堆重複字元）。**但 VRAM 限制依然存在**：MADLAD 3B（+4.2GB）加上 Kotoba-whisper（+2.1GB）在這台 8GB 卡上還是裝不下，這個問題跟 decoding 參數無關，沒有被這輪測試解決。

**4. 如果都無法解決...**
不適用——`no_repeat_ngram_size=3` 這組確實解決了，不需要更複雜的 workaround。

## Live-session follow-up: length_penalty (2026-09-26)

First High-preset live test (RTX 4070 Ti) showed MADLAD padding and duplicating short utterances even with `no_repeat_ngram_size=3` (e.g. すごいな → 「真是太棒了，這麼多年來，我從來沒有見過這樣的東西。」, 懐かしいね → 「很想念, 很難忘, 太想念了。」). All 70 translation units of that session were saved as a text-only regression set, `translation_dataset_live.py` (no audio kept, so translation side only), and run offline with `run_live_regression.py` on the live set plus the original dataset. Offline decoding with the production config reproduced the live output 70/70.

Length measurement on the production output: acceptable translations stay at <= ~1.33x output/input tokens; padded or duplicated ones have a median of ~1.86x.

| Config (on top of beam 4 + no_repeat_ngram_size=3) | Live set changed | Result |
|---|---|---|
| hard `max_decoding_length` = 1.5x+2 | 19/70 | Rejected: truncates mid-sentence (「真是令人驚歎，這麼多」) |
| n-best (4 finished hyps), pick best within 1.3x/1.5x | 9/70, 7/70 | Safe but weak: fixes the D-style loop, most padding untouched |
| `length_penalty=0.0` | 36/70 | Most padding removed, but more regressions, incl. CASE1 rewording |
| **`length_penalty=0.5`** | 28/70 | **Adopted.** ~15 live + ~9 original improved, ~5 mild regressions, CASE1/CASE4/CASE5 unchanged |
| `length_penalty=0.5` + n-best 1.5x | 29/70 | Same as 0.5 alone, no extra gain |

Improved with 0.5: だから初めてわあ (loop → 「所以，這是第一次，哇，哇。」), なんだけどあなた (drops the invented 「你是這麼的可愛」), 懐かしいね, これは, 地上に出たら家族に会える喜びもある, D08 (drops 「哈哈哈」). Mild regressions: 初コラボ → 「首次合作合作。」, 名が刻まれる → 「刻有名字的名字。」, one sentence ending on a dangling 「但是，」. Latency unchanged (~570ms avg).

Not fixed by any decoding setting: the worst padding (すごいな, 懐かしいな, でも京子ちゃん, 毎日2回行動). All 4 beam hypotheses are padded there, so this is model behavior, not decoding. Member names (フブちゃん → 胡佛, etc.) are also unaffected and need a separate fix.
