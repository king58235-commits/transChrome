@echo off
rem transChrome backend launcher: the one script users run day to day.
rem ASCII only on purpose; user-facing text is in messages\*.txt (see setup.bat).
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not exist venv\Scripts\python.exe (
    call :msg start_err_venv
    pause
    exit /b 1
)
if not exist runtime\llama.cpp\llama-server.exe (
    call :msg start_err_runtime
    pause
    exit /b 1
)

rem A backend left running (window minimized, or started twice) keeps
rem holding port 8765 and several GB of VRAM. Don't start a second one.
set "EXISTING_PID="
for /f "tokens=5" %%p in ('netstat -ano -p tcp ^| findstr /C:"127.0.0.1:8765 " ^| findstr LISTENING') do set "EXISTING_PID=%%p"
if defined EXISTING_PID (
    title transChrome Backend - ALREADY RUNNING
    call :msg start_already_running
    echo   taskkill /PID %EXISTING_PID% /T /F
    echo.
    pause
    exit /b 1
)

rem Window title shows in the taskbar, so a forgotten backend is easy to spot.
rem Closing this window stops the backend and its llama-server.
title transChrome Backend - RUNNING (port 8765)
venv\Scripts\python.exe main.py
set "CODE=%errorlevel%"
title transChrome Backend - STOPPED
echo.
if not "%CODE%"=="0" call :msg start_stopped
pause
exit /b %CODE%

:msg
type "%~dp0messages\%~1.txt"
exit /b 0
