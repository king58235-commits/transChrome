# Backend

Installation, usage and architecture are in the [project README](../README.md).
Quick reference (the same scripts also exist at the project root):

| Script | What it does |
|---|---|
| `setup.bat` | Checks Python, creates `venv`, installs packages and the llama.cpp runtime. Safe to re-run. |
| `start.bat` | Starts the backend (`ws://127.0.0.1:8765`). Refuses to start a second one. |
| `uninstall.bat` | Removes `venv`, `runtime`, logs and temporary files; asks before removing transChrome's models. |

Logs: `logs/latest.log` (overwritten on every start; attach it to bug reports).

## Verify without Chrome

```
venv\Scripts\python.exe test_client.py <recording.wav>
```

Streams a 16kHz mono PCM16 wav in real time (for example a `recordings/` file
saved with `SAVE_SESSION_AUDIO = True`) and prints every Japanese final and
Chinese translation. Without an argument it sends 4 seconds of silence, which
only checks that the server runs.
