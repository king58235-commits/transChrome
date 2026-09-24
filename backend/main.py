import asyncio
import logging
import sys

import transcriber
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

if __name__ == "__main__":
    transcriber.load_model()
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        logging.getLogger("main").info("Server stopped by user")
