"""CDP-based persistent browser manager for the web tools.

We drive a *real* Chrome/Chromium over the Chrome DevTools Protocol (CDP)
rather than Playwright's bundled automation Chromium, because a vanilla Chrome
is far less likely to be flagged by bot detection (Playwright's Chromium leaks
``navigator.webdriver``, CDC_ host bindings, etc.).

Lifecycle:
* On first use we resolve a Chrome executable (config -> platform detection ->
  auto-installed Playwright Chromium as a fallback), launch it once with
  ``--remote-debugging-port`` and a persistent ``--user-data-dir``, and connect
  via ``connect_over_cdp``. The browser stays up for the process lifetime and
  is reused by every ``access_website`` call (the old code killed it per op,
  which defeated the singleton and the "leave open for the user" use case).
* The browser window is headed by default so the operator can see / browse
  whatever page the model opens (``access_website(url, close=false)``).

Config (env vars, all optional):
* ``BROWSER_CHROME_PATH`` - override the Chrome executable path.
* ``BROWSER_CDP_PORT``    - debug port (default 9222).
* ``BROWSER_HEADLESS``    - "1"/"true" to run headless (server deployments).
* ``BROWSER_PROFILE_DIR`` - profile dir (default <ai_core>/browser_profile).
"""

from __future__ import annotations

import asyncio
import atexit
import base64
import os
import shutil
import socket
import subprocess
import sys
import time
from typing import Optional

import httpx

_LOG_PREFIX = "[browser]"

# Module-level singleton state (lazily initialised under a lock).
_lock = asyncio.Lock()
_chrome_proc: Optional[subprocess.Popen] = None
_playwright = None
_browser = None  # Playwright Browser connected over CDP


def _profile_dir() -> str:
    d = os.environ.get("BROWSER_PROFILE_DIR")
    if d:
        return os.path.abspath(d)
    # <ai_core>/browser_profile
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "browser_profile")


def _candidate_chrome_paths() -> list:
    """Platform-specific real-Chrome executable candidates."""
    plt = sys.platform
    if plt == "win32":
        prog = os.environ.get("ProgramFiles", r"C:\Program Files")
        prog86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        return [
            os.path.join(prog, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(prog86, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local, "Google", "Chrome", "Application", "chrome.exe"),
        ]
    if plt == "darwin":
        return ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    # linux / other
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        p = shutil.which(name)
        if p:
            return [p]
    return []


def _resolve_chrome_path() -> Optional[str]:
    configured = os.environ.get("BROWSER_CHROME_PATH", "").strip()
    if configured and os.path.exists(configured):
        return configured
    for c in _candidate_chrome_paths():
        if c and os.path.exists(c):
            return c
    return None


def _wait_for_port(port: int, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


async def _start() -> None:
    """Launch Chrome (if not already up) and connect over CDP."""
    global _chrome_proc, _playwright, _browser
    from playwright.async_api import async_playwright

    port = int(os.environ.get("BROWSER_CDP_PORT", "9222"))
    headless = os.environ.get("BROWSER_HEADLESS", "").lower() in ("1", "true", "yes")

    # If something already listens on the port (e.g. a user-launched debug
    # Chrome), just connect to it instead of launching a new one.
    port_open = _wait_for_port(port, timeout=0.5)
    if not port_open:
        chrome = _resolve_chrome_path()
        if chrome is None:
            # Fallback: auto-install Playwright Chromium and launch that.
            print(f"{_LOG_PREFIX} no system Chrome found; auto-installing Playwright Chromium ...")
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
            pw = await async_playwright().start()
            try:
                try:
                    chrome = pw.chromium.executable_path
                except Exception:
                    chrome = None
            finally:
                await pw.stop()
            if chrome is None or not os.path.exists(chrome):
                raise RuntimeError(
                    "未找到 Chrome，且无法自动安装 Chromium。请安装 Google Chrome，"
                    "或设置 BROWSER_CHROME_PATH 环境变量。"
                )
            print(f"{_LOG_PREFIX} using Playwright Chromium (less stealthy): {chrome}")

        profile = _profile_dir()
        os.makedirs(profile, exist_ok=True)
        cmd = [
            chrome,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
            "--remote-allow-origins=*",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=Translate",
        ]
        if headless:
            cmd.append("--headless=new")
        _chrome_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        atexit.register(_shutdown)
        if not _wait_for_port(port, timeout=20.0):
            raise RuntimeError(f"Chrome 调试端口 {port} 未就绪，启动失败。")

    if _playwright is None:
        _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")


async def get_browser():
    """Return the shared CDP-connected browser, starting it if necessary."""
    global _browser
    async with _lock:
        if _browser is not None:
            try:
                if _browser.is_connected():
                    return _browser
            except Exception:
                pass
        await _start()
        return _browser


def _shutdown() -> None:
    global _chrome_proc
    if _chrome_proc is not None and _chrome_proc.poll() is None:
        try:
            _chrome_proc.terminate()
            try:
                _chrome_proc.wait(timeout=5)
            except Exception:
                _chrome_proc.kill()
        except Exception:
            pass
    _chrome_proc = None
