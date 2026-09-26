"""Sakura-7B translation backend: one llama.cpp server process (llama-server.exe)
started at backend startup, kept loaded on the GPU for the whole session, and
called over localhost HTTP once per translation unit. Model, runtime and
prompt are exactly what the 09-26 offline benchmark validated (see config.py).

The server is tied to this Python process with a Windows job object, so it
can't outlive the backend and keep holding ~4GB of VRAM (closing the console
window, Ctrl+C and a crash all take it down).
"""
import atexit
import ctypes
import http.client
import json
import logging
import os
import re
import secrets
import socket
import subprocess
import sys
import time

from config import (
    LLAMA_SERVER_DIR,
    LLAMA_SERVER_PORT,
    LOG_DIR,
    SAKURA_MAX_TOKENS_CAP,
    SAKURA_MAX_TOKENS_MIN,
    SAKURA_MAX_TOKENS_PER_CHAR,
    SAKURA_MODEL_FILE,
    SAKURA_MODEL_REPO,
)

logger = logging.getLogger("sakura")

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_EXE = os.path.join(BACKEND_DIR, LLAMA_SERVER_DIR, "llama-server.exe")
SERVER_LOG = os.path.join(BACKEND_DIR, LOG_DIR, "llama_server.log")
STARTUP_TIMEOUT_S = 120
REQUEST_TIMEOUT_S = 30

# Official Sakura v1.0 prompt (github.com/SakuraLLM/SakuraLLM), unchanged: the
# benchmark ran with it and got no explanations, notes or markdown in any
# output. The model answers in Simplified Chinese; translator.py runs OpenCC.
SYSTEM_PROMPT = ("你是一个轻小说翻译模型，可以流畅通顺地以日本轻小说的风格将日文翻译成简体中文，"
                 "并联系上下文正确使用人称代词，不擅自添加原文中没有的代词。")

# The same 1-10 character piece repeated 8+ more times at the end of the
# output ("啊啊啊啊…", "哈哈哈…", "對對對…") means generation ran away.
_RUNAWAY_RE = re.compile(r"(.{1,10}?)\1{7,}$", re.S)

_proc = None
_job = None
_model_path = None
# Random per-start API key: llama-server allows any origin (CORS), so without
# one any web page open in the browser could call it on localhost.
_api_key = secrets.token_hex(16)


def _prompt(japanese_text, names=()):
    # With names: Sakura v1.0's official glossary form ("source->target #note"
    # lines), target in Simplified like the rest of its output.
    if names:
        glossary_lines = "\n".join(f"{src}->{dst} #人名" for src, dst in names)
        user = (f"根据以下术语表（可以为空）：\n{glossary_lines}\n"
                f"将下面的日文文本根据对应关系和备注翻译成中文：{japanese_text}")
    else:
        user = f"将下面的日文文本翻译成中文：{japanese_text}"
    return (f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n"
            f"<|im_start|>assistant\n")


def _port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _BasicLimitInfo(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", ctypes.c_uint32), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", ctypes.c_uint32), ("SchedulingClass", ctypes.c_uint32)]


class _ExtendedLimitInfo(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimitInfo), ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


def _kill_with_this_process(proc):
    """Put proc in a job object that kills it when this process exits for any
    reason (the job handle closes with us). Best effort: on failure the atexit
    handler still covers a normal exit."""
    global _job
    if sys.platform != "win32":
        return
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = ctypes.c_void_p
    k32.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    k32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    job = k32.CreateJobObjectW(None, None)
    info = _ExtendedLimitInfo()
    info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = job and k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)) \
        and k32.AssignProcessToJobObject(job, int(proc._handle))
    if ok:
        _job = job  # keep the handle open for our whole lifetime
    else:
        logger.warning("Couldn't tie llama-server to the backend process (error %d)", ctypes.get_last_error())


def stop():
    global _proc
    if _proc is not None and _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _proc.kill()
    _proc = None


