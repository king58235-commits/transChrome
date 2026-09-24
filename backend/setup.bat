@echo off
cd /d "%~dp0"

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo.
        echo Failed to create venv. Make sure Python 3.10+ is installed and on PATH.
        pause
        exit /b 1
    )
)

echo Installing dependencies (this downloads ~1.3GB for GPU support on first run)...
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo Install failed. See the error above.
    pause
    exit /b 1
)

echo.
echo Setup complete. Run start.bat to launch the backend.
pause
