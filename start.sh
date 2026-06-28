#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "  ArisuAgentIntegration Launcher"
echo "========================================"
echo

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 not found. Please install Python 3.10+."
    exit 1
fi
echo "[OK] Python found."

if ! command -v node &> /dev/null; then
    echo "[ERROR] Node.js not found. Please install Node.js 18+ from https://nodejs.org"
    exit 1
fi
echo "[OK] Node.js found."
echo

# NOTE: venvs are created once but `pip install -r` runs EVERY launch so newly
# added requirements are always synced. start.sh stays the single source of truth.

# --- AI Core venv ---
if [ ! -x "venv/bin/python" ]; then
    echo "[AI Core] Creating venv ..."
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
fi
echo "[AI Core] Syncing dependencies ..."
./venv/bin/pip install -r requirements.txt

# --- Chromium for the CDP browser (only if no system Chrome) ---
if ! command -v google-chrome &> /dev/null && ! command -v chromium &> /dev/null && ! command -v chromium-browser &> /dev/null; then
    if [ ! -d "/Applications/Google Chrome.app" ]; then
        echo "[Browser] No system Chrome found; installing Playwright Chromium for web tools ..."
        ./venv/bin/python -m playwright install chromium
    fi
fi

# --- QQ Bot venv ---
if [ ! -x "qq_bot/.venv/bin/python" ]; then
    echo
    echo "[QQ Bot] Creating venv ..."
    python3 -m venv qq_bot/.venv
    qq_bot/.venv/bin/pip install --upgrade pip
fi
echo "[QQ Bot] Syncing dependencies ..."
qq_bot/.venv/bin/pip install -r qq_bot/requirements.txt

# --- Bilibili venv ---
if [ ! -x "bilibili/.venv/bin/python" ]; then
    echo
    echo "[Bilibili] Creating venv ..."
    python3 -m venv bilibili/.venv
    bilibili/.venv/bin/pip install --upgrade pip
fi
echo "[Bilibili] Syncing dependencies ..."
bilibili/.venv/bin/pip install -r bilibili/requirements.txt

# --- Frontend build ---
echo
echo "[Frontend] Installing + building ..."
cd ai_core/web
npm install
npm run build
cd "$SCRIPT_DIR"

echo
echo "========================================"
echo "[RUN] Starting AI Core ..."
echo "       Admin UI : http://localhost:8000/admin"
echo "       Press Ctrl+C to stop."
echo "========================================"
echo
./venv/bin/python run.py