def start():
    """Start llama-server with Sakura-7B fully on the GPU and wait until it is
    ready. Raises (no silent fallback) if the runtime or model is missing, the
    port is taken, or the server exits during startup."""
    global _proc, _model_path
    from huggingface_hub import hf_hub_download

    if not os.path.isfile(SERVER_EXE):
        raise FileNotFoundError(f"llama-server.exe not found at {SERVER_EXE}. Run setup.bat (or "
                                f"venv\\Scripts\\python.exe setup_llama.py) to install the llama.cpp runtime.")
    if _port_in_use(LLAMA_SERVER_PORT):
        raise RuntimeError(f"Port {LLAMA_SERVER_PORT} is already in use, probably a leftover llama-server.exe. "
                           f"Close it (Task Manager, or: taskkill /IM llama-server.exe /F) and start again.")
    _model_path = hf_hub_download(SAKURA_MODEL_REPO, SAKURA_MODEL_FILE)
    logger.info("Sakura model: %s", _model_path)
    logger.info("llama.cpp runtime: %s (llama-server log: %s)", SERVER_EXE, SERVER_LOG)

    os.makedirs(os.path.dirname(SERVER_LOG), exist_ok=True)
    started = time.monotonic()
    _proc = subprocess.Popen(
        [SERVER_EXE, "-m", _model_path, "--host", "127.0.0.1", "--port", str(LLAMA_SERVER_PORT),
         "-ngl", "99", "-c", "2048", "-np", "1", "--no-webui", "--api-key", _api_key],
        stdout=subprocess.DEVNULL, stderr=open(SERVER_LOG, "w", encoding="utf-8"),
    )
    _kill_with_this_process(_proc)
    atexit.register(stop)

    while True:
        if _proc.poll() is not None:
            raise RuntimeError(f"llama-server exited during startup (code {_proc.returncode}), see {SERVER_LOG}")
        try:
            conn = http.client.HTTPConnection("127.0.0.1", LLAMA_SERVER_PORT, timeout=2)
            conn.request("GET", "/health")
            if conn.getresponse().status == 200:
                break
        except OSError:
            pass
        if time.monotonic() - started > STARTUP_TIMEOUT_S:
            stop()
            raise RuntimeError(f"llama-server not ready after {STARTUP_TIMEOUT_S}s, see {SERVER_LOG}")
        time.sleep(0.2)
    generate("テスト")  # warm-up, and surfaces a runtime problem now instead of on the first real sentence
    logger.info("Sakura-7B ready on CUDA via llama-server (PID %d, %.1fs)", _proc.pid, time.monotonic() - started)


def generate(japanese_text, names=()):
    """Translate one unit; returns the model's Simplified Chinese text.
    names: (Japanese, Simplified Chinese) member-name glossary entries."""
    max_tokens = min(SAKURA_MAX_TOKENS_CAP, max(SAKURA_MAX_TOKENS_MIN, SAKURA_MAX_TOKENS_PER_CHAR * len(japanese_text)))
    body = {"prompt": _prompt(japanese_text, names), "n_predict": max_tokens, "temperature": 0,
            "stream": True, "stop": ["<|im_end|>"], "cache_prompt": True}
    conn = http.client.HTTPConnection("127.0.0.1", LLAMA_SERVER_PORT, timeout=REQUEST_TIMEOUT_S)
    started = time.monotonic()
    first_token_s = None
    try:
        conn.request("POST", "/completion", json.dumps(body),
                     {"Content-Type": "application/json", "Authorization": f"Bearer {_api_key}"})
        resp = conn.getresponse()
        if resp.status != 200:
            raise RuntimeError(f"llama-server returned HTTP {resp.status}: {resp.read()[:200]!r}")
        text = ""
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line.startswith("data: "):
                continue
            chunk = json.loads(line[6:])
            if first_token_s is None and chunk.get("content"):
                first_token_s = time.monotonic() - started
            text += chunk.get("content", "")
            if _RUNAWAY_RE.search(text):
                # Closing the connection makes llama-server stop generating.
                logger.warning("[SAKURA] runaway repetition stopped: %r", text[-40:])
                return _RUNAWAY_RE.sub(lambda m: m.group(1) * 2, text).strip()
            if chunk.get("stop"):
                if chunk.get("stop_type") == "limit":
                    logger.warning("[SAKURA] hit the %d-token output limit for: %s", max_tokens, japanese_text)
                break
        return text.strip()
    finally:
        conn.close()
        total_s = time.monotonic() - started
        if total_s > 1.0:  # stall diagnostics: normally ~0.1s
            logger.warning("[SAKURA] slow generation: %.1fs total, first token after %s", total_s,
                           f"{first_token_s:.1f}s" if first_token_s is not None else "none")
