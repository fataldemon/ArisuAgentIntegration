"""Process management tools — list, inspect, and kill OS processes.

All tools are read-only by default except ``kill_process`` which requires
user confirmation.
"""

import subprocess
import sys
from tools.registry import get_tool_registry
from tools.schema import PermissionLevel, ToolDef


async def _list_processes(filter_name: str = "", limit: int = 50) -> str:
    try:
        if sys.platform == "win32":
            cmd = ["tasklist", "/FO", "CSV", "/NH"]
            if filter_name:
                cmd += ["/FI", f"IMAGENAME eq {filter_name}"]
        else:
            cmd = ["ps", "aux", "--no-headers"]
            if filter_name:
                cmd = ["sh", "-c", f"ps aux --no-headers | grep -i {filter_name}"]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        lines = proc.stdout.strip().split("\n")
        if limit and len(lines) > limit:
            lines = lines[:limit]
            lines.append(f"... (truncated at {limit}, refine filter for more)")
        return "\n".join(lines) if lines else "No processes found."
    except subprocess.TimeoutExpired:
        return "Error: process listing timed out."
    except FileNotFoundError:
        return "Error: system command not found."
    except Exception as e:
        return f"Error listing processes: {e}"


async def _get_process_info(pid: int) -> str:
    try:
        if sys.platform == "win32":
            proc = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH", "/V"],
                                  capture_output=True, text=True, timeout=10)
        else:
            proc = subprocess.run(["ps", "-p", str(pid), "-o", "pid,ppid,user,%cpu,%mem,comm,args"],
                                  capture_output=True, text=True, timeout=10)
        out = proc.stdout.strip()
        return out if out else f"No process found with PID {pid}."
    except subprocess.TimeoutExpired:
        return "Error: process info lookup timed out."
    except Exception as e:
        return f"Error getting process info: {e}"


async def _kill_process(pid: int, force: bool = False) -> str:
    try:
        if sys.platform == "win32":
            flag = "/F" if force else ""
            proc = subprocess.run(["taskkill", "/PID", str(pid), flag] if flag else ["taskkill", "/PID", str(pid)],
                                  capture_output=True, text=True, timeout=10)
        else:
            sig = "-9" if force else "-15"
            proc = subprocess.run(["kill", sig, str(pid)], capture_output=True, text=True, timeout=10)
        out = proc.stdout.strip() or proc.stderr.strip()
        return out or f"Process {pid} terminated."
    except subprocess.TimeoutExpired:
        return "Error: kill operation timed out."
    except Exception as e:
        return f"Error killing process: {e}"


def register() -> None:
    reg = get_tool_registry()
    reg.register(ToolDef(
        name="list_processes",
        description="列出系统中正在运行的进程。可按程序名过滤（如 python.exe、chrome.exe），默认最多返回50条。",
        parameters={
            "type": "object",
            "properties": {
                "filter_name": {"type": "string", "description": "可选，按程序名过滤，如 python.exe。"},
                "limit": {"type": "integer", "description": "最多返回多少条记录，默认50。"},
            },
            "required": [],
        },
        permission_level=PermissionLevel.READ,
        handler=_list_processes,
        group="system",
        category="进程管理",
        guidance="想知道系统在运行什么程序 → list_processes",
    ))
    reg.register(ToolDef(
        name="get_process_info",
        description="根据进程ID（PID）查看某个进程的详细信息，包括内存、CPU占用等。",
        parameters={
            "type": "object",
            "properties": {
                "pid": {"type": "integer", "description": "目标进程的PID。"},
            },
            "required": ["pid"],
        },
        permission_level=PermissionLevel.READ,
        handler=_get_process_info,
        group="system",
        category="进程管理",
        guidance="要看某进程详细信息 → get_process_info（需PID）",
    ))
    reg.register(ToolDef(
        name="kill_process",
        description="终止指定PID的进程。可强制终止（force=true）。请谨慎使用。",
        parameters={
            "type": "object",
            "properties": {
                "pid": {"type": "integer", "description": "要终止的进程PID。"},
                "force": {"type": "boolean", "description": "Force kill (default false)."},
            },
            "required": ["pid"],
        },
        permission_level=PermissionLevel.CONTROL,
        handler=_kill_process,
        group="system",
        category="进程管理",
        guidance="要强制关闭某程序 → kill_process（需PID，谨慎）",
    ))
