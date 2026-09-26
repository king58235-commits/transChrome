import asyncio
import errno
import logging
import os
import subprocess
import sys
import time
import threading
import traceback
import warnings

# Before huggingface_hub is imported: its symlink warning on Windows is noise
# for users (caching works without symlinks).
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
# Hugging Face's own console logger would print server notices such as the
# "unauthenticated requests" hint on the first download.
os.environ.setdefault("HF_HUB_VERBOSITY", "error")

import config
import sakura
import transcriber
import translator
from server import start_server

# Windows consoles often default to a non-UTF-8 codepage (e.g. cp950 on
# Traditional Chinese locale), which can't represent Japanese characters and
# silently mangles them into '?'/replacement chars. Force UTF-8 for output
# (start.bat also switches the console to UTF-8 with chcp 65001).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BACKEND_DIR, config.LOG_DIR)
LATEST_LOG = os.path.join(LOG_DIR, "latest.log")
LATEST_LOG_HINT = r"backend\logs\latest.log"

# The console only shows the short status lines printed by say(); the full log
# (INFO and up, tracebacks, library warnings) goes to logs/latest.log
# (overwritten each start, the file to attach to a bug report) and, with
# LOG_TO_FILE, a timestamped copy too.
os.makedirs(LOG_DIR, exist_ok=True)
log_handlers = [logging.FileHandler(LATEST_LOG, mode="w", encoding="utf-8")]
log_path = None
if config.LOG_TO_FILE:
    # Keep only the newest LOG_KEEP_FILES timestamped logs (this start's
    # included); the names sort by start time.
    old_logs = sorted(f for f in os.listdir(LOG_DIR) if f.startswith("backend_") and f.endswith(".log"))
    for name in old_logs[:max(0, len(old_logs) - (config.LOG_KEEP_FILES - 1))]:
        try:
            os.remove(os.path.join(LOG_DIR, name))
        except OSError:
            pass
    log_path = os.path.join(LOG_DIR, time.strftime("backend_%Y%m%d_%H%M%S.log"))
    log_handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
_file_format = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
for handler in log_handlers:
    handler.setFormatter(_file_format)
logging.basicConfig(level=logging.INFO, handlers=log_handlers)
logging.captureWarnings(True)  # Python warnings (e.g. Hugging Face's) to the log, not the console
# Routine per-call lines from libraries ("Processing audio with duration",
# "VAD filter removed", every HTTP request) filled most of the log file.
for noisy in ("faster_whisper", "httpx"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
warnings.filterwarnings("ignore", message=".*unauthenticated requests.*")

logger = logging.getLogger("main")


class StartupError(Exception):
    """A startup problem with a message meant for the user."""


def say(text=""):
    print(text, flush=True)


def log_gpu_state(label):
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        logger.info("[GPU %s] %s", label, out)
    except Exception:
        logger.info("[GPU %s] nvidia-smi unavailable (no NVIDIA GPU, or driver not found)", label)


def check_gpu():
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                                capture_output=True, text=True, timeout=10)
        name = result.stdout.strip().splitlines()[0] if result.returncode == 0 and result.stdout.strip() else ""
    except (OSError, subprocess.TimeoutExpired):
        name = ""
    if not name:
        raise StartupError("找不到 NVIDIA GPU。\n"
                           "transChrome 需要支援 CUDA 的 NVIDIA 顯示卡，並安裝最新的 NVIDIA 驅動程式。")
    logger.info("GPU: %s", name)
    return name


class DownloadProgress:
    """Prints "已下載 x / y GB" every few seconds while a model downloads,
    from the size of its Hugging Face cache folder: Hugging Face's own
    progress bars don't show in every console, and a silent first start
    looks like a hang."""

    def __init__(self, repo, total_gb):
        from huggingface_hub import constants
        self.folder = os.path.join(constants.HF_HUB_CACHE, "models--" + repo.replace("/", "--"))
        self.total_gb = total_gb
        self.stop = threading.Event()

    def _size_gb(self):
        total = 0
        for root, _dirs, files in os.walk(self.folder):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
        return total / 1e9

    def _run(self):
        while not self.stop.wait(3):
            say(f"    已下載 {self._size_gb():.1f} / {self.total_gb} GB")

    def __enter__(self):
        from huggingface_hub.utils import disable_progress_bars
        disable_progress_bars()
        threading.Thread(target=self._run, daemon=True).start()
        return self

    def __exit__(self, *exc):
        from huggingface_hub.utils import enable_progress_bars
        self.stop.set()
        enable_progress_bars()


