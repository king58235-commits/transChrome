# YouTube 即時日文字幕翻譯工具

本機工具：擷取 YouTube 分頁音訊 → 本機日文語音辨識 → 即時字幕 Overlay，顯示在 YouTube 播放器畫面上。完全本機運算，不使用付費 API，不依賴雲端 LLM。

目前完成到「即時串流字幕」（partial 邊講邊顯示、停頓後 finalize 定案），尚未包含翻譯（見「下一階段建議」）。

## 1. 目前架構

```
Chrome Tab Audio
  → Extension (offscreen document) 擷取 + 降頻至 16kHz mono PCM16
  → WebSocket (ws://127.0.0.1:8765)
  → Python Backend
      → Audio Buffer 累積
      → 語音停頓偵測 (Silero VAD, faster-whisper 內建)
      → faster-whisper (Whisper "small", GPU CUDA float16 優先，CPU int8 為 fallback)
      → partial / final 結果
  → WebSocket 送回 Extension
  → content.js 更新 YouTube 播放器上的字幕 Overlay
```

**串流字幕的運作方式**：講話期間，backend 每 ~0.75 秒把目前這句「還沒講完」的音訊整段重新辨識一次，當作可被覆寫的 `partial` 送回去顯示；偵測到語音停頓（或講超過 8 秒還沒停頓）就用較高品質設定做最後一次辨識，當作 `final` 送出並鎖定顯示，同時清空 buffer 開始下一句。

沒有做增量式的 confirmed-prefix 演算法（像 Whisper-Streaming 那樣） — 因為 GPU 加速後單次辨識已經快到可以每次整段重跑，不需要那層複雜度。

## 2. 實際建立的檔案

### extension/（Chrome MV3 擴充功能）
| 檔案 | 用途 |
|---|---|
| `manifest.json` | 擴充功能設定，權限：tabCapture、offscreen、scripting、storage |
| `background.js` | Service worker：tabCapture 協調、offscreen document 生命週期、狀態管理（用 `chrome.storage.session`，因為 service worker 會被 Chrome 回收，不能用一般變數存狀態）、字幕轉發給 content script |
| `offscreen.js` | 實際擷取分頁音訊（`getUserMedia`）、接回喇叭讓使用者仍聽得到聲音、透過 AudioWorklet 降頻、WebSocket 收送 |
| `worklet-processor.js` | AudioWorklet：把原生取樣率降到 16kHz mono PCM16 |
| `content.js` | 在 YouTube 播放器 DOM 上掛字幕 overlay，接收 partial/final 更新 |
| `popup.html` / `popup.js` | 開始/停止按鈕、Backend 連線狀態顯示 |
| `styles.css` | popup 樣式 + 字幕 overlay 樣式 |

### backend/（Python）
| 檔案 | 用途 |
|---|---|
| `main.py` | 進入點：載入 Whisper 模型、啟動 WebSocket server |
| `server.py` | WebSocket 連線處理、partial/final 觸發邏輯、逾時保護 |
| `audio_buffer.py` | 累積收到的 PCM16 音訊 |
| `transcriber.py` | faster-whisper 封裝：模型載入（含 CUDA 能力偵測與 CPU fallback）、GPU DLL 路徑註冊、VAD 停頓偵測、partial/final 兩種辨識設定 |
| `config.py` | 所有可調參數（chunk 秒數、VAD 閾值、逾時秒數等） |
| `test_client.py` | 不需要 Chrome，直接送合成音訊測試 backend 的除錯工具 |
| `setup.bat` | 一鍵建立 venv + 安裝套件 |
| `start.bat` | 一鍵啟動 backend |
| `requirements.txt` | Python 套件清單 |

## 3. 安裝方法

**系統需求**：Windows、Python 3.10+（開發時用 3.13）、Google Chrome（116+，需要 `tabCapture.getMediaStreamId`）。NVIDIA GPU 為選用，沒有的話會自動用 CPU（速度較慢但仍可運作）。

### Backend
```
cd backend
setup.bat
```
會自動建立虛擬環境並安裝套件。**如果沒有 NVIDIA GPU**，可以先把 `requirements.txt` 最後兩行（`nvidia-cublas-cu12`、`nvidia-cudnn-cu12`，共約 1.3GB）刪掉再跑 `setup.bat`，省下載時間，程式會自動改用 CPU。

### Chrome 擴充功能
1. 開 `chrome://extensions`
2. 右上角打開「開發人員模式」
3. 「載入未封裝項目」→ 選擇 `extension` 資料夾
4. 建議把它釘選到工具列方便使用

## 4. 執行方法

1. 雙擊 `backend/start.bat`（或 `cd backend && start.bat`），等到 console 出現 `server listening on 127.0.0.1:8765`
   - 第一次啟動會從 Hugging Face 下載 Whisper small 模型（約 250MB），需要網路
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
