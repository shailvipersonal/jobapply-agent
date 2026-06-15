@echo off
REM ===  One-click launcher for Windows  ===
REM Double-click this file to set up (first run) and start the web app.

cd /d "%~dp0"
echo.
echo ============================================
echo   My Job Apply Agent - starting up
echo ============================================
echo.

REM Create a virtual environment the first time.
if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating Python environment...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo ERROR: Python was not found. Install Python 3.10+ from https://python.org
        echo and make sure to tick "Add Python to PATH" during install.
        pause
        exit /b 1
    )
)

REM Install dependencies (quick if already installed).
echo [2/3] Installing dependencies (first run can take a few minutes)...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo ERROR: Could not install dependencies. Check your internet connection.
    pause
    exit /b 1
)

REM Install the browser Playwright needs (no-op if already present).
".venv\Scripts\python.exe" -m playwright install chromium

echo [3/3] Launching... your browser will open at http://127.0.0.1:8000
echo.
".venv\Scripts\python.exe" run.py

pause