def load_stt():
    try:
        if not transcriber.model_is_cached():
            say("  第一次使用：正在下載 Kotoba STT 模型（約 1.5GB），需要幾分鐘，之後啟動不用重新下載。")
            with DownloadProgress(transcriber.MODEL_REPO, 1.5):
                transcriber._model_path()
            say("  下載完成。")
        transcriber.load_model()
    except Exception as exc:
        logger.exception("STT model failed to load")
        raise StartupError("Kotoba STT 模型載入失敗。\n"
                           "如果是第一次啟動，請確認網路連線後重新執行 start.bat。") from exc
    if transcriber.device != "cuda":
        say("  [警告] STT 無法使用 GPU（CUDA），改用 CPU，速度會跟不上直播。")
        say("         請確認 NVIDIA 驅動程式是最新版本，並重新執行 setup.bat。")


def load_translation():
    try:
        if config.TRANSLATION_BACKEND == "sakura" and not sakura.model_is_cached():
            say("  第一次使用：正在下載 Sakura-7B 翻譯模型（約 4.3GB），需要幾分鐘，之後啟動不用重新下載。")
            from huggingface_hub import hf_hub_download
            with DownloadProgress(config.SAKURA_MODEL_REPO, 4.3):
                hf_hub_download(config.SAKURA_MODEL_REPO, config.SAKURA_MODEL_FILE)
            say("  下載完成。")
        translator.load_model()
        return True
    except FileNotFoundError:
        logger.exception("Translation runtime missing")
        say("  [警告] 找不到 llama.cpp runtime，請重新執行 setup.bat。")
    except Exception as exc:
        # Translation is a decoupled add-on: Japanese subtitles still work.
        logger.exception("Translation model failed to load; continuing with STT-only (no translation)")
        reason = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        say(f"  [警告] 翻譯模型載入失敗：{reason}")
    say("         目前只會顯示日文字幕。詳細原因請看 " + LATEST_LOG_HINT)
    return False


def print_ready(translation_ok):
    stt = "Kotoba / " + (transcriber.device or "?").upper()
    if not translation_ok:
        translation = "無法使用（只顯示日文）"
    elif config.TRANSLATION_BACKEND == "sakura":
        translation = "Sakura-7B / CUDA"
    else:
        translation = "MADLAD (legacy) / " + config.TRANSLATION_DEVICE.upper()
    say()
    say("=" * 44)
    say(f"  transChrome v{config.VERSION} Backend Ready")
    say()
    say(f"  STT:         {stt}")
    say(f"  Translation: {translation}")
    say(f"  WebSocket:   ws://{config.HOST}:{config.PORT}")
    say()
    say("  可以開始使用 Chrome Extension。")
    say("  關閉這個視窗即可停止 backend。")
    say(f"  若需要回報問題，請附上：{LATEST_LOG_HINT}")
    say("=" * 44)


def main():
    say(f"transChrome v{config.VERSION}")
    logger.info("transChrome v%s", config.VERSION)
    if log_path:
        logger.info("Logging to %s", log_path)
    logger.info("Hardware preset: %s", config.HARDWARE_PRESET)
    logger.info("Translation backend: %s", config.TRANSLATION_BACKEND)

    if sakura._port_in_use(config.PORT):
        raise StartupError(f"Port {config.PORT} 已被其他程式使用。\n"
                           "transChrome backend 可能已經在執行（工作列上的 transChrome 視窗），請先關閉它。")
    say(f"  GPU: {check_gpu()}")
    log_gpu_state("startup (before any model load)")

    say("[1/3] 載入語音辨識（Kotoba）...")
    load_stt()
    log_gpu_state("after STT model load")

    say("[2/3] 載入翻譯模型（Sakura-7B）...")
    translation_ok = load_translation()
    log_gpu_state("after STT + translation models loaded")

    say("[3/3] 啟動 WebSocket server...")
    try:
        asyncio.run(start_server(on_ready=lambda: print_ready(translation_ok)))
    except OSError as exc:
        if exc.errno in (errno.EADDRINUSE, 10048):
            raise StartupError(f"Port {config.PORT} 已被其他程式使用。\n"
                               "請先關閉另一個 transChrome backend（工作列上的 transChrome 視窗）。") from exc
        raise


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        say("backend 已停止。")
    except StartupError as exc:
        logger.error("Startup failed: %s", exc)
        say()
        say(f"[ERROR] {exc}")
        say(f"詳細紀錄：{LATEST_LOG_HINT}")
        sys.exit(1)
    except Exception:
        logger.error("Unexpected error:\n%s", traceback.format_exc())
        say()
        say("[ERROR] backend 發生未預期的錯誤而停止。")
        say(f"若需要回報問題，請附上：{LATEST_LOG_HINT}")
        sys.exit(1)
