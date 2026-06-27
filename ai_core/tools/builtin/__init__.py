"""Built-in tools provided by Arisu AI Core.

Each module in this package defines one or more :class:`ToolDef` instances.
Imports trigger registration via each module's ``register()`` function.
"""

import json
from core.skill_manager import get_skill_manager
from tools.registry import get_tool_registry
from tools.schema import PermissionLevel, ToolDef

from . import desktop, echo, filesystem, process, terminal, web

echo.register()
filesystem.register()
terminal.register()
desktop.register()
process.register()
web.register()

_reg = get_tool_registry()

async def _list_skills_handler() -> str:
    sm = get_skill_manager()
    return json.dumps(sm.list_skills(), ensure_ascii=False, indent=2)

async def _read_skill_handler(name: str) -> str:
    sm = get_skill_manager()
    body = sm.read_skill(name)
    return body if body else f"Skill not found: {name!r}"

_reg.register(ToolDef(
    name="list_skills",
    description="列出所有可用的技能模块名称和描述。用于了解系统有哪些专业能力可用。",
    parameters={"type": "object", "properties": {}, "required": []},
    permission_level=PermissionLevel.READ,
    handler=_list_skills_handler,
    group="skills",
    guidance="想知道有哪些可用技能模块 → list_skills",
))
_reg.register(ToolDef(
    name="read_skill",
    description="按名称读取某个技能模块的详细内容和使用说明。",
    parameters={
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
    permission_level=PermissionLevel.READ,
    handler=_read_skill_handler,
    group="skills",
    guidance="要查看某技能的具体内容 → read_skill",
))
