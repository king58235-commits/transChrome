@echo off
cd /d "%~dp0"

if not exist venv (
    echo venv not found. Run setup.bat first.
    pause
    exit /b 1
)

echo Starting backend on ws://127.0.0.1:8765 ...
echo (First run downloads Kotoba-whisper (~1.5GB) and MADLAD (~3GB) from Hugging Face.)
echo Keep this window open while using the extension. Press Ctrl+C to stop.
echo.
venv\Scripts\python.exe main.py
pause
