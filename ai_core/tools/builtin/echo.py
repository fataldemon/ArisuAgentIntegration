"""Echo tool — returns the input arguments as a JSON string.

Useful for verifying that the tool-call pipeline is working end-to-end.
"""

import json
from tools.registry import get_tool_registry
from tools.schema import PermissionLevel, ToolDef


async def _echo_handler(message: str = "", **kwargs) -> str:
    data = {"message": message, **kwargs}
    return json.dumps(data, ensure_ascii=False, indent=2)


def register() -> None:
    get_tool_registry().register(ToolDef(
        name="echo",
        description="回显输入参数为JSON字符串。用于测试工具调用管道是否正常工作。",
        parameters={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "要回显的消息。",
                },
            },
            "required": [],
        },
        permission_level=PermissionLevel.READ,
        handler=_echo_handler,
        group="test",
        category="测试",
        guidance="要测试工具调用链路是否正常 → echo",
    ))
