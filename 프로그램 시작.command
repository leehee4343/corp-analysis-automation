#!/bin/bash
# macOS용 실행 파일 — Finder에서 더블클릭하면 터미널 창이 열리며 서버가 뜬다.
# Windows용 프로그램 시작.bat / run.bat과 같은 역할(처음 실행 시 환경 자동 준비 → 서버 기동 → 브라우저 오픈).
# 시스템 Python(3.9)으로는 동작하지 않아(3.10+ 필요) uv로 Python 3.12 가상환경을 만든다.
cd "$(dirname "$0")" || exit 1
# Finder에서 더블클릭하면 셸 설정의 PATH가 적용되지 않아 사용자 폴더에 설치한 uv·tesseract를 못 찾는다.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"
# .env에 DATABASE_URL이 있으면 Supabase(DB + Storage, 영구 저장)를, 없으면 로컬 SQLite(data/companies.db)를 쓴다.
# 앱 실행에 필요한 값만 내보낸다(관리용 토큰·API 키는 내보내지 않음). APP_LOGIN_PASSWORD가 있으면 로그인 화면이 켜진다.
if [ -f .env ]; then
    for key in DATABASE_URL SUPABASE_URL SUPABASE_PUBLISHABLE_KEY STORAGE_BUCKET STORAGE_SERVICE_EMAIL STORAGE_SERVICE_PASSWORD APP_LOGIN_PASSWORD APP_LOGIN_USER; do
        value="$(grep "^${key}=" .env | head -1 | cut -d= -f2-)"
        [ -n "$value" ] && export "${key}=${value}"
    done
fi

UV="$HOME/.local/bin/uv"
# 이 맥에서는 8000번을 다른 프로젝트 서버가 쓰고 있어 8700번을 쓴다.
PORT=8700
URL="http://127.0.0.1:$PORT"

if lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
    if curl -sf "$URL/api/session" >/dev/null 2>&1; then  # 로그인 없이 열리는 확인용 주소
        echo "Server is already running. Opening browser..."
        open "$URL"
        exit 0
    fi
    echo "Port $PORT is used by another program. Close it or change PORT in this file."
    read -r -p "Press Enter to close"
    exit 1
fi

if [ ! -x .venv/bin/python ]; then
    if [ ! -x "$UV" ]; then
        echo "[1/3] Installing uv (Python manager)..."
        curl -LsSf https://astral.sh/uv/install.sh | UV_NO_MODIFY_PATH=1 sh || { echo "uv install failed."; read -r -p "Press Enter to close"; exit 1; }
    fi
    echo "[1/3] Creating virtual environment (Python 3.12)..."
    "$UV" venv --python 3.12 .venv || { echo "venv creation failed."; read -r -p "Press Enter to close"; exit 1; }
fi

echo "[2/3] Checking required packages..."
if [ -x "$UV" ]; then
    "$UV" pip install -q --python .venv/bin/python -r requirements.txt
else
    .venv/bin/python -m pip install -q -r requirements.txt
fi

if command -v tesseract >/dev/null 2>&1; then
    if [ ! -d .tessdata ]; then
        echo "[3/3] Preparing Korean OCR data..."
        .venv/bin/python setup_tessdata.py
    fi
else
    echo
    echo "[WARNING] Tesseract-OCR is not installed."
    echo "          Credit-grade/EW-grade recognition will not work. See README.md for setup."
    echo
fi

echo
echo "Starting server. Your browser will open automatically in a moment..."
echo "Close this window (or press Ctrl+C) to stop."
echo
(sleep 2 && open "$URL") &
exec .venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port $PORT
