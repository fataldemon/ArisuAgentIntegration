"""Built-in tool group definitions.

Each group carries its own guidance preamble (with an optional ``{identity}``
placeholder substituted at render time) and a display order. Tools reference a
group by its ``name``; only groups that have at least one enabled tool are
rendered into the system prompt.

Adding a new tool group is a two-step change:
1. Append a :class:`ToolGroup` here.
2. Reference the group ``name`` from the relevant ``ToolDef`` registrations.

Permission control is per-tool today (READ/WRITE/CONTROL); the ``group``
attribute is first-class so per-group permission whitelisting can be layered on
later without touching the schema.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .schema import ToolGroup

TOOL_GROUPS: List[ToolGroup] = [
    ToolGroup(
        name="system",
        display="系统操作",
        order=1,
        guidance=(
            "你可以接入并操作{identity}的电脑——真实地读取与修改文件、运行命令、"
            "查看与控制桌面及进程，作为可靠的助手协助{identity}完成工作。"
            "这些能力真实生效，需要操作时请真正调用对应的工具，而不要只在对话里说“我来帮你做”。"
            "其中只读类（查看、截屏、检索）会自动执行；写入或控制类（修改文件、键鼠操作、运行命令）"
            "会先请{identity}确认后再执行。"
        ),
    ),
    ToolGroup(
        name="web",
        display="网络检索",
        order=2,
        guidance=(
            "你可以联网搜索信息与图片，以及打开网页阅读内容或截图查看页面。"
            "搜索结果或网页截图会直接呈给你（视觉可用时你能看到图片/截图）。"
            "需要查资料、看最新动态、找图片，或访问某个网址时使用。"
            "搜索后如果结果里有值得深入了解的网页，继续调用 access_website 读取完整内容，"
            "再综合回答。不要只凭搜索摘要回答。"
            "如果学到了有价值的新知识，调用 save_knowledge 保存到知识库供以后使用。"
        ),
    ),
    ToolGroup(
        name="memory",
        display="记忆召回",
        order=3,
        guidance=(
            "你可以召回过往的对话片段，涵盖与{identity}以及其他人的交流。"
            "当需要回忆之前聊过的具体内容——某个时间、某个话题、或某人说过的话——时，调用记忆召回。"
        ),
    ),
    ToolGroup(
        name="skills",
        display="技能知识",
        order=4,
        guidance=(
            "系统预置了一些技能模块（能力说明文档）。想了解系统还提供了哪些专业能力、"
            "或查阅某项能力的详细用法时，先列出技能再阅读对应说明。"
        ),
    ),
    ToolGroup(
        name="reminder",
        display="提醒日程",
        order=5,
        guidance="你可以为{identity}设置、查看或取消定时提醒。",
    ),
    ToolGroup(
        name="game",
        display="游戏世界设定",
        order=6,
        guidance=(
            "在基沃托斯，你可以在不同的学校、校区与地点之间移动，也能乘坐铁道往返车站；"
            "这些行动会改变你当前所在的位置。你还可以为其他人起外号，"
            "以及安排自己每日的作息（睡眠与起床时间）。"
        ),
    ),
    ToolGroup(
        name="test",
        display="测试",
        order=7,
        guidance="用于自检工具调用链路是否正常工作。",
    ),
]

_GROUPS_BY_NAME: Dict[str, ToolGroup] = {g.name: g for g in TOOL_GROUPS}


def get_group(name: str) -> Optional[ToolGroup]:
    return _GROUPS_BY_NAME.get(name)


def groups_in_order() -> List[ToolGroup]:
    return sorted(TOOL_GROUPS, key=lambda g: g.order)
