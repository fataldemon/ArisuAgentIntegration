"""Channel subprocess supervisor.

Manages external service processes (QQ bot, Bilibili stream, Unity desktop pet)
as child processes, capturing their stdout/stderr to separate log files.

Does NOT auto-start channels. All control is through the Admin API / WebUI.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

LOG = logging.getLogger(__name__)

_AI_CORE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHANNELS_CONFIG_PATH = os.path.join(_AI_CORE_DIR, "config", "channels.json")


# ---------------------------------------------------------------------------
# Log colourisation for HTML log viewer
# ---------------------------------------------------------------------------

_COLOR_PATTERNS = [
    (re.compile(r'\[(SUCCESS|成功)\]'), '<span style="color:#53d8b2;font-weight:bold">'),
    (re.compile(r'\[(ERROR|错误|FATAL)\]'), '<span style="color:#e94560;font-weight:bold">'),
    (re.compile(r'\[(WARNING|警告|WARN)\]'), '<span style="color:#f0c040;font-weight:bold">'),
    (re.compile(r'\[(INFO|信息)\]'), '<span style="color:#5dade2;font-weight:bold">'),
    (re.compile(r'\[(DEBUG|调试)\]'), '<span style="color:#888">'),
    (re.compile(r'Process exited with code (?!0\b)\d+'), '<span style="color:#e94560">'),
    (re.compile(r'Process exited with code 0'), '<span style="color:#53d8b2">'),
    (re.compile(r'Traceback \(most recent call last\):'), '<span style="color:#e94560;font-weight:bold">'),
    (re.compile(r'ModuleNotFoundError:.*?$', re.MULTILINE), '<span style="color:#e94560;font-weight:bold">'),
]


def _colorize_log(text: str) -> str:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for pattern, tag in _COLOR_PATTERNS:
        def _repl(m, t=tag):
            return f'{t}{m.group(0)}</span>'
        escaped = pattern.sub(_repl, escaped)
    return escaped


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ChannelConfig:
    name: str
    command: str = ""
    args: List[str] = field(default_factory=list)
    python: str = ""
    cwd: str = ""
    env: Dict[str, str] = field(default_factory=dict)
    log_file: str = ""
    restart_on_crash: bool = True
    restart_delay: int = 3
    platforms: List[str] = field(default_factory=list)
    config_file: str = ""
    config_mappings: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "ChannelConfig":
        return cls(
            name=name,
            command=str(data.get("command", "")),
            args=[str(a) for a in data.get("args", [])],
            python=str(data.get("python", "")),
            cwd=str(data.get("cwd", "")),
            env={str(k): str(v) for k, v in data.get("env", {}).items()},
            log_file=str(data.get("log_file", "")),
            restart_on_crash=bool(data.get("restart_on_crash", True)),
            restart_delay=int(data.get("restart_delay", 3)),
            platforms=[str(p) for p in data.get("platforms", [])],
            config_file=str(data.get("config_file", "")),
            config_mappings={str(k): str(v) for k, v in data.get("config_mappings", {}).items()},
        )

    def resolve_cwd(self) -> str:
        if self.cwd and not os.path.isabs(self.cwd):
            return os.path.normpath(os.path.join(_AI_CORE_DIR, self.cwd))
        return self.cwd

    def resolve_log_file(self) -> str:
        if self.log_file and not os.path.isabs(self.log_file):
            return os.path.normpath(os.path.join(_AI_CORE_DIR, self.log_file))
        if self.log_file:
            return self.log_file
        return os.path.join(_AI_CORE_DIR, "logs", f"channel_{self.name}.log")

    def resolve_venv(self) -> str:
        if self.python and not os.path.isabs(self.python):
            return os.path.normpath(os.path.join(_AI_CORE_DIR, self.python))
        return self.python

    @property
    def platform_ok(self) -> bool:
        if not self.platforms:
            return True
        return sys.platform in self.platforms


@dataclass
class ChannelStatus:
    name: str
    running: bool = False
    pid: Optional[int] = None
    started_at: Optional[str] = None
    restart_count: int = 0
    platform_blocked: bool = False


# ---------------------------------------------------------------------------
# ChannelSupervisor
# ---------------------------------------------------------------------------


class ChannelSupervisor:
    """Process-wide singleton managing channel subprocesses."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._configs: Dict[str, ChannelConfig] = {}
        self._processes: Dict[str, asyncio.subprocess.Process] = {}
        self._tasks: Dict[str, List[asyncio.Task]] = {}
        self._status: Dict[str, ChannelStatus] = {}
        self._load_config()

    # ---- config ------------------------------------------------------------

    def _load_config(self) -> None:
        if not os.path.exists(CHANNELS_CONFIG_PATH):
            self._configs = {}
            return
        try:
            with open(CHANNELS_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            LOG.warning("Failed to load channels.json")
            self._configs = {}
            return
        channels = data.get("channels", {}) or {}
        self._configs = {
            name: ChannelConfig.from_dict(name, cfg)
            for name, cfg in channels.items()
        }
        for name in self._configs:
            if name not in self._status:
                self._status[name] = ChannelStatus(
                    name=name,
                    platform_blocked=not self._configs[name].platform_ok,
                )

    # ---- start / stop / restart --------------------------------------------

    async def start_channel(self, name: str) -> bool:
        async with self._lock:
            return await self._start_locked(name)

    @staticmethod
    def _resolve_exe(command: str, cwd: str) -> str:
        if cwd:
            candidate = os.path.join(cwd, command)
            if os.path.isfile(candidate):
                return candidate
        return command

    async def _start_locked(self, name: str) -> bool:
        cfg = self._configs.get(name)
        if cfg is None:
            LOG.warning("Channel %s: config not found", name)
            return False
        if not cfg.platform_ok:
            LOG.warning("Channel %s: blocked on platform %s", name, sys.platform)
            self._status.setdefault(
                name, ChannelStatus(name=name, platform_blocked=True)
            ).platform_blocked = True
            return False
        if name in self._processes and self._processes[name].returncode is None:
            LOG.info("Channel %s: already running (pid=%s)", name, self._processes[name].pid)
            return True

        cwd = cfg.resolve_cwd()
        log_path = cfg.resolve_log_file()
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        if os.path.exists(log_path) and os.path.getsize(log_path) > 0:
            ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            archive = f"{log_path}.{ts}"
            try:
                os.rename(log_path, archive)
            except OSError:
                pass

        env = os.environ.copy()
        env.update(cfg.env)
        if cwd not in sys.path:
            env.setdefault("PYTHONPATH", cwd)
        if cwd:
            env.setdefault("PYTHONPATH",
                           cwd + os.pathsep + env.get("PYTHONPATH", ""))

        venv_dir = cfg.resolve_venv()
        if venv_dir:
            if sys.platform == "win32":
                scripts_path = os.path.join(venv_dir, "Scripts")
            else:
                scripts_path = os.path.join(venv_dir, "bin")
            env["PATH"] = scripts_path + os.pathsep + env.get("PATH", "")
            env["VIRTUAL_ENV"] = venv_dir
            LOG.info("Channel %s: using venv %s", name, venv_dir)

        try:
            from core.config_manager import get_config_manager
            cm = get_config_manager()
            for env_name in (".env", ".env.prod"):
                env_file = os.path.join(cwd, env_name) if cwd else None
                if env_file and os.path.isfile(env_file):
                    with open(env_file, "r", encoding="utf-8") as _f:
                        for _line in _f:
                            _line = _line.strip()
                            if not _line or _line.startswith("#") or "=" not in _line:
                                continue
                            _k, _, _v = _line.partition("=")
                            _resolved = cm.resolve_variables(_v.strip())
                            env[_k.strip()] = _resolved
        except Exception as _e:
            LOG.warning("Channel %s: variable resolution failed: %r", name, _e)

        log_file = open(log_path, "a", encoding="utf-8")
        header = f"\n{'='*60}\n[{datetime.now(timezone.utc).isoformat()}] Channel '{name}' started\n{'='*60}\n"
        log_file.write(header)
        log_file.flush()

        try:
            exe = self._resolve_exe(cfg.command, cwd)
            proc = await asyncio.create_subprocess_exec(
                exe,
                *cfg.args,
                cwd=cwd if cwd else None,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            LOG.warning("Channel %s: executable not found: %s (cwd=%s)", name, cfg.command, cwd)
            log_file.write(f"[ERROR] Executable not found: {cfg.command}\n")
            log_file.write(f"[ERROR] Working directory: {cwd}\n")
            log_file.write(f"[ERROR] Full path: {os.path.join(cwd, cfg.command) if cwd else cfg.command}\n")
            log_file.close()
            return False
        except Exception as e:
            LOG.warning("Channel %s: failed to start: %r", name, e)
            log_file.write(f"[ERROR] {e}\n")
            log_file.close()
            return False

        self._processes[name] = proc
        status = self._status.setdefault(name, ChannelStatus(name=name))
        status.running = True
        status.pid = proc.pid
        status.started_at = datetime.now(timezone.utc).isoformat()
        status.platform_blocked = False

        async def _pipe_reader(stream: asyncio.StreamReader, tag: str) -> None:
            try:
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    try:
                        decoded = line.decode('utf-8')
                    except UnicodeDecodeError:
                        decoded = line.decode('gbk', errors='replace')
                    log_file.write(decoded)
                    log_file.flush()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                LOG.debug("Channel %s %s reader done: %r", name, tag, e)

        t_out = asyncio.create_task(_pipe_reader(proc.stdout, "out"))  # type: ignore[arg-type]
        t_err = asyncio.create_task(_pipe_reader(proc.stderr, "err"))  # type: ignore[arg-type]

        async def _monitor() -> None:
            try:
                rc = await proc.wait()
                log_file.write(
                    f"[{datetime.now().strftime('%H:%M:%S')}] "
                    f"Process exited with code {rc}\n"
                )
                log_file.flush()
                log_file.close()
            except Exception:
                pass
            t_out.cancel()
            t_err.cancel()

            should_restart = False
            async with self._lock:
                if name in self._processes and self._processes[name] is proc:
                    # Still registered as THIS proc => crashed on its own (an
                    # explicit stop would have popped it first). Auto-restart
                    # decision must be captured before we delete the entry.
                    del self._processes[name]
                    status = self._status.get(name)
                    if status:
                        status.running = False
                        status.pid = None
                        status.restart_count += 1
                    if cfg.restart_on_crash and proc.returncode != 0:
                        should_restart = True

            if should_restart:
                delay = cfg.restart_delay
                LOG.info("Channel %s: restarting in %ss (rc=%s)", name, delay, rc)
                await asyncio.sleep(delay)
                await self.start_channel(name)

        self._tasks[name] = [t_out, t_err, asyncio.create_task(_monitor())]
        LOG.info("Channel %s: started (pid=%s)", name, proc.pid)
        return True

    async def stop_channel(self, name: str) -> bool:
        async with self._lock:
            proc = self._processes.get(name)
            if proc is None or proc.returncode is not None:
                return False
            try:
                if sys.platform == "win32":
                    # nb run spawns a child uvicorn that holds the port.
                    # Kill the whole process tree first while the parent is
                    # still alive so /T can walk down to the children.
                    import subprocess
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        capture_output=True,
                    )
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=5)
                    except (asyncio.TimeoutError, ProcessLookupError):
                        pass
                else:
                    proc.terminate()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        LOG.warning("Channel %s: force killing", name)
                        proc.kill()
                        await proc.wait()
            except ProcessLookupError:
                pass
            for t in self._tasks.pop(name, []):
                t.cancel()
            self._processes.pop(name, None)
            status = self._status.get(name)
            if status:
                status.running = False
                status.pid = None
            LOG.info("Channel %s: stopped", name)
            return True

    async def restart_channel(self, name: str) -> bool:
        await self.stop_channel(name)
        await asyncio.sleep(1)
        return await self.start_channel(name)

    async def stop_all(self) -> None:
        names = list(self._configs.keys())
        for name in names:
            await self.stop_channel(name)
        LOG.info("All channels stopped")

    # ---- status / log ------------------------------------------------------

    def list_status(self) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for name, cfg in self._configs.items():
            st = self._status.get(name) or ChannelStatus(
                name=name,
                platform_blocked=not cfg.platform_ok,
            )
            result.append({
                "name": name,
                "running": st.running,
                "pid": st.pid,
                "started_at": st.started_at,
                "restart_count": st.restart_count,
                "platform_blocked": st.platform_blocked,
                "platform_restricted": cfg.platforms if cfg.platforms else None,
                "command": f"{cfg.command} {' '.join(cfg.args)}".strip(),
            })
        return result

    def get_log_tail(self, name: str, lines: int = 200, html: bool = False) -> str:
        cfg = self._configs.get(name)
        if cfg is None:
            return f"Channel '{name}' not found"
        log_path = cfg.resolve_log_file()
        if not os.path.exists(log_path):
            return f"(no log yet -- {log_path})"
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            text = "".join(all_lines[-lines:])
            if html:
                text = _colorize_log(text)
            return text
        except Exception as e:
            return f"(error reading log: {e})"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_singleton: Optional[ChannelSupervisor] = None


def get_channel_supervisor() -> ChannelSupervisor:
    global _singleton
    if _singleton is None:
        _singleton = ChannelSupervisor()
    return _singleton
