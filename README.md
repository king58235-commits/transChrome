# YouTube 即時日文字幕翻譯工具

本機工具：擷取 YouTube 分頁音訊 → 本機日文語音辨識 → 本機日文→繁體中文翻譯 → 即時雙語字幕 Overlay，顯示在 YouTube 播放器畫面上。完全本機運算，不使用付費 API，不依賴雲端 LLM。

## 1. 目前架構

```
Chrome Tab Audio
  → Extension (offscreen document) 擷取 + 降頻至 16kHz mono PCM16
  → WebSocket (ws://127.0.0.1:8765)
  → Python Backend
      → Audio Buffer 累積
      → 語音停頓偵測 (Silero VAD, faster-whisper 內建)
      → faster-whisper (kotoba-whisper-v2.0-faster，GPU CUDA float16 優先，CPU int8 為 fallback)
      → Japanese partial / final 結果
      → （只有 final）Translation Sentence Buffer：依「真實 audio 停頓時間」合併相鄰 STT final，
        避免一句話因為 STT 的短停頓斷句被拆成沒有上下文的片段分別翻譯
      → Sakura-7B（llama.cpp llama-server，GPU 常駐）→ OpenCC s2twp → 繁體中文（台灣用字）
  → WebSocket 送回 Extension（partial / final / translation 三種訊息各自獨立）
  → content.js 更新 YouTube 播放器上的字幕 Overlay（由上到下照時間順序：最多 3 組「日文原文＋中文翻譯」，最下方是正在說的日文）
```

**串流字幕的運作方式**：講話期間，backend 每 ~0.75 秒把目前這句「還沒講完」的音訊整段重新辨識一次，當作可被覆寫的 `partial` 送回去顯示；偵測到語音停頓（或講超過 8 秒還沒停頓）就用較高品質設定做最後一次辨識，當作 `final` 送出並鎖定顯示，同時清空 buffer 開始下一句。沒有做增量式的 confirmed-prefix 演算法（像 Whisper-Streaming 那樣） — GPU 加速後單次辨識已經快到可以每次整段重跑，不需要那層複雜度。

**翻譯的運作方式**：只有 finalized 的日文才會被翻譯，partial 不會。STT 的斷句（~300ms 停頓）是為了讓日文字幕反應快，但常常把一句話切成好幾段；直接逐段翻譯會讓 NLLB 失去上下文、翻出語意不連貫的中文。因此在 STT 與翻譯之間加了一層 Translation Sentence Buffer：用 VAD 量出的**真實語音停頓時間**（不是 STT final 訊息抵達 server 的時間差，那個會被 buffering / inference 延遲污染）判斷要不要把相鄰的 STT final 合併成一個翻譯單位。翻譯本身跑在獨立的 FIFO queue + worker，跟 STT 完全解耦，翻譯多慢都不會卡住日文字幕。

**Hardware Preset**（`backend/config.py` 的 `HARDWARE_PRESET`，決定 STT/翻譯各自跑在哪個裝置，集中一處管理，不在 `transcriber.py`/`translator.py` 各自 hardcode）：

| Preset | STT 裝置 | 翻譯裝置 | 適合硬體 | 實測數據 |
|---|---|---|---|---|
| **`balanced`**（目前預設） | GPU | **CPU** | VRAM 偏緊的顯卡（約 6-8GB，例如公司這台 RTX 3050 8GB） | 翻譯平均延遲 1.6 秒、P95 2.9 秒；VRAM 只需 Kotoba 的 ~2.1GB，餘裕充足 |
| `high` | GPU | GPU | 顯存較充裕的顯卡（例如 RTX 4070 Ti 12GB+） | 翻譯平均延遲 528ms（比 CPU 快 3 倍）；此卡上實測峰值 VRAM 7533/8192MB，餘裕僅 ~660MB，建議留給顯存更大的卡 |

啟動時 console 會明確印出目前模式，例如：
```
Hardware preset: high
STT: Kotoba / CUDA
Translation: Sakura-7B / CUDA (llama.cpp b11200)
```
（Hardware Preset 目前只影響 STT 與 legacy MADLAD 的裝置；Sakura-7B 固定整個跑在 GPU 上。）
若 `HARDWARE_PRESET` 設成不支援的值，啟動時會直接報錯並列出合法值，不會靜默 fallback。目前只有 `balanced`/`high` 兩檔；純 CPU（含 STT）已實測不可行（Kotoba CPU realtime factor 2.622，處理速度比音訊本身還慢），故未提供第三檔，詳見 `backend/benchmark/hardware_compat_matrix.md`。

