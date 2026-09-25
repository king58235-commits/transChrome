# Hardware Compatibility & Fallback Benchmark

Same quality setting throughout: Kotoba-whisper (STT) + MADLAD-400 3B int8 with `no_repeat_ngram_size=3` (Translation). Only the **device** each runs on changes. Test data: existing 70-71 sentence translation dataset (MADLAD) and `test_clip.wav` (Kotoba, 314s / 5.23min). No live rerun, no quality re-scoring, no production files touched (server stopped only to free VRAM/CPU for a clean measurement, restarted after — `config.py` unchanged throughout).

## Comparison table

| Mode | STT device | Translation device | Avg latency | P50 | P95 | CPU usage | RAM | VRAM | Queue backlog | OOM | Live suitability | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **A** | GPU | GPU | 528ms | 497ms | 964ms | — (GPU-bound) | — | **7533 MiB peak / 8192** (659 MiB headroom) | None expected | **No OOM** — both loaded + real inference confirmed working | **Good** | Contradicts earlier back-of-envelope estimate; actual combined test fits, but margin is thin |
| **B** | GPU | **CPU** | 1597ms | 1350ms | 2905ms | ~385% (of 2000% max, 20 logical cores) | +92 MB (translation) | Kotoba only: ~2.1GB | None expected (see analysis below) | N/A | **Good** — meets your <=2s avg / <=3s P95 target | Best fallback candidate |
| **C** | **CPU** | GPU | Kotoba RTF=**2.622**× (i.e. 2.6x slower than real-time) | — | — | ~368% avg, 888% peak | Kotoba: ~1GB | MADLAD only: 7440 MiB (Mode A load figure) | **Would accumulate — STT itself can't keep up with live audio** | No OOM, but irrelevant | **Not viable** | Disqualified by STT alone, translation device doesn't matter |
| **D** | **CPU** | **CPU** | (STT: same 2.622x RTF as C) | — | — | High (STT dominates) | ~1-1.3GB total (STT+translation) | 0 (no GPU used) | **Would accumulate**, same reason as C | No OOM | **Not viable, but "runs"** | Confirms: doesn't crash, just can't keep up live |

## Mode B deep-dive (the most important test, per the brief)

1. **MADLAD CPU avg latency: 1597ms** — under your 2s target.
2. **P95: 2905ms** — under your 3s target (barely: 2905 < 3000).
3. **Live experience**: full per-sentence detail in `benchmark/test_madlad_cpu.py` output — no batching used, one sentence at a time as specified.
4. **Queue backlog**: not measured via a literal 10-minute rerun (per your instruction not to redo the live stream). Instead, a queueing-theory check using two already-measured real numbers: production's actual translation-unit arrival rate from the earlier Stage 2B benchmark was ~60 units over 314s ≈ **one unit every 5.2s on average**. MADLAD-CPU's avg (1.6s) and even P95 (2.9s) latency are both comfortably below that 5.2s inter-arrival time, so the single FIFO worker should finish each translation before the next one typically arrives — **no backlog growth expected**. This is a projection from measured data, not an empirical 10-minute observation; flagging that distinction explicitly since you asked for one.
5. **RAM**: only +92MB growth from load-time to after running all 70 sentences — no indication of a leak in this sample size. CPU usage (~385% of 2000% available on this 20-logical-core machine) leaves the vast majority of the CPU free, so no system-wide sluggishness expected from this alone.

## Mode A note (contradicts the earlier "won't fit" assumption)

The Stage 2B benchmark's earlier VRAM-delta arithmetic (Kotoba +2.1GB + MADLAD +4.2GB + ~3GB background ≈ 9.3GB) was extrapolated from **separate measurements taken at different times with different background-app VRAM noise** (2.9-4.8GB baseline observed across different runs). Actually loading both in the same process and running real inference gave **7533 MiB peak** — it fits, with **659 MiB headroom**. That's thin (a heavier browser tab or another GPU app could tip it over), but it is not the hard OOM the earlier estimate implied. No workaround was applied to achieve this — this is the stock configuration.

## Mode C/D note

Kotoba-whisper on CPU (int8) has a **realtime factor of 2.622** on `test_clip.wav` — processing took 2.6x longer than the audio's own duration. For segments that actually contain speech (not silence — the VAD-filtered silent chunks resolve in ~5ms and don't represent the real cost), per-segment inference was **~11-12 seconds** each. This alone disqualifies both C and D for live captioning regardless of what device translation runs on — the STT stage falls further behind in real time with every segment. Neither mode crashed or OOM'd; they simply can't keep pace with a live stream.

## Direct answers to the 5 questions

**1. RTX 3050 8GB 是否能跑 Kotoba GPU + MADLAD GPU？**
能，實測兩者同時載入並跑真實推論成功，峰值 VRAM 7533/8192 MiB，餘裕約 660MB。餘裕偏薄，但沒有 OOM。

**2. Kotoba GPU + MADLAD CPU 是否可作實用 fallback？**
可以——平均延遲 1.6 秒、P95 2.9 秒，都落在你要的目標範圍內，CPU 佔用率也不高（約 385%／2000% 上限），佇列理論上不會累積。這是目前測出來最穩健的一組。

**3. 全 CPU 是否至少能跑？**
能「跑」（不會 crash、不會 OOM），但 Kotoba CPU 的 realtime factor 是 2.622——處理速度比音訊本身還慢 2.6 倍，代表音訊會越積越多，完全不適合即時直播用途，純粹是「能執行」而非「能用」。

**4. 哪個模式最適合這台公司的 RTX 3050 8GB？**
**Mode B（Kotoba GPU + MADLAD CPU）**——VRAM 餘裕比 Mode A 多很多（只需要 Kotoba 的 ~2.1GB，不用擠進 MADLAD 的 4.2GB），延遲依然達標，是風險最低的選擇。Mode A 雖然測出來「能跑」，但 660MB 的餘裕在背景應用程式波動時有踩線風險。

**5. 哪個模式最適合之後 RTX 4070 Ti？**
**Mode A（Kotoba GPU + MADLAD GPU）**——4070 Ti 有 12GB VRAM，兩個模型同時常駐的延遲更低（528ms 平均，比 CPU 的 1597ms 快 3 倍），VRAM 餘裕也會從 660MB 大幅提升，沒有理由不兩個都上 GPU。

## Hardware tier summary

- **High**（大顯存 GPU，如 4070 Ti 12GB+）：Kotoba GPU + MADLAD GPU（Mode A）
- **Balanced**（6-8GB VRAM，如這台 RTX 3050）：Kotoba GPU + MADLAD CPU（Mode B）
- **Low**：目前不可行（Mode C/D 都被 Kotoba CPU 的 realtime factor 2.622 卡死），需要之後另做更小的模型 preset，這輪不設計。

Production `config.py` 全程未修改。原始數據見 `benchmark/test_mode_a_full.py`、`test_madlad_cpu.py`、`test_kotoba_cpu.py` 的輸出。
