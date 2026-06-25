"""FastAPI surface for hippocampus context operations.

Mounted onto the AI Core app under ``/ctx`` (see ``main.py``). These are
*new* context endpoints; the legacy ``/v1`` and ``/assistant/v1`` chat
routes are untouched.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from hippocampus.context.manager import get_context_manager


class SaveMessageBody(BaseModel):
    role: str
    content: str = ""
    thought: str = ""
    action_name: str = ""
    action_input: str = ""
    request_id: str = ""
    is_summary: int = 0
    append_to_history: bool = True
    max_history: int = 40
    timestamp: Optional[str] = None


class RecallBody(BaseModel):
    time_range: str = ""
    keywords: str = ""
    limit: int = 5
    context_lines: int = 1


class DatasetBody(BaseModel):
    role: str
    content: str
    functions: Optional[List[Dict]] = None
    is_first: bool = False


class DatasetFlushBody(BaseModel):
    embeddings: str = ""


def _serialize_history(history: List[Dict]) -> List[Dict]:
    out = []
    for m in history:
        ts = m.get("_timestamp")
        out.append({
            "role": m.get("role"),
            "content": m.get("content"),
            "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else None,
        })
    return out


def build_router() -> APIRouter:
    router = APIRouter(prefix="/ctx", tags=["hippocampus"])
    cm = get_context_manager()

    @router.get("/sessions")
    async def list_sessions():
        return {"sessions": cm.list_sessions()}

    @router.get("/sessions/list")
    async def list_user_sessions(prefix: str = "chat:"):
        return {"sessions": cm.list_user_sessions(prefix)}

    @router.post("/{sid}/message")
    async def save_message(sid: str, body: SaveMessageBody):
        print(f"[hippocampus] save_message sid={sid} role={body.role}")
        row_id = await cm.save_message(
            session_id=sid,
            role=body.role,
            content=body.content,
            thought=body.thought,
            action_name=body.action_name,
            action_input=body.action_input,
            request_id=body.request_id,
            is_summary=body.is_summary,
            append_to_history=body.append_to_history,
            max_history=body.max_history,
            timestamp=body.timestamp,
        )
        return {"id": row_id}

    @router.get("/{sid}/history")
    async def get_history(sid: str, limit: int = 40):
        history = await cm.load_history(sid, limit=limit)
        return {"session_id": sid, "history": _serialize_history(history)}

    @router.get("/{sid}/turn-context")
    async def turn_context(sid: str, limit: int = 40):
        print(f"[hippocampus] turn_context sid={sid} limit={limit}")
        ctx = await cm.turn_context(sid, max_history=limit)
        return {
            "session_id": sid,
            "history": _serialize_history(ctx["history"]),
            "time_annotation": ctx["time_annotation"],
            "was_reset": ctx["was_reset"],
            "summary": ctx["summary"],
        }

    @router.post("/{sid}/clear")
    async def clear_session(sid: str):
        print(f"[hippocampus] clear sid={sid}")
        await cm.clear_session(sid)
        return {"ok": True}

    @router.post("/{sid}/delete")
    async def delete_session(sid: str):
        print(f"[hippocampus] delete sid={sid}")
        await cm.delete_session(sid)
        return {"ok": True}

    @router.get("/{sid}/time-annotation")
    async def time_annotation(sid: str):
        annotation, was_reset = await cm.build_time_annotation(sid)
        return {"annotation": annotation, "was_reset": was_reset}

    @router.post("/{sid}/recall")
    async def recall(sid: str, body: RecallBody):
        result = await cm.recall(
            session_id=sid,
            time_range=body.time_range,
            keywords=body.keywords,
            limit=body.limit,
            context_lines=body.context_lines,
        )
        return {"result": result}

    @router.post("/{sid}/dataset")
    async def record_dataset(sid: str, body: DatasetBody):
        await cm.record_dataset(
            session_id=sid,
            role=body.role,
            content=body.content,
            functions=body.functions,
            is_first=body.is_first,
        )
        return {"ok": True}

    @router.post("/{sid}/dataset/flush")
    async def flush_dataset(sid: str, body: DatasetFlushBody):
        await cm.flush_dataset(sid, embeddings=body.embeddings)
        return {"ok": True}

    @router.get("/{sid}/session")
    async def get_session_state(sid: str):
        sess = await cm.get_session(sid)
        return {
            "session_id": sess.session_id,
            "summary": sess.summary,
            "last_reply": sess.last_reply.isoformat(),
            "history_len": len(sess.history),
            "max_history": sess.max_history,
            "embedding_buffer": sess.embedding_buffer,
        }

    return router


def register_hippocampus_routes(app) -> None:
    app.include_router(build_router())
