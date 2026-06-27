#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "  ArisuAgentIntegration Launcher"
echo "========================================"
echo

# --- Check Node.js ---
if ! command -v node &> /dev/null; then
    echo "[ERROR] Node.js not found. Please install Node.js 18+ from https://nodejs.org"
    exit 1
fi
echo "[OK] Node.js found."

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

# --- Frontend build ---
if [ ! -f "ai_core/web/dist/.installed" ]; then
    echo
    echo "[Frontend] Installing dependencies ..."
    cd ai_core/web
    npm install
    echo "[Frontend] Building ..."
    npm run build
    mkdir -p dist
    touch dist/.installed
    cd "$SCRIPT_DIR"
    echo "[Frontend] Done."
fi

# --- SearXNG (optional, powers web_search) ---
if command -v docker &> /dev/null; then
    docker start searxng > /dev/null 2>&1 || docker run -d --name searxng -p 8888:8080 -v "$SCRIPT_DIR/searxng/settings.yml:/etc/searxng/settings.yml" searxng/searxng > /dev/null 2>&1
    echo "[OK] SearXNG on http://localhost:8888 (web search)"
else
    echo "[SKIP] Docker not found - SearXNG (web search) disabled. Install Docker to enable web_search."
fi

echo
echo "========================================"
echo "[RUN] Starting AI Core ..."
echo "       Admin UI : http://localhost:8000/admin"
echo "       Press Ctrl+C to stop."
echo "========================================"
echo
./venv/bin/python run.py
