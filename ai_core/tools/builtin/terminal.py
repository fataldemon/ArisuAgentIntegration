"""Terminal tool — executes allowed commands in a sandboxed subprocess.

Only a curated allowlist of commands can be executed.  All commands run with
the workspace root as their CWD and a 30-second timeout.
"""

import asyncio
import os
import shlex
from tools.registry import get_tool_registry
from tools.schema import PermissionLevel, ToolDef


_ALLOWED_COMMANDS = {
    "python", "python3", "py",
    "pip",
    "node",
    "npm", "npx",
    "git",
    "dir", "ls",
    "echo", "cat", "type",
    "mkdir", "rmdir",
    "where", "which",
}


async def _terminal_command(command: str) -> str:
    if not command or not command.strip():
        return "Error: empty command"

    try:
        argv = shlex.split(command)
    except ValueError as e:
        return f"Error parsing command: {e}"

    if not argv:
        return "Error: empty command"

    base = os.path.basename(argv[0]).lower()
    if base not in _ALLOWED_COMMANDS and argv[0].lower() not in _ALLOWED_COMMANDS:
        return f"Error: command {argv[0]!r} is not in the allowlist. Allowed: {', '.join(sorted(_ALLOWED_COMMANDS))}"

    cwd = os.environ.get("TOOL_WORKSPACE", os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "game_workspace",
    ))
    os.makedirs(cwd, exist_ok=True)

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    except asyncio.TimeoutError:
        return f"Error: command timed out after 30s — {command!r}"
    except FileNotFoundError:
        return f"Error: command not found — {argv[0]!r}"
    except OSError as e:
        return f"Error executing command: {e}"

    out = stdout.decode("utf-8", errors="replace").strip()
    err = stderr.decode("utf-8", errors="replace").strip()
    parts = []
    if out:
        parts.append(out)
    if err:
        parts.append(f"[stderr]\n{err}")
    if proc.returncode is not None and proc.returncode != 0:
        parts.append(f"[exit code: {proc.returncode}]")
    return "\n".join(parts) if parts else "(no output)"


def register() -> None:
    get_tool_registry().register(ToolDef(
        name="terminal_command",
        description=(
            "在工作空间目录执行安全的终端命令（超时30秒）。仅允许以下命令："
            f"{', '.join(sorted(_ALLOWED_COMMANDS))}。"
            "可用于运行脚本、管理版本、查看文件等。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的完整命令，如 'python main.py' 或 'git status' 或 'ls'。",
                },
            },
            "required": ["command"],
        },
        permission_level=PermissionLevel.CONTROL,
        handler=_terminal_command,
        group="system",
        category="终端命令",
        guidance="要运行脚本/做版本管理/装依赖/查文件 → terminal_command（工作目录为工作空间，超时30秒，仅白名单）",
    ))
