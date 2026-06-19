#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "  ArisuAgentIntegration Launcher"
echo "========================================"
echo

# --- AI Core venv ---
if [ ! -f "venv/.installed" ]; then
    echo "[AI Core] Creating venv ..."
    python3 -m venv venv
    echo "[AI Core] Installing dependencies ..."
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt
    touch venv/.installed
    echo "[AI Core] Done."
fi

# --- QQ Bot venv ---
if [ ! -f "qq_bot/.venv/.installed" ]; then
    echo
    echo "[QQ Bot] Creating venv ..."
    python3 -m venv qq_bot/.venv
    echo "[QQ Bot] Installing dependencies ..."
    qq_bot/.venv/bin/pip install --upgrade pip
    qq_bot/.venv/bin/pip install -r qq_bot/requirements.txt
    touch qq_bot/.venv/.installed
    echo "[QQ Bot] Done."
fi

# --- Bilibili venv ---
if [ ! -f "bilibili/.venv/.installed" ]; then
    echo
    echo "[Bilibili] Creating venv ..."
    python3 -m venv bilibili/.venv
    echo "[Bilibili] Installing dependencies ..."
    bilibili/.venv/bin/pip install --upgrade pip
    bilibili/.venv/bin/pip install -r bilibili/requirements.txt
    touch bilibili/.venv/.installed
    echo "[Bilibili] Done."
fi

echo
echo "========================================"
echo "[RUN] Starting AI Core ..."
echo "       Admin UI : http://localhost:8000/admin"
echo "       Press Ctrl+C to stop."
echo "========================================"
echo
./venv/bin/python run.py
