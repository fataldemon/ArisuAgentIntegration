"""Capability-based permission catalog for built-in tools.

Authorization is expressed per *capability* (an operation class, optionally
scoped), not per tool name. Each capability has a global state:

  allow  -> auto-execute (no prompt)
  ask    -> execute only after human confirmation
  deny   -> not available (the tool is not advertised to the model)

File tools span two capabilities depending on the ``scope`` argument they
receive (``workspace`` vs ``system``). :func:`resolve_capability` picks the
right capability for a concrete call; :func:`all_capabilities_for` returns
every capability a tool might touch (used to decide whether to advertise it).

The catalog is the single source of truth shared by:
  * the admin WebUI (permission management page),
  * ``llm/chat.py`` (advertising + agent-loop authorization),
  * ``main.py`` ``/v1/tools/execute`` (confirmation gating).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

STATE_ALLOW = "allow"
STATE_ASK = "ask"
STATE_DENY = "deny"
VALID_STATES = (STATE_ALLOW, STATE_ASK, STATE_DENY)


@dataclass
class Capability:
    key: str          # e.g. "file.read.workspace"
    display: str      # e.g. "读取（工作空间内）"
    domain: str       # e.g. "文件"
    description: str
    default_state: str = STATE_ASK


CAPABILITIES: List[Capability] = [
    Capability("file.read.workspace", "读取（工作空间内）", "文件",
               "读取工作空间内的文件、目录，或在工作空间内搜索文件/内容", STATE_ALLOW),
    Capability("file.write.workspace", "写入（工作空间内）", "文件",
               "在工作空间内创建、修改或删除文件", STATE_ASK),
    Capability("shell.exec", "执行命令", "终端",
               "执行终端命令（受命令白名单限制）", STATE_ASK),
    Capability("desktop.observe", "查看", "桌面",
               "截屏、列出窗口、获取前台窗口", STATE_ALLOW),
    Capability("desktop.control", "控制", "桌面",
               "点击、输入文字、滚动、按键、拖拽", STATE_ASK),
    Capability("process.observe", "查看", "进程",
               "列出进程、查看进程详细信息", STATE_ALLOW),
    Capability("process.control", "控制", "进程",
               "终止进程", STATE_ASK),
    Capability("skill.read", "读取", "技能",
               "列出/阅读技能模块文档", STATE_ALLOW),
    Capability("test.run", "执行", "测试",
               "运行测试工具", STATE_ALLOW),
]

DOMAIN_ORDER: List[str] = ["文件", "终端", "桌面", "进程", "技能", "测试"]

_CAP_BY_KEY: Dict[str, Capability] = {c.key: c for c in CAPABILITIES}


def get_capability(key: str) -> Optional[Capability]:
    return _CAP_BY_KEY.get(key)


def default_states() -> Dict[str, str]:
    """Default ``allow/ask/deny`` for every capability (used on first init)."""
    return {c.key: c.default_state for c in CAPABILITIES}


# ----- tool -> capability mapping ----------------------------------------

FILE_READ_TOOLS = {"read_file", "list_directory", "search_files", "search_content"}
FILE_WRITE_TOOLS = {"write_file", "edit_file", "delete_file"}

_STATIC_CAPABILITY: Dict[str, str] = {
    "terminal_command": "shell.exec",
    "screenshot": "desktop.observe",
    "list_windows": "desktop.observe",
    "get_active_window": "desktop.observe",
    "click": "desktop.control",
    "type_text": "desktop.control",
    "scroll": "desktop.control",
    "press_keys": "desktop.control",
    "drag": "desktop.control",
    "list_processes": "process.observe",
    "get_process_info": "process.observe",
    "kill_process": "process.control",
    "list_skills": "skill.read",
    "read_skill": "skill.read",
    "echo": "test.run",
}


def resolve_capability(tool_name: str, arguments: Optional[Dict] = None) -> str:
    """Capability required by this concrete call.

    File tools depend on the ``scope`` argument (workspace vs system); every
    other tool maps to a single static capability.
    """
    arguments = arguments or {}
    scope = arguments.get("scope", "workspace")
    if tool_name in FILE_READ_TOOLS:
        return "file.read.system" if scope == "system" else "file.read.workspace"
    if tool_name in FILE_WRITE_TOOLS:
        return "file.write.system" if scope == "system" else "file.write.workspace"
    return _STATIC_CAPABILITY.get(tool_name, "")


def all_capabilities_for(tool_name: str) -> List[str]:
    """Every capability a tool might require (for advertising decisions)."""
    if tool_name in FILE_READ_TOOLS:
        return ["file.read.workspace", "file.read.system"]
    if tool_name in FILE_WRITE_TOOLS:
        return ["file.write.workspace", "file.write.system"]
    cap = _STATIC_CAPABILITY.get(tool_name)
    return [cap] if cap else []


def tools_for_capability(cap_key: str) -> List[str]:
    """Inverse mapping: which tools may use this capability (for the UI)."""
    out = []
    for t in FILE_READ_TOOLS:
        if cap_key in ("file.read.workspace", "file.read.system"):
            out.append(t)
    for t in FILE_WRITE_TOOLS:
        if cap_key in ("file.write.workspace", "file.write.system"):
            out.append(t)
    for t, cap in _STATIC_CAPABILITY.items():
        if cap == cap_key:
            out.append(t)
    return sorted(out)
