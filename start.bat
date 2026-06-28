@echo off
setlocal EnableDelayedExpansion
title ArisuAgentIntegration
cd /d "%~dp0"

echo ========================================
echo   ArisuAgentIntegration Launcher
echo ========================================
echo [%date% %time%] Start
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
echo.

:: NOTE: venvs are created once but `pip install -r` runs EVERY launch so that
:: newly added requirements (e.g. playwright, trafilatura) are always synced.
:: This keeps start.bat the single source of truth for setup.

:: ---------- AI Core venv ----------
if not exist "venv\Scripts\python.exe" (
    echo [AI Core] Creating venv ...
    python -m venv venv
    if %errorlevel% neq 0 (echo [ERROR] venv creation failed. & pause & exit /b 1)
    venv\Scripts\python.exe -m pip install --upgrade pip >nul
)
echo [AI Core] Syncing dependencies ...
venv\Scripts\python.exe -m pip install -r requirements.txt
if %errorlevel% neq 0 (echo [ERROR] AI Core pip install failed. & pause & exit /b 1)

:: ---------- Chromium for the CDP browser (only if no system Chrome) ----------
set "PF86=%ProgramFiles(x86)%"
set "HAS_CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "HAS_CHROME=1"
if exist "%PF86%\Google\Chrome\Application\chrome.exe" set "HAS_CHROME=1"
if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "HAS_CHROME=1"
if not defined HAS_CHROME (
    echo [Browser] No system Chrome found; installing Playwright Chromium for web tools ...
    venv\Scripts\python.exe -m playwright install chromium
)

:: ---------- QQ Bot venv ----------
if not exist "qq_bot\.venv\Scripts\python.exe" (
    echo.
    echo [QQ Bot] Creating venv ...
    python -m venv qq_bot\.venv
    if %errorlevel% neq 0 (echo [ERROR] venv creation failed. & pause & exit /b 1)
    qq_bot\.venv\Scripts\python.exe -m pip install --upgrade pip >nul
)
echo [QQ Bot] Syncing dependencies ...
qq_bot\.venv\Scripts\python.exe -m pip install -r qq_bot\requirements.txt
if %errorlevel% neq 0 (echo [ERROR] QQ Bot pip install failed. & pause & exit /b 1)

:: ---------- Bilibili venv ----------
if not exist "bilibili\.venv\Scripts\python.exe" (
    echo.
    echo [Bilibili] Creating venv ...
    python -m venv bilibili\.venv
    if %errorlevel% neq 0 (echo [ERROR] venv creation failed. & pause & exit /b 1)
    bilibili\.venv\Scripts\python.exe -m pip install --upgrade pip >nul
)
echo [Bilibili] Syncing dependencies ...
bilibili\.venv\Scripts\python.exe -m pip install -r bilibili\requirements.txt
if %errorlevel% neq 0 (echo [ERROR] Bilibili pip install failed. & pause & exit /b 1)

:: ---------- Frontend build ----------
echo.
echo [Frontend] Installing + building ...
pushd ai_core\web
call npm install
if %errorlevel% neq 0 (echo [ERROR] npm install failed. & popd & pause & exit /b 1)
call npm run build
if %errorlevel% neq 0 (echo [ERROR] npm build failed. & popd & pause & exit /b 1)
popd

echo.
echo ========================================
echo [RUN] Starting AI Core ...
echo        Admin UI : http://localhost:8000/admin
echo        Press Ctrl+C to stop.
echo ========================================
echo.
venv\Scripts\python.exe run.py

echo.
echo [%date% %time%] AI Core exited (code %errorlevel%).
echo ========================================
echo Press any key to close this window.
echo ========================================
pause >nul
