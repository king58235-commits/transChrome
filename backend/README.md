# Backend

Full architecture, install, run, known issues, and benchmarks are documented
in the [project README](../README.md). Quick reference:

## Setup

```
setup.bat
```

## Run

```
start.bat
```

Starts a WebSocket server on `ws://127.0.0.1:8765`.

## Verify without Chrome

```
venv\Scripts\python test_client.py
```

Sends synthetic silent PCM16 audio over the WebSocket protocol; useful for
confirming the server starts and doesn't crash without needing the extension.
Silence doesn't exercise real transcription quality — that still needs a real
Chrome + YouTube test.