**其他目前正式參數**（`backend/config.py`）：

| 參數 | 值 | 用途 |
|---|---|---|
| `STT_MODEL` | `kotoba` | 對應 `STT_MODEL_PRESETS["kotoba"]` = `kotoba-tech/kotoba-whisper-v2.0-faster`。可切換 `small`/`medium`/`kotoba`，比較結果見 `backend/benchmark/result_*.json` |
| `TRANSLATION_BACKEND` | `sakura` | 正式翻譯模型 Sakura-7B（`SAKURA_MODEL_REPO`/`SAKURA_MODEL_FILE` = `SakuraLLM/Sakura-7B-Qwen2.5-v1.0-GGUF` 的 `iq4xs`，第一次啟動自動下載到 Hugging Face 快取）。2026-09-26 離線比較（MADLAD、Sakura-1.5B、Sakura-7B、Qwen2.5-7B，同一批直播字幕句）中品質最好且每句平均 0.11 秒（MADLAD 0.51 秒）。改成 `madlad` 可切回舊的 MADLAD（legacy，程式與設定保留以便 rollback） |
| `LLAMA_CPP_RELEASE` / `LLAMA_SERVER_DIR` | `b11200` / `runtime/llama.cpp` | Sakura 用的 llama.cpp 官方 Windows CUDA 版，由 `setup_llama.py` 安裝，不進 Git |
| `SAKURA_MAX_TOKENS_*` | 每字 2、最少 32、上限 320 | 輸出保護：每句最多輸出的 token 數；另外生成中出現同一段字重複 8 次以上會立刻中止 |
| `STT_HALLUCINATION_TEXTS` / `STT_HALLUCINATION_MAX_SPEECH_S` | `{"ごめん"}` / 0.3s | Whisper 在幾乎無聲的片段上會幻聽出「ごめん」：整句只有這個詞、且人聲不到 0.3 秒時丟棄（不顯示不翻譯）。依據：實測 log 中 17 次 ごめん 全部人聲 < 0.2 秒 |
| `VAD_FALLBACK_*` | 開啟、音量 0.04、人聲 < 0.3s | Silero VAD 在遊戲音效／料理雜音混著人聲時可能完全聽不到人聲，導致字幕停住：VAD 幾乎沒偵測到人聲但音量夠大時，改成不經 VAD 直接辨識，且要等音量也降下來才算停頓（log 記 `[VAD FALLBACK]`）。錄音重播：遊戲／料理直播各救回 12／25 句，安靜與播歌場景只多 1～3 句，延遲約 +0.1 秒 |
| `AUDIO_GAP_LOG_S` | 1.0s | 卡頓診斷（只記錄）：超過此時間沒收到音訊時記 `[GAP]`；另有 `[LOOP LAG]`、`[SAKURA] slow generation`、`[SLOW SEND]`，以及擴充功能回報的 `[CLIENT DIAG]`（capture_gap／send_backlog） |
| `TRANSLATION_MODEL_REPO` 等 | MADLAD 設定 | 只在 `TRANSLATION_BACKEND = "madlad"` 時使用 |
| `LOG_TO_FILE` | True | console log 同時寫進 `backend/logs/backend_*.log`（約 3MB／小時，不進 Git），live 測試後不用再手動複製 log |
| `SAVE_SESSION_AUDIO` | False | 設成 `True` 時，每次「開始字幕」會把收到的音訊另存成 `backend/recordings/session_*.wav`（約 115MB／小時，不進 Git），供之後離線重跑 STT／翻譯合併測試；不影響字幕 |
| `TRANSLATION_LENGTH_PENALTY` | 0.5 | 讓 beam search 偏好較短的完整譯文，減少短句「自己加戲／同義重複」，校準依據同上（live-session 段落） |
| `TRANSLATION_DROP_REPEATED_CLAUSES` | True | 刪掉譯文中「換句話再講一次」的子句（例：「我太緊張了，我很緊張。」→「我太緊張了。」），以及用空格列出的同義說法（「停下來 停住 停止」→「停下來」）；只刪幾乎完全重複、或多出來的只有虛詞的部分，正常的並列句不受影響 |
| `SILENCE_TRIGGER_MS` | 300ms | STT 斷句用的語音停頓門檻（日文字幕反應速度） |
| `TRANSLATION_BOUNDARY_SILENCE_MS` | 800ms | 判斷是否合併相鄰 STT final 成一個翻譯單位的真實語音停頓門檻 |
| `TRANSLATION_IDLE_FLUSH_S` | 0s | 日文定案後等多久才送去翻譯。原為 1.2s，但 live 實測幾乎從未因此合併句子，只讓中文晚 1.8 秒出現；用錄音重播比較 1.2／0.6／0 秒後改為 0（定案即翻，中文約 0.56 秒後出現，譯文內容相同） |
| `TRANSLATION_JOIN_CONTINUATION` / `TRANSLATION_JOIN_MAX_GAP_S` | True / 3s | 上一句以「…て／けど／と／を」等沒講完的形式結尾、且下一句在 3 秒內接上時，把兩句一起翻譯，中文行直接換成合併後的譯文（最多合併兩句）。用 09-26 的 log 測 24 組：約 15 組變好、6 組差不多、3 組變差 |
| `TRANSLATION_MAX_AUDIO_SECONDS` / `TRANSLATION_MAX_CHARS` | 7.0s / 70 字 | 保底上限，避免講很久都不停頓時翻譯單位無限變大 |

