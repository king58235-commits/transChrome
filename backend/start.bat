@echo off
cd /d "%~dp0"

if not exist venv (
    echo venv not found. Run setup.bat first.
    pause
    exit /b 1
)

rem A backend left running (window minimized, or started in the background)
rem keeps holding port 8765 and several GB of VRAM. Detect it up front with a
rem clear message instead of letting main.py fail with a port-in-use traceback.
set "EXISTING_PID="
for /f "tokens=5" %%p in ('netstat -ano -p tcp ^| findstr /C:"127.0.0.1:8765 " ^| findstr LISTENING') do set "EXISTING_PID=%%p"
if defined EXISTING_PID (
    title transChrome Backend - ALREADY RUNNING
    echo Backend is already running on port 8765 ^(PID %EXISTING_PID%^).
    echo Look for the "transChrome Backend - RUNNING" window in the taskbar and use that one,
    echo or stop it first with:  taskkill /PID %EXISTING_PID% /T /F
    echo.
    pause
    exit /b 1
)

rem Window title shows in the taskbar, so a forgotten backend is easy to spot.
title transChrome Backend - RUNNING (port 8765)
echo Starting backend on ws://127.0.0.1:8765 ...
echo (First run downloads Kotoba-whisper (~1.5GB) and Sakura-7B (~4.3GB) from Hugging Face.)
echo Keep this window open while using the extension. Press Ctrl+C to stop.
echo.
venv\Scripts\python.exe main.py
title transChrome Backend - STOPPED
pause
