"""Built-in tool framework for Arisu AI Core.

This package provides a unified :class:`ToolRegistry` singleton that all
built-in tools register with. The Agent Loop in :mod:`llm.chat` discovers
these tools via :func:`get_tool_registry().list_tools()` and routes
executions through :func:`get_tool_registry().call_tool()`.
"""

from .permissions import PendingManager, PendingRequest, get_pending_manager
from .registry import ToolRegistry, get_tool_registry
from .schema import PermissionLevel, ToolContext, ToolDef, ToolResult

__all__ = [
    "ToolRegistry",
    "get_tool_registry",
    "ToolDef",
    "ToolResult",
    "ToolContext",
    "PermissionLevel",
    "PendingManager",
    "PendingRequest",
    "get_pending_manager",
]
