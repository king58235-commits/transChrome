# 第三方元件與授權說明

transChrome 本身不包含任何 AI 模型或 llama.cpp 執行檔。這些元件會在執行 `setup.bat` 和第一次執行 `start.bat` 時，從下列官方來源下載到你的電腦。使用時請遵守各元件的授權條款。

以下授權資訊整理自各來源在 2026-09-26 標示的內容，僅供參考；實際條款以各來源頁面為準。

## AI 模型

| 元件 | 用途 | 來源 | 授權 |
|---|---|---|---|
| Kotoba-Whisper v2.0（faster-whisper 格式） | 日文語音辨識 | [kotoba-tech/kotoba-whisper-v2.0-faster](https://huggingface.co/kotoba-tech/kotoba-whisper-v2.0-faster)（原始模型：[kotoba-tech/kotoba-whisper-v2.0](https://huggingface.co/kotoba-tech/kotoba-whisper-v2.0)，Apache-2.0） | MIT |
| Sakura-7B-Qwen2.5-v1.0（GGUF iq4xs） | 日文翻譯成中文 | [SakuraLLM/Sakura-7B-Qwen2.5-v1.0-GGUF](https://huggingface.co/SakuraLLM/Sakura-7B-Qwen2.5-v1.0-GGUF)（[SakuraLLM](https://github.com/SakuraLLM/SakuraLLM)） | **CC BY-NC-SA 4.0** |
| MADLAD-400 3B（CTranslate2 int8，舊版翻譯，預設不下載） | 只在 `TRANSLATION_BACKEND = "madlad"` 時使用 | [Heng666/madlad400-3b-mt-ct2-int8](https://huggingface.co/Heng666/madlad400-3b-mt-ct2-int8)（原始模型：[google/madlad400-3b-mt](https://huggingface.co/google/madlad400-3b-mt)） | Apache-2.0 |

### Sakura 的非商業使用限制

Sakura-7B 採用 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 授權，SakuraLLM 並聲明其模型與衍生品**禁止任何形式的商業用途**。

- 個人使用、分享給朋友非商業使用：可以。
- 用於營利、商業服務、或包含在付費產品中：**不可以**。
- 分享或散布時，需要標示來源（SakuraLLM），並以相同授權條款分享。

transChrome 不會重新散布 Sakura 模型；模型由使用者的電腦直接從上方來源下載。

## 執行環境

| 元件 | 用途 | 來源 | 授權 |
|---|---|---|---|
| llama.cpp（b11200，Windows CUDA 12.4 版） | 在 GPU 上執行 Sakura-7B | [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) | MIT |
| NVIDIA CUDA runtime、cuBLAS、cuDNN（pip 套件） | GPU 運算 | PyPI：`nvidia-cuda-runtime-cu12`、`nvidia-cublas-cu12`、`nvidia-cudnn-cu12` | NVIDIA 專有授權（NVIDIA Software License Agreement） |

## Python 套件（由 `setup.bat` 從 PyPI 安裝）

| 套件 | 授權 |
|---|---|
| faster-whisper（內含 Silero VAD 模型） | MIT |
| CTranslate2 | MIT |
| huggingface_hub | Apache-2.0 |
| OpenCC | Apache-2.0 |
| websockets | BSD-3-Clause |
| NumPy | BSD-3-Clause（含其他寬鬆授權的元件） |
| ONNX Runtime | MIT |
| SentencePiece | Apache-2.0 |
| PyAV（內含 FFmpeg 函式庫） | BSD-3-Clause（FFmpeg 為 LGPL） |

其他間接相依的套件，授權資訊可以在 `backend\venv\Lib\site-packages\` 中各套件的 metadata 查看。
