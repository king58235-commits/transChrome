@echo off
rem transChrome setup: builds backend\venv and installs the llama.cpp runtime.
rem Everything stays inside this folder: no global Python packages, no PATH or
rem registry changes, no admin rights. Safe to run again (reuses what works).
rem
rem This file is ASCII on purpose: with chcp 65001, cmd misreads the line after
rem one containing UTF-8 Chinese. User-facing text lives in messages\*.txt and
rem is printed with "call :msg <name>".
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title transChrome Setup

call :msg setup_intro
echo.

rem 1. Python 3.10+ (64-bit), checked first so a missing Python fails right away.
call :msg setup_step1
set "PY="
py -3 -c "import sys, struct; sys.exit(0 if sys.version_info >= (3, 10) and struct.calcsize('P') == 8 else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys, struct; sys.exit(0 if sys.version_info >= (3, 10) and struct.calcsize('P') == 8 else 1)" >nul 2>&1 && set "PY=python"
if not defined PY goto no_python
for /f "delims=" %%v in ('%PY% -c "import sys; print(sys.version.split()[0])"') do echo       Python %%v

rem 2. backend\venv (reused when it already works)
call :msg setup_step2
if exist venv (
    venv\Scripts\python.exe -c "import sys" >nul 2>&1 || (
        call :msg setup_venv_broken
        rmdir /s /q venv
    )
)
if exist venv (
    call :msg setup_venv_reuse
) else (
    %PY% -m venv venv
    if errorlevel 1 goto fail_venv
)

rem 3. Python packages, incl. the NVIDIA CUDA runtime wheels (no CUDA Toolkit)
call :msg setup_step3
venv\Scripts\python.exe -m pip install --upgrade pip --disable-pip-version-check -q
if errorlevel 1 goto fail_pip
venv\Scripts\python.exe -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 goto fail_pip

rem 4. llama.cpp runtime (fixed release, into backend\runtime)
call :msg setup_step4
venv\Scripts\python.exe setup_llama.py
if errorlevel 1 goto fail_llama

rem 5. Check the result
call :msg setup_step5
if not exist logs mkdir logs
venv\Scripts\python.exe -c "import faster_whisper, ctranslate2, opencc, huggingface_hub, websockets, numpy" >nul 2>&1
if errorlevel 1 goto fail_check
runtime\llama.cpp\llama-server.exe --version >nul 2>&1
if errorlevel 1 goto fail_check
call :msg setup_check_ok
nvidia-smi >nul 2>&1
if errorlevel 1 call :msg setup_no_nvidia

call :msg setup_done
echo.
pause
exit /b 0

:no_python
call :msg setup_err_python
goto end_fail
:fail_venv
call :msg setup_err_venv
goto end_fail
:fail_pip
call :msg setup_err_pip
goto end_fail
:fail_llama
call :msg setup_err_llama
goto end_fail
:fail_check
call :msg setup_err_check
goto end_fail

:end_fail
echo.
pause
exit /b 1

:msg
type "%~dp0messages\%~1.txt"
exit /b 0
