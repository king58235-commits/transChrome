import asyncio
import logging
import subprocess
import sys

import config
import transcriber
import translator
from server import start_server

# Windows consoles often default to a non-UTF-8 codepage (e.g. cp950 on
# Traditional Chinese locale), which can't represent Japanese characters and
# silently mangles them into '?'/replacement chars. Force UTF-8 for log output.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("main")


def log_gpu_state(label):
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        logger.info("[GPU %s] %s", label, out)
    except Exception:
        logger.info("[GPU %s] nvidia-smi unavailable (no NVIDIA GPU, or driver not found)", label)


if __name__ == "__main__":
    logger.info("Hardware preset: %s", config.HARDWARE_PRESET)
    logger.info("STT: Kotoba / %s", config.STT_DEVICE.upper())
    logger.info("Translation: MADLAD / %s", config.TRANSLATION_DEVICE.upper())
    log_gpu_state("startup (before any model load)")

    transcriber.load_model()
    log_gpu_state("after STT model load")

    try:
        translator.load_model()
    except Exception:
        # Translation is a decoupled add-on: if it fails to set up (e.g. no
        # internet for the first-run model download), Japanese STT should
        # still work. translator.translate() returns "" when unloaded.
        logger.exception("Translation model failed to load; continuing with STT-only (no translation)")
    log_gpu_state("after STT + translation models loaded")

    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
