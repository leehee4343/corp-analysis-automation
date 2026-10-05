@echo off
REM Kept in sync with the Korean-named launcher file in this same folder
REM (same script, duplicated on purpose for reliability). Update both if
REM you change the setup/run steps here.
setlocal
cd /d "%~dp0"

REM Load Supabase/login settings from .env (same keys as the macOS launcher).
REM Without .env (or DATABASE_URL in it) the app uses local SQLite: data\companies.db.
if exist .env (
    for %%K in (DATABASE_URL SUPABASE_URL SUPABASE_PUBLISHABLE_KEY STORAGE_BUCKET STORAGE_SERVICE_EMAIL STORAGE_SERVICE_PASSWORD APP_LOGIN_PASSWORD APP_LOGIN_USER) do (
        for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
            if "%%A"=="%%K" set "%%A=%%B"
        )
    )
)
if defined DATABASE_URL (echo Data: Supabase) else (echo Data: local SQLite - no DATABASE_URL in .env)

if not exist .venv (
    echo [1/3] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Python was not found. Install it from https://python.org and try again.
        pause
        exit /b 1
    )
)

echo [2/3] Checking required packages...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt

where tesseract >nul 2>nul
if errorlevel 1 (
    if not exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
        echo.
        echo [WARNING] Tesseract-OCR is not installed.
        echo           Credit-grade/EW-grade recognition will not work. See README.md for setup.
        echo.
    )
)

if not exist .tessdata (
    echo [3/3] Preparing Korean OCR data...
    ".venv\Scripts\python.exe" setup_tessdata.py
)

echo.
echo Starting server. Your browser will open automatically in a moment...
echo Press Ctrl+C in this window to stop.
echo.
start "" /min cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8000"
".venv\Scripts\python.exe" -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
