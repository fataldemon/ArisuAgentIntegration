"""Tool definition and result schemas.

Defines the canonical shape for every built-in tool registered with
:class:`ToolRegistry`. The ``ToolDef`` dataclass mirrors the OpenAI
function-calling format while adding permission metadata so the Agent Loop
can decide whether to auto-execute or ask for human confirmation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict


class PermissionLevel(str, Enum):
    READ = "read"
    WRITE = "write"
    CONTROL = "control"


@dataclass
class ToolGroup:
    """A logical group of tools rendered together in the system prompt.

    Each group carries its own guidance preamble (with an optional
    ``{identity}`` placeholder substituted at render time) and a display order.
    Tools reference a group by its ``name``; only groups that have at least one
    enabled tool are emitted into the prompt.
    """

    name: str
    display: str
    guidance: str
    order: int = 0


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: Dict[str, Any]
    permission_level: PermissionLevel
    handler: Callable[..., Coroutine[Any, Any, str]]
    group: str = "system"
    category: str = ""
    guidance: str = ""


@dataclass
class ToolResult:
    success: bool
    output: str = ""
    error: str = ""


@dataclass
class ToolContext:
    workspace: str = field(default="")