## 2. 實際建立的檔案

### extension/（Chrome MV3 擴充功能）
| 檔案 | 用途 |
|---|---|
| `manifest.json` | 擴充功能設定，權限：tabCapture、offscreen、scripting、storage |
| `background.js` | Service worker：tabCapture 協調、offscreen document 生命週期、狀態管理（用 `chrome.storage.session`，因為 service worker 會被 Chrome 回收，不能用一般變數存狀態）、字幕轉發給 content script |
| `offscreen.js` | 實際擷取分頁音訊（`getUserMedia`）、接回喇叭讓使用者仍聽得到聲音、透過 AudioWorklet 降頻、WebSocket 收送 |
| `worklet-processor.js` | AudioWorklet：把原生取樣率降到 16kHz mono PCM16 |
| `content.js` | 在 YouTube 播放器 DOM 上掛字幕 overlay：最多 3 組「日文原文＋中文」（最新 100%、次新 85%、最舊淡出；每組依字數保證最短顯示時間 `clamp(1.5 + 字數×0.08, 1.5, 5)` 秒），合併翻譯會更新最新一組而不重複；最下方是正在說的日文，該句翻譯到達後清空 |
| `popup.html` / `popup.js` | 開始/停止按鈕、Backend 連線狀態顯示 |
| `styles.css` | popup 樣式 + 字幕 overlay 樣式 |

### backend/（Python）
| 檔案 | 用途 |
|---|---|
| `main.py` | 進入點：載入 Whisper 模型、啟動 WebSocket server |
| `server.py` | WebSocket 連線處理、partial/final 觸發邏輯、逾時保護 |
| `audio_buffer.py` | 累積收到的 PCM16 音訊 |
| `transcriber.py` | faster-whisper 封裝：模型載入（含 CUDA 能力偵測與 CPU fallback）、GPU DLL 路徑註冊、VAD 停頓偵測與真實語音時間擷取、partial/final 兩種辨識設定 |
| `translator.py` | 獨立翻譯模組（刻意不 import transcriber.py，與 STT 解耦）：依 `TRANSLATION_BACKEND` 呼叫 Sakura 或 legacy MADLAD、字典前後處理、OpenCC 轉台灣繁中，翻譯失敗永遠回傳空字串、不拋例外 |
| `sakura.py` | Sakura-7B 後端：backend 啟動時開一個 llama-server 程序並常駐 GPU（每句不重新載入），透過本機 HTTP 翻譯；每次啟動產生隨機 API 金鑰；用 Windows job object 綁定 backend，backend 結束（含關視窗、當掉）時 llama-server 一定跟著結束 |
| `setup_llama.py` | 下載並安裝 llama.cpp runtime 到 `backend/runtime/llama.cpp`（setup.bat 會自動執行，已安裝就略過） |
| `glossary.py` | 翻譯前處理：整句只有語助詞或常用短句（ありがとうございます、懐かしい…）時直接給固定譯文；其餘句子再做人名／用語字典替換：把 hololive 成員名與常用直播用語換成固定的中文（或英文）寫法，避免 MADLAD 亂音譯（例如 フブちゃん → 胡佛）。可自行增修，新增名字前先確認 MADLAD 不會把它當一般詞翻譯（說明見檔案開頭）。`STT_FIXES` 放反覆出現的固定聽錯（例如 また目／渡辺 → わため），只收在實際 log 中重複出現、且錯誤寫法在該位置不是一般用詞的項目 |
| `config.py` | 所有可調參數（STT 模型選擇、VAD 閾值、翻譯合併門檻等，見上方「目前正式參數」） |
| `test_client.py` | 不需要 Chrome 的測試工具：不帶參數送 4 秒靜音；帶錄音檔（`test_client.py <wav> [秒數]`）會即時串流並印出日文 final 與中文翻譯 |
| `benchmark/` | 模型/硬體比較工具與長期參考資料：`recorder.py`（錄固定測試音訊）、`run_model.py`/`run_translation_model.py`/`run_madlad_decoding_sweep.py`（STT/翻譯模型與 decoding 參數跑分）、`test_*.py`（硬體相容性測試）、`translation_dataset.py`（固定 70 句翻譯測試集）、三份 `.md` 比較報告。原始逐句 JSON 輸出跟測試音訊本身（`.wav`，內含真實直播內容，有版權疑慮）不進 Git，只保留腳本、資料集跟摘要報告 |
| `setup.bat` | 一鍵建立 venv + 安裝套件 |
| `start.bat` | 一鍵啟動 backend |
| `requirements.txt` | Python 套件清單 |

