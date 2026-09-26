"""Install the llama.cpp runtime (llama-server.exe) used by the Sakura
translation backend: the official Windows CUDA 12.4 build of
config.LLAMA_CPP_RELEASE from github.com/ggml-org/llama.cpp, extracted into
config.LLAMA_SERVER_DIR (git-ignored). The CUDA runtime DLLs it needs come
from the pip packages in requirements.txt, so the separate cudart zip isn't
downloaded. Run by setup.bat; safe to re-run (skips if already installed).

GitHub release downloads can be throttled to a few dozen KB/s per connection,
so the zip is fetched in parallel byte ranges.
"""
import io
import os
import sys
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

from config import LLAMA_CPP_RELEASE, LLAMA_SERVER_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

URL = (f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_CPP_RELEASE}/"
       f"llama-{LLAMA_CPP_RELEASE}-bin-win-cuda-12.4-x64.zip")
TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), LLAMA_SERVER_DIR)
VERSION_FILE = os.path.join(TARGET, "VERSION.txt")
CONNECTIONS = 16


def fetch_range(start, end):
    req = urllib.request.Request(URL, headers={"Range": f"bytes={start}-{end}"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except OSError:
            if attempt == 4:
                raise


def main():
    if os.path.isfile(VERSION_FILE) and open(VERSION_FILE).read().strip() == LLAMA_CPP_RELEASE:
        print(f"      llama.cpp {LLAMA_CPP_RELEASE} 已安裝，略過。")
        return
    with urllib.request.urlopen(urllib.request.Request(URL, method="HEAD"), timeout=60) as r:
        total = int(r.headers["Content-Length"])
    print(f"      下載 llama.cpp {LLAMA_CPP_RELEASE}（{total / 1e6:.0f} MB）...")
    step = -(-total // CONNECTIONS)
    ranges = [(i, min(i + step, total) - 1) for i in range(0, total, step)]
    done = [0]

    def fetch_and_report(r):
        chunk = fetch_range(*r)
        done[0] += 1  # progress only; a lost update just skips a line
        print(f"      {done[0] * 100 // len(ranges)}%", flush=True)
        return chunk

    with ThreadPoolExecutor(CONNECTIONS) as pool:
        data = b"".join(pool.map(fetch_and_report, ranges))
    if len(data) != total:
        sys.exit(f"下載不完整（{len(data)} / {total} bytes），請重新執行 setup.bat。")
    os.makedirs(TARGET, exist_ok=True)
    zipfile.ZipFile(io.BytesIO(data)).extractall(TARGET)
    with open(VERSION_FILE, "w") as f:
        f.write(LLAMA_CPP_RELEASE + "\n")
    print("      llama.cpp 安裝完成。")


if __name__ == "__main__":
    main()
