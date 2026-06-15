#!/usr/bin/env bash
# ===  One-click launcher for macOS / Linux  ===
# Run with:  bash start.sh   (or: ./start.sh after chmod +x start.sh)

set -e
cd "$(dirname "$0")"

echo
echo "============================================"
echo "  My Job Apply Agent - starting up"
echo "============================================"
echo

PY=python3
command -v $PY >/dev/null 2>&1 || PY=python

if [ ! -x ".venv/bin/python" ]; then
  echo "[1/3] Creating Python environment..."
  $PY -m venv .venv
fi

echo "[2/3] Installing dependencies (first run can take a few minutes)..."
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt
.venv/bin/python -m playwright install chromium

echo "[3/3] Launching... your browser will open at http://127.0.0.1:8000"
echo
.venv/bin/python run.py
