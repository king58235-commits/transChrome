@echo off
rem transChrome uninstall: removes what setup.bat / start.bat created inside
rem this folder, and (only if confirmed) transChrome's own model folders in the
rem Hugging Face cache. Never the whole cache, the source code, or anything
rem system-wide. Never deletes the project folder itself.
rem ASCII only on purpose; user-facing text is in messages\*.txt (see setup.bat).
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title transChrome Uninstall

call :msg uninstall_intro
set "ANS="
set /p "ANS=[Y/N] "
if /i not "!ANS!"=="Y" goto cancelled

rem Refuse while the backend or its llama-server is still running: files in
rem use can't be deleted and a half-removed install would be broken.
set "RUNNING="
for /f "tokens=5" %%p in ('netstat -ano -p tcp ^| findstr /C:"127.0.0.1:8765 " /C:"127.0.0.1:8790 " ^| findstr LISTENING') do set "RUNNING=%%p"
if defined RUNNING (
    call :msg uninstall_running
    echo   PID !RUNNING!
    goto end
)

echo.
for %%d in (venv runtime logs recordings) do (
    if exist "%%d" (
        rmdir /s /q "%%d"
        if exist "%%d" (echo   [FAILED] backend\%%d) else (echo   removed backend\%%d)
    )
)
for /d /r %%d in (__pycache__) do if exist "%%d" rmdir /s /q "%%d"
del /q benchmark\*.log benchmark\*.json benchmark\*.wav benchmark\stt_compare*.txt 2>nul
echo   removed __pycache__ and temporary outputs

rem AI models: resolve the Hugging Face hub cache like huggingface_hub does
rem (HF_HUB_CACHE, then HF_HOME\hub, then the default under the user profile).
if defined HF_HUB_CACHE (
    set "HUB=%HF_HUB_CACHE%"
) else if defined HF_HOME (
    set "HUB=%HF_HOME%\hub"
) else (
    set "HUB=%USERPROFILE%\.cache\huggingface\hub"
)
set "M1=models--kotoba-tech--kotoba-whisper-v2.0-faster"
set "M2=models--SakuraLLM--Sakura-7B-Qwen2.5-v1.0-GGUF"
set "M3=models--Heng666--madlad400-3b-mt-ct2-int8"

call :msg uninstall_models_header
echo   !HUB!
set "FOUND="
if exist "!HUB!\!M1!" (echo     Kotoba STT            !M1!& set "FOUND=1")
if exist "!HUB!\!M2!" (echo     Sakura-7B             !M2!& set "FOUND=1")
if exist "!HUB!\!M3!" (echo     MADLAD, legacy        !M3!& set "FOUND=1")
if not defined FOUND (
    call :msg uninstall_models_none
    goto done
)
call :msg uninstall_models_ask
set "ANS="
set /p "ANS=[Y/N] "
if /i not "!ANS!"=="Y" (
    call :msg uninstall_models_kept
    goto done
)
for %%m in ("!M1!" "!M2!" "!M3!") do (
    if exist "!HUB!\%%~m" (
        rmdir /s /q "!HUB!\%%~m"
        if exist "!HUB!\%%~m" (echo   [FAILED] %%~m) else (echo   removed %%~m)
    )
)

:done
call :msg uninstall_done
goto end

:cancelled
call :msg uninstall_cancelled

:end
echo.
pause
exit /b 0

:msg
type "%~dp0messages\%~1.txt"
exit /b 0
