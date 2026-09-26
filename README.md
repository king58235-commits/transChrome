# transChrome v1.0.0

在 YouTube 上即時顯示「日文原文＋繁體中文翻譯」字幕的本機工具。語音辨識和翻譯都在你自己的電腦上執行，不需要雲端服務或付費 API。

## 系統需求

| 項目 | 需求 |
|---|---|
| 作業系統 | Windows 10 / 11（64 位元） |
| 瀏覽器 | Google Chrome 116 以上 |
| 顯示卡 | 支援 CUDA 的 NVIDIA 顯示卡，並安裝最新的 NVIDIA 驅動程式（不需要另外安裝 CUDA Toolkit） |
| 顯示卡記憶體（VRAM） | **建議 12GB**。本工具本身約使用 6.5GB；目前主要測試環境為 RTX 4070 Ti 12GB，8GB 以下的顯示卡尚未測試 |
| Python | 3.10 以上（64 位元），請先從 [python.org](https://www.python.org/downloads/) 下載安裝，安裝時勾選「Add python.exe to PATH」（`setup.bat` 不會自動安裝 Python） |
| 磁碟空間 | 建議預留 **12GB**（執行環境約 3GB、AI 模型約 5.5GB，安裝過程另有下載暫存） |
| 網路 | 安裝與第一次啟動需要下載約 **7.5GB**（套件約 1.5GB、llama.cpp 約 0.3GB、AI 模型約 5.8GB） |

## 快速安裝

### 方式 A：Git

```
git clone https://github.com/king58235-commits/transChrome.git
cd transChrome
setup.bat
```

之後要更新時：

```
git pull
setup.bat
```

`setup.bat` 可以重複執行，已經裝好的部分會沿用，不會破壞現有環境。

### 方式 B：ZIP（不需要 Git）

1. 到 [Releases 頁面](https://github.com/king58235-commits/transChrome/releases/latest) 下載 `transChrome-1.0.0.zip`
2. 解壓縮到任意資料夾（路徑建議不要有特殊符號）
3. 雙擊 `setup.bat`

`setup.bat` 會做的事：檢查 Python → 在 `backend\venv` 建立獨立的執行環境 → 安裝套件（含 NVIDIA CUDA runtime）→ 下載 llama.cpp → 檢查安裝結果。所有東西都裝在這個資料夾裡，不會修改系統的 Python、PATH 或登錄檔，也不需要系統管理員權限。

## 第一次啟動

雙擊 `start.bat`。第一次啟動會自動下載 AI 模型，畫面上會顯示進度：

- Kotoba 語音辨識模型：約 1.5GB
- Sakura-7B 翻譯模型：約 4.3GB

依網路速度需要幾分鐘到十幾分鐘。模型會存放在 Hugging Face 快取（`%USERPROFILE%\.cache\huggingface\hub`），之後啟動不用重新下載。出現下面的畫面就代表準備好了：

```
============================================
  transChrome v1.0.0 Backend Ready

  STT:         Kotoba / CUDA
  Translation: Sakura-7B / CUDA
  WebSocket:   ws://127.0.0.1:8765

  可以開始使用 Chrome Extension。
============================================
```

## 安裝 Chrome 擴充功能

1. 開啟 `chrome://extensions`
2. 開啟右上角的「開發人員模式」（Developer mode）
3. 按「載入未封裝項目」（Load unpacked）
4. 選擇這個資料夾裡的 `extension` 資料夾

建議把擴充功能釘選到工具列，方便使用。

## 使用

1. 執行 `start.bat`，等到出現「Backend Ready」
2. 在 Chrome 打開日文的 YouTube 影片或直播
3. 點擴充功能圖示，按「開始字幕」

字幕會顯示在播放器上：最下方是正在說的日文，上方最多保留 3 組「日文原文＋中文翻譯」。

## 停止

- 在擴充功能按「停止字幕」
- 關閉 backend 視窗（標題為「transChrome Backend - RUNNING」），翻譯用的 llama-server 會一起結束

## 遇到問題

- 啟動時的錯誤會直接顯示原因，例如找不到 NVIDIA 顯示卡、backend 已經在執行等
- 需要回報問題時，請附上 `backend\logs\latest.log`

## 解除安裝

1. 執行 `uninstall.bat`：刪除 `backend\venv`、`backend\runtime`、紀錄檔與暫存檔，並詢問是否一併刪除 transChrome 使用的 AI 模型（只刪 transChrome 自己的模型，Hugging Face 快取裡的其他模型不會動）
2. 到 `chrome://extensions` 移除 transChrome 擴充功能
3. 如果確定不再使用，手動刪除整個 transChrome 資料夾

## 已知限制

- 只支援 Windows + NVIDIA 顯示卡；目前只在 RTX 4070 Ti 12GB 上完整測試過
- 語音辨識是主要的準確度瓶頸：多人同時講話、口音重、背景音效大時容易聽錯，翻譯會跟著出錯
- 每句獨立翻譯，沒有前後文；省略主詞的句子，人稱偶爾會翻錯
- 人名與粉絲名字典以 hololive 為主（`backend\glossary.py`，可自行增修）
- 同一時間只能對一個 YouTube 分頁使用
- backend 中途關閉時，擴充功能不會自動重新連線，需要按「停止」再「開始」
- 翻譯模型 Sakura-7B 採用 CC BY-NC-SA 4.0 授權，**不可用於商業用途**
- 第一次下載 llama.cpp 時，GitHub 可能限速，下載會比較慢

## 第三方元件與授權

AI 模型（Kotoba-Whisper、Sakura-7B）和 llama.cpp 不包含在 transChrome 裡，而是在安裝和第一次啟動時從官方來源下載。各元件的來源與授權（包括 Sakura 的**非商業使用限制**）請看 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

---

# 開發者資訊

## 架構

```
Chrome 分頁音訊
  → Extension（offscreen document）擷取並降頻為 16kHz mono PCM16
  → WebSocket（ws://127.0.0.1:8765）
  → Python backend
      → 語音停頓偵測（Silero VAD；VAD 聽不到但音量夠大時改用備援判斷）
      → Kotoba-whisper（faster-whisper，CUDA float16）→ 日文 partial / final
      → （只有 final）Translation Sentence Buffer：依真實停頓時間合併相鄰 final
      → 字典前處理（用語、STT 常見聽錯；人名走 Sakura 術語表、粉絲名換成代號）
      → Sakura-7B（llama.cpp llama-server，GPU 常駐）→ OpenCC s2twp → 台灣繁體中文
  → WebSocket 送回 Extension（partial / final / translation）
  → content.js 在播放器上顯示字幕
```

**串流字幕**：講話期間每約 0.75 秒把這句還沒講完的音訊整段重新辨識，當作可覆寫的 `partial`；偵測到停頓（或超過 8 秒）就做最後一次辨識，送出 `final` 並清空 buffer。

**翻譯**：只翻譯 final。翻譯在獨立的佇列裡執行，不會卡住日文字幕。上一句以「…て／けど／と／を」等沒講完的形式結尾、且下一句在 3 秒內接上時，兩句會一起翻譯（「確かに」「さすがに」等副詞例外）。

## 檔案

### extension/（Chrome MV3）
| 檔案 | 用途 |
|---|---|
| `manifest.json` | 擴充功能設定（版本與 backend 的 `config.VERSION` 一致） |
| `background.js` | Service worker：tabCapture、offscreen document 生命週期、狀態、字幕轉發 |
| `offscreen.js` | 擷取分頁音訊、AudioWorklet 降頻、WebSocket 收送；回報擷取端停頓（`[CLIENT DIAG]`） |
| `worklet-processor.js` | AudioWorklet：降頻為 16kHz mono PCM16 |
| `content.js` / `styles.css` | 字幕 overlay：最多 3 組「日文＋中文」（最新 100%、次新 85%、最舊淡出，每組依字數保證最短顯示時間），最下方是正在說的日文 |
| `popup.html` / `popup.js` | 開始／停止按鈕與連線狀態 |

### backend/（Python）
| 檔案 | 用途 |
|---|---|
| `main.py` | 進入點：啟動檢查、載入模型、啟動 WebSocket server；畫面只顯示精簡狀態，完整紀錄寫入 `logs/latest.log` |
| `server.py` | WebSocket 處理、partial/final 觸發、翻譯佇列、幻聽過濾、停頓診斷 |
| `transcriber.py` | faster-whisper 封裝：模型下載與載入、VAD 停頓偵測與備援 |
| `translator.py` | 翻譯流程：字典前後處理、Sakura／legacy MADLAD、OpenCC |
| `sakura.py` | 啟動並管理 llama-server（Windows job object 綁定 backend，關視窗或當掉時一起結束；每次啟動產生隨機 API 金鑰）、輸出保護 |
| `glossary.py` | 固定短句、用語字典、STT 常見聽錯、成員名（`MEMBERS`）、粉絲名（`FANS`） |
| `config.py` | 所有參數與版本號 |
| `setup_llama.py` | 下載 llama.cpp 指定版本（b11200）到 `runtime/llama.cpp` |
| `messages/` | bat 檔顯示的中文訊息（bat 本身維持 ASCII，避免 cmd 在 UTF-8 模式下讀錯行） |
| `setup.bat` / `start.bat` / `uninstall.bat` | 安裝、啟動、解除安裝（專案根目錄有同名入口） |
| `test_client.py` | 不用 Chrome 的測試工具：`test_client.py <wav> [秒數]` 即時串流錄音並印出日文與中文 |
| `benchmark/` | 各項比較的腳本、資料集與報告（例如 `sakura_translation_benchmark.md`） |
| `make_release.py` | 產生 `release/transChrome-<版本>.zip` |

## 主要參數（`backend/config.py`）

| 參數 | 值 | 用途 |
|---|---|---|
| `VERSION` | `1.0.0` | 版本號 |
| `TRANSLATION_BACKEND` | `sakura` | 正式翻譯模型；改成 `madlad` 可切回舊版 MADLAD（程式保留以便 rollback） |
| `SAKURA_MODEL_REPO` / `SAKURA_MODEL_FILE` | `SakuraLLM/Sakura-7B-Qwen2.5-v1.0-GGUF` / `iq4xs` | 選型依據見 `benchmark/sakura_translation_benchmark.md` |
| `LLAMA_CPP_RELEASE` | `b11200` | llama.cpp 官方 Windows CUDA 12.4 版 |
| `SAKURA_MAX_TOKENS_*` | 每字 2、最少 32、上限 320 | 輸出長度上限；另外偵測到大量重複會中止生成 |
| `VAD_FALLBACK_*` | 開啟、音量 0.04 | VAD 在遊戲音效、料理雜音中聽不到人聲時的備援 |
| `STT_HALLUCINATION_*` | `{"ごめん"}` / 0.3s | 過濾 Whisper 在近乎無聲片段上的幻聽 |
| `SILENCE_TRIGGER_MS` | 300ms | 日文斷句的停頓門檻 |
| `TRANSLATION_BOUNDARY_SILENCE_MS` | 800ms | 合併相鄰 final 成一個翻譯單位的停頓門檻 |
| `TRANSLATION_JOIN_CONTINUATION` | True | 沒講完的句子與下一句合併翻譯 |
| `AUDIO_GAP_LOG_S` | 1.0s | 停頓診斷：超過此時間沒收到音訊時記錄 `[GAP]` |
| `LOG_TO_FILE` | True | 除 `latest.log` 外另存 `logs/backend_*.log` |
| `SAVE_SESSION_AUDIO` | False | 開啟時另存每次字幕的音訊到 `recordings/`，供離線重播測試 |
| `HARDWARE_PRESET` | `high` | 只影響 STT 與 legacy MADLAD 的裝置；Sakura 固定在 GPU |

## 發佈

```
backend\venv\Scripts\python.exe backend\make_release.py
```

產生 `release/transChrome-<版本>.zip`：只包含 Git 追蹤的原始碼（不含 `.git`、venv、runtime、模型、log、錄音），bat 檔一律使用 CRLF 換行。
