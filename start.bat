@echo off
setlocal EnableDelayedExpansion
title ArisuAgentIntegration
cd /d "%~dp0"

echo ========================================
echo   ArisuAgentIntegration Launcher
echo ========================================
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in PATH.
    echo Please install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)
echo [OK] Python found.

:: ---------- Check Node.js ----------
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found in PATH.
    echo Please install Node.js 18+ from https://nodejs.org
    pause
    exit /b 1
)
echo [OK] Node.js found.

:: ---------- AI Core venv ----------
if not exist "venv\.installed" (
    echo.
    echo [AI Core] Creating venv ...
    python -m venv venv
    if %errorlevel% neq 0 (echo [ERROR] Failed. & pause & exit /b 1)
    echo [AI Core] Installing dependencies ...
    venv\Scripts\python.exe -m pip install --upgrade pip
    venv\Scripts\python.exe -m pip install -r requirements.txt
    if %errorlevel% neq 0 (echo [ERROR] Failed. & pause & exit /b 1)
    echo. > "venv\.installed"
    echo [AI Core] Done.
)

:: ---------- QQ Bot venv ----------
if not exist "qq_bot\.venv\.installed" (
    echo.
    echo [QQ Bot] Creating venv ...
    python -m venv qq_bot\.venv
    if %errorlevel% neq 0 (echo [ERROR] Failed. & pause & exit /b 1)
    echo [QQ Bot] Installing dependencies ...
    qq_bot\.venv\Scripts\python.exe -m pip install --upgrade pip
    qq_bot\.venv\Scripts\python.exe -m pip install -r qq_bot\requirements.txt
    if %errorlevel% neq 0 (echo [ERROR] Failed. & pause & exit /b 1)
    echo. > "qq_bot\.venv\.installed"
    echo [QQ Bot] Done.
)

:: ---------- Bilibili venv ----------
if not exist "bilibili\.venv\.installed" (
    echo.
    echo [Bilibili] Creating venv ...
    python -m venv bilibili\.venv
    if %errorlevel% neq 0 (echo [ERROR] Failed. & pause & exit /b 1)
    echo [Bilibili] Installing dependencies ...
    bilibili\.venv\Scripts\python.exe -m pip install --upgrade pip
    bilibili\.venv\Scripts\python.exe -m pip install -r bilibili\requirements.txt
    if %errorlevel% neq 0 (echo [ERROR] Failed. & pause & exit /b 1)
    echo. > "bilibili\.venv\.installed"
    echo [Bilibili] Done.
)

:: ---------- Frontend build ----------
if not exist "ai_core\web\dist\.installed" (
    echo.
    echo [Frontend] Installing dependencies ...
    pushd ai_core\web
    call npm install
    if %errorlevel% neq 0 (echo [ERROR] npm install failed. & popd & pause & exit /b 1)
    echo [Frontend] Building ...
    call npm run build
    if %errorlevel% neq 0 (echo [ERROR] npm build failed. & popd & pause & exit /b 1)
    popd
    echo. > "ai_core\web\dist\.installed"
    echo [Frontend] Done.
)

:: ---------- SearXNG (optional, powers web_search) ----------
where docker >nul 2>&1
if %errorlevel% equ 0 (
    docker start searxng >nul 2>&1
    if %errorlevel% neq 0 (
        echo [SearXNG] Creating container ...
        docker run -d --name searxng -p 8888:8080 -v "%~dp0searxng\settings.yml:/etc/searxng/settings.yml" searxng/searxng >nul 2>&1
    )
    echo [OK] SearXNG on http://localhost:8888 ^(web search^)
) else (
    echo [SKIP] Docker not found - SearXNG ^(web search^) disabled. Install Docker to enable web_search.
)

echo.
echo ========================================
echo [RUN] Starting AI Core ...
echo        Admin UI : http://localhost:8000/admin
echo        Press Ctrl+C to stop.
echo ========================================
echo.
venv\Scripts\python.exe run.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] AI Core exited with code %errorlevel%.
    pause
)
