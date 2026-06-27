"""ToolRegistry singleton.

Unified registry for all built-in tools. Follows the same singleton pattern
as :class:`SkillManager` and :class:`MCPManager`.

Usage::

    from tools.registry import get_tool_registry

    reg = get_tool_registry()
    reg.register(tool_def)
    tools = reg.list_tools()          # OpenAI format
    result = await reg.call_tool(name, args)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .schema import PermissionLevel, ToolDef, ToolResult

LOG = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolDef] = {}

    def register(self, tool: ToolDef) -> None:
        if tool.name in self._tools:
            LOG.warning("Tool %r is already registered; overwriting.", tool.name)
        self._tools[tool.name] = tool
        LOG.info("Registered tool: %s (permission=%s)", tool.name, tool.permission_level.value)

    def unregister(self, name: str) -> bool:
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get_tool(self, name: str) -> Optional[ToolDef]:
        return self._tools.get(name)

    def get_permission(self, name: str) -> Optional[PermissionLevel]:
        tool = self._tools.get(name)
        return tool.permission_level if tool else None

    def list_tools(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for tool in self._tools.values():
            out.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
        return out

    def list_defs(self) -> List[ToolDef]:
        """Raw :class:`ToolDef` objects (with group/category/guidance metadata)."""
        return list(self._tools.values())

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(success=False, error=f"Unknown tool: {name!r}")
        try:
            output = await tool.handler(**arguments)
            return ToolResult(success=True, output=output)
        except Exception as exc:
            LOG.warning("Tool %s failed: %r", name, exc)
            return ToolResult(success=False, error=str(exc))


_singleton: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    global _singleton
    if _singleton is None:
        _singleton = ToolRegistry()
    return _singleton