## 3. 新電腦安裝流程

**系統需求**：Windows、Python 3.10+（開發時用 3.13）、Google Chrome（116+，需要 `tabCapture.getMediaStreamId`）。STT（Kotoba）一定要有 NVIDIA GPU（兩個 preset 都固定用 CUDA，目前沒有 CPU-only 選項——實測 Kotoba 在 CPU 上 realtime factor 2.622，追不上直播音訊，故未提供）。

1. **取得原始碼**：從 Git clone，或直接複製整個專案資料夾到新電腦（不含 `backend/venv/`、任何 `__pycache__/`，這些都不需要、也不會被帶過去）
2. **建立環境**：
   ```
   cd backend
   setup.bat
   ```
   會在**全新一台電腦、完全沒有 venv 的狀態下**自動建立虛擬環境並安裝 `requirements.txt` 裡的所有套件（已實測驗證：用一份乾淨、沒有任何手動裝過套件的 venv 跑過，requirements.txt 本身就足夠讓 Kotoba+MADLAD 兩個模型成功載入並跑出真實翻譯結果）。這步會下載約 1.3GB 的 NVIDIA CUDA runtime（cuBLAS/cuDNN/cudart），不需要另外安裝完整 CUDA Toolkit；最後會執行 `setup_llama.py` 下載 llama.cpp runtime（約 260MB，GitHub 單線下載常被限速，所以用多線分段下載）。
3. **選擇硬體 preset**：打開 `backend/config.py`，確認 `HARDWARE_PRESET` 設成符合你新電腦顯卡的值：
   ```python
   HARDWARE_PRESET = "balanced"  # 顯存偏緊的卡，例如 RTX 3050 8GB
   ```
   或
   ```python
   HARDWARE_PRESET = "high"  # 顯存充裕的卡，例如 RTX 4070 Ti 12GB+
   ```
   （這台公司電腦是 RTX 3050 8GB，用 `balanced`；家裡如果是 RTX 4070 Ti，改成 `high`。詳細差異見下方「Hardware Preset」表格。）
4. **啟動 backend**：
   ```
   start.bat
   ```
   第一次啟動會從 Hugging Face **自動下載模型**（不依賴這台公司電腦既有的任何快取，新電腦會是全新下載）：
   - Kotoba-whisper（約 1.5GB）
   - Sakura-7B（約 4.3GB）

   下載完會快取在 `%USERPROFILE%\.cache\huggingface\hub`，之後每次啟動不用重下。**第一次啟動需要較大的磁碟空間（建議預留 10GB 以上）跟網路連線，時間會明顯比之後久**；等到 console 出現 `server listening on 127.0.0.1:8765` 就代表完成。
   - 如何清除模型快取：直接刪除 `%USERPROFILE%\.cache\huggingface\hub` 底下對應的 `models--*` 資料夾即可，重開 backend 會自動重新下載
5. **載入 Chrome 擴充功能**：
   1. 開 `chrome://extensions`
   2. 右上角打開「Developer mode / 開發人員模式」
   3. 「Load unpacked / 載入未封裝項目」→ 選擇 `extension/` 資料夾
   4. 建議把它釘選到工具列方便使用

完成後即可打開日文 YouTube 影片、點擴充功能圖示 →「開始字幕」開始使用（見下方「執行方法」）。

## 4. 執行方法

1. 雙擊 `backend/start.bat`（或 `cd backend && start.bat`），等到 console 出現 `server listening on 127.0.0.1:8765`
2. 打開一個日文 YouTube 影片，點擴充功能圖示 →「開始字幕」
3. 講話期間字幕會即時浮現並持續修正，停頓後定案
4. 「停止字幕」會停止擷取並清除畫面上的字幕

