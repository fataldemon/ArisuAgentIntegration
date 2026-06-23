"""HTTP client for the AI Core hippocampus context module.

Used only when the ``USE_HIPPOCAMPUS`` feature flag is on. When off, the QQ
bot keeps its original in-process context handling (Qwen.history etc.) and
none of these functions are called.

Full-delegation model: the QQ bot holds no conversation history of its own;
each LLM request fetches the current turn context from hippocampus and writes
messages back (awaited, so ordering is preserved). Truncation/summary is
self-managed by hippocampus.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp
from dotenv import load_dotenv

load_dotenv()

AI_CORE_URL = os.environ.get("AI_CORE_URL", "http://localhost:8000")
USE_HIPPOCAMPUS = os.environ.get("USE_HIPPOCAMPUS", "0") in ("1", "true", "True")

_TIMEOUT = aiohttp.ClientTimeout(total=30)


def session_id_for(group_id) -> str:
    """Channel-owned session id. QQ uses the bare group id so hippocampus
    reuses the existing t_chat_history rows (no 'forget everything' on cutover)."""
    return str(group_id)


def _parse_ts(value) -> datetime:
    if not value:
        return datetime.now()
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return datetime.now()


async def _get(path: str) -> Dict:
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{AI_CORE_URL}{path}", timeout=_TIMEOUT) as r:
            r.raise_for_status()
            return await r.json()


async def _post(path: str, payload: Optional[Dict] = None) -> Dict:
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{AI_CORE_URL}{path}", json=payload or {}, timeout=_TIMEOUT) as r:
            r.raise_for_status()
            return await r.json()


async def turn_context(sid: str, limit: int = 40) -> Dict:
    """Everything needed to build the next request: history (with datetimes),
    time annotation, and the current summary."""
    print(f"[hippo-client] turn_context sid={sid}")
    data = await _get(f"/ctx/{sid}/turn-context?limit={limit}")
    history = [
        {
            "role": m.get("role"),
            "content": m.get("content"),
            "_timestamp": _parse_ts(m.get("timestamp")),
        }
        for m in data.get("history", [])
    ]
    return {
        "history": history,
        "time_annotation": data.get("time_annotation", ""),
        "was_reset": data.get("was_reset", False),
        "summary": data.get("summary", ""),
    }


async def save_message(
    sid: str,
    role: str,
    content: str = "",
    thought: str = "",
    action_name: str = "",
    action_input: str = "",
    request_id: str = "",
    is_summary: int = 0,
    max_history: int = 40,
) -> int:
    print(f"[hippo-client] save_message sid={sid} role={role} len={len(content)}")
    data = await _post(
        f"/ctx/{sid}/message",
        {
            "role": role,
            "content": content,
            "thought": thought,
            "action_name": action_name,
            "action_input": action_input,
            "request_id": request_id,
            "is_summary": is_summary,
            "max_history": max_history,
        },
    )
    return data.get("id", 0)


async def recall(
    sid: str, time_range: str = "", keywords: str = "", limit: int = 5, context_lines: int = 1
) -> str:
    data = await _post(
        f"/ctx/{sid}/recall",
        {"time_range": time_range, "keywords": keywords, "limit": limit, "context_lines": context_lines},
    )
    return data.get("result", "")


async def clear(sid: str) -> None:
    print(f"[hippo-client] clear sid={sid}")
    await _post(f"/ctx/{sid}/clear", {})


async def list_sessions() -> List[Dict]:
    data = await _get("/ctx/sessions")
    return [
        {"session_id": s.get("session_id"), "last_reply": _parse_ts(s.get("last_reply"))}
        for s in data.get("sessions", [])
    ]


async def record_dataset(
    sid: str, role: str, content: str, functions: Optional[List[Dict]] = None, is_first: bool = False
) -> None:
    await _post(
        f"/ctx/{sid}/dataset",
        {"role": role, "content": content, "functions": functions, "is_first": is_first},
    )


async def flush_dataset(sid: str, embeddings: str = "") -> None:
    await _post(f"/ctx/{sid}/dataset/flush", {"embeddings": embeddings})
