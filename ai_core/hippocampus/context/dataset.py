"""Training-data (JSONL) collection -- ported from the QQ bot's
``src/plugins/dataset_collection.py`` (pure functions, no framework deps).

Records each conversation turn in the ShareGPT-style ``{system, conversations}``
schema and flushes it to a dated ``MyDataset-YYYY-MM-DD.jsonl`` file.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import List

from pydantic import BaseModel

TOOL_DESC = (
    "{name_for_model}: Call this tool to interact with the {name_for_human} API. "
    "What is the {name_for_human} API useful for? {description_for_model} "
    "Parameters: {parameters}"
)

SETTING = """你是爱丽丝，全名是天童爱丽丝，看上去是一个可爱的小女孩，实际上是个机器人。
{embeddings}"""

REACT_INSTRUCTION = """Join the following conversation as best you can. You have access to the following APIs:

{tools_text}

Use the following format:

Conversation: the chat you should reply to
Thought: you should always think about what to answer and what to do
Answer: reply before taking action, mark your emotion in 【】 and movement description in （）
Action: the action to take, should be one of [{tools_name_text}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Answer/Action/Action Input/Observation can be repeated zero or more times)
Thought: I now know the final answer
Final Answer: the final reply according to your last thought, mark your emotion in 【】 and movement description in （）

Begin!"""


class Conversation(BaseModel):
    from_param: str
    value: str


class DataSet(BaseModel):
    system: str
    conversations: List[Conversation]


def create_first_conversation(dialog: dict, functions: list) -> Conversation:
    tools_text = []
    tools_name_text = []
    for func_info in functions or []:
        name = func_info.get("name", "")
        name_m = func_info.get("name_for_model", name)
        name_h = func_info.get("name_for_human", name)
        desc = func_info.get("description", "")
        desc_m = func_info.get("description_for_model", desc)
        tool = TOOL_DESC.format(
            name_for_model=name_m,
            name_for_human=name_h,
            description_for_model=desc_m,
            parameters=json.dumps(func_info.get("parameters", {}), ensure_ascii=False),
        )
        tools_text.append(tool)
        tools_name_text.append(name_m)
    instruction = REACT_INSTRUCTION.format(
        tools_text="\n\n".join(tools_text),
        tools_name_text=", ".join(tools_name_text),
    )
    content = dialog["content"]
    from_param = "human" if dialog["role"] == "user" else "gpt"
    return Conversation(from_param=from_param, value=f"{instruction}\n\nConversation: {content}")


def create_conversation(dialog: dict) -> Conversation:
    content = dialog["content"]
    if dialog["role"] == "user":
        from_param = "human"
    elif dialog["role"] == "assistant":
        from_param = "gpt"
    else:
        from_param = "observation"
    return Conversation(from_param=from_param, value=content)


def construct_dataset(conversations: List[Conversation], embeddings: str) -> DataSet:
    return DataSet(system=SETTING.format(embeddings=embeddings), conversations=list(conversations))


def get_json(conversations: List[Conversation], embeddings: str) -> str:
    dataset = construct_dataset(conversations, embeddings)
    content = json.dumps(dataset.dict(), indent=1, ensure_ascii=False)
    return content.replace('"from_param": ', '"from": ')


def _dataset_dir() -> str:
    # dataset.py -> context -> hippocampus -> ai_core
    here = os.path.abspath(__file__)
    ai_core = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    path = os.environ.get("HIPPOCAMPUS_DATASET_DIR") or os.path.join(ai_core, "logs", "datasets")
    os.makedirs(path, exist_ok=True)
    return path


def record_dialog_in_file(conversations: List[Conversation], embeddings: str = "") -> None:
    if not conversations:
        return
    current_date = datetime.now().strftime("%Y-%m-%d")
    filename = os.path.join(_dataset_dir(), f"MyDataset-{current_date}.jsonl")
    with open(filename, "a", encoding="utf-8") as f:
        f.write(get_json(conversations, embeddings) + "\n")