**每次修改擴充功能程式碼後**：`chrome://extensions` 重新整理擴充功能，並且**把 YouTube 分頁也重新整理一次**（擴充功能 reload 不會自動讓已開啟分頁裡的 content script 重新注入；雖然 `background.js` 有自動偵測並重新注入的 fallback，但正常使用時不會遇到這個問題，只有開發除錯時會）。

## 5. 測試結果

- **Backend 連線 / 音訊持續傳輸**：驗證通過，連續 100+ 秒無中斷
- **日文辨識**：console 能穩定看到正確的日文辨識結果
- **字幕顯示於畫面**：驗證通過，含開始/停止時的正確顯示與清除（含清除時避免殘留空白黑框的修正）
- **10 分鐘穩定性**：在「固定時間切段 + CPU」的舊架構上驗證通過（連續 12 分 47 秒、286 次辨識、記憶體無成長趨勢、僅 1 次觸發逾時保護且自動恢復）。**目前的 GPU + partial/final 串流新架構尚未重新跑過這項長時間測試**，建議之後補測
- **GPU 加速**：確認實際使用 CUDA（非 CPU fallback），benchmark 見下方

## 6. STT 平均延遲

在 NVIDIA GeForce RTX 3050 (8GB VRAM) 上，Whisper "small" + float16：

| 音訊長度 | 平均延遲 |
|---|---|
| 2 秒 | 0.116s |
| 5 秒 | 0.131s |

（純模型運算時間，不含 VAD/serialize 開銷；beam_size=1）

實際 partial 字幕（含 VAD 等開銷）在真實測試中約 0.2-0.3 秒可看到更新。CPU fallback（int8）下，2.5 秒音訊約需 1.5-2 秒，明顯較慢但仍可用。

## 7. CPU / GPU 使用狀況

- **GPU VRAM**：Whisper small float16 模型約增加 790MB 用量
- **GPU 使用率**：辨識當下短暫尖峰，其餘時間閒置（每次呼叫僅 0.1-0.3 秒）
- **Host RAM**（CPU 路徑下量測）：約 570-600MB，長時間運行無持續成長趨勢
- GPU 路徑下的 host RAM 尚未另外量測，但沒有觀察到異常跡象

## 8. 已知問題

- **CUDA 執行需要額外安裝**：僅有 NVIDIA 驅動不夠，ctranslate2 需要 cuBLAS/cuDNN runtime，且必須手動把對應 DLL 目錄加進 `PATH`（`transcriber.py` 的 `_register_nvidia_dll_dirs()` 已處理，但如果 pip 套件版本或路徑結構改變可能需要調整）
- **首次啟動需要網路**：下載 Whisper 模型（~250MB）與（若安裝 GPU 套件）約 1.3GB 的 NVIDIA runtime wheel
- **同時間只能對一個 YouTube 分頁使用**：`activeTabId` 是單一值，沒有處理多分頁同時擷取
- **Backend 斷線不會自動重連**：只會在 popup 顯示 `Disconnected`，需要手動「停止」→「開始」重新連線
- **VAD 停頓判定仍可能不夠自然**：背景音樂/雜音較多的影片，句子邊界偶爾仍會切得不理想，`SILENCE_TRIGGER_MS` / `MAX_CHUNK_SECONDS` 可依實際使用調整
- **`test_client.py` 只送合成靜音**：只能驗證管線本身不會 crash，不能驗證真實辨識品質，真實測試仍需搭配 Chrome 手動操作
- **新的 GPU + 串流架構尚未跑過長時間穩定性測試**（見上方測試結果）
- **未支援全螢幕 / 各種播放器版面配置的完整測試**，overlay 定位邏輯較單純

## 9. 下一階段建議

依優先順序：

1. 補跑一次新架構（GPU + partial/final streaming）的 10 分鐘穩定性測試
2. 依實際使用調整 `PARTIAL_INTERVAL_SECONDS` / `SILENCE_TRIGGER_MS` 等參數
3. Backend 斷線自動重連機制
4. **第二階段**：日文 → 繁體中文本機翻譯（NLLB / MarianMT / CTranslate2 候選），overlay 改為日文 + 繁中雙語同時顯示（使用者已確認的需求，見專案記憶）
5. **第三階段**：YouTube Live Chat 翻譯
6. 若要方便非技術朋友安裝，可考慮之後包裝成 Chrome Web Store 私有/非公開發佈（需要 Google 開發者帳號，目前尚未進行，需另外討論）
