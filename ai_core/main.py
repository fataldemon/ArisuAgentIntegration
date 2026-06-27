"""FastAPI application entry point.

Compared to the legacy ``main.py`` (which booted an in-process vLLM
``AsyncLLMEngine``), this version:

* talks to an OpenAI-compatible upstream over HTTP (see :mod:`llm.backends`);
* exposes streaming completions via SSE under the same ``/v1/chat/completions``
  route the existing front-end already uses (the route is now stream-aware
  via the ``stream`` field already declared in :class:`ChatCompletionRequest`);
* keeps every legacy route shape intact so the existing front-end keeps
  working without any code change:

    - ``POST /assistant/v1/chat/completions`` (analysis)
    - ``POST /v1/chat/completions``           (chat, now stream-capable)
    - ``WS   /ws/{ws_mode}``                  (quick-reply)

* adds an admin surface for runtime configuration:

    - ``GET  /admin``                          -- Vue SPA (built from web/)
    - ``GET  /admin/api/providers``            -- list providers
    - ``PUT  /admin/api/providers/{name}``     -- upsert
    - ``DELETE /admin/api/providers/{name}``   -- delete
    - ``POST /admin/api/providers/{name}/activate``
    - ``GET  /admin/api/mcp/servers`` + PUT/DELETE/health
    - ``POST /admin/api/abort/{abort_id}``     -- cooperative abort

* migrates legacy embedding pickles on startup automatically (no-op when
  already migrated).

The old in-process vLLM bootstrap (``vllm_start_engine``) is preserved as
dead code in :mod:`llm.local_llm_manage` for documentation purposes only -- it
is never imported here. Run an external ``vllm serve`` instead and point a
provider at it via :class:`ConfigManager` (default fixture in
``config/providers.example.json``).
"""

from __future__ import annotations

import os
os.environ.setdefault("TRANSFORMERS_OFFLINE", "0")
os.environ.setdefault("HF_HUB_OFFLINE", "0")

import base64
import logging
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sse_starlette.sse import EventSourceResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from admin.routes import register_admin_routes
from core.channel_manager import get_channel_supervisor
from core.config_manager import get_config_manager
from core.mcp_manager import get_mcp_manager
from core.persona_manager import get_persona_manager
from core.skill_manager import get_skill_manager
from embedding.embedding import _get_model
from embedding.migrate import migrate_all
from hippocampus.router import register_hippocampus_routes
from llm.chat import (
    _split_thought_and_answer,
    abort_request,
    chat,
    chat_on_setting,
    chat_on_setting_stream,
    clear_stale_media_cache,
    truncate_vllm_request_log,
)
from models.base import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionResponseChoice,
    ChatMessage,
)
from template import (
    LEGACY_ALICE_IMAGE_SETTING,
    LEGACY_ALICE_REPLY_INSTRUCTION,
    LEGACY_ALICE_SETTING,
    _get_args,
    max_analysis_len,
    max_chat_len,
    max_quick_reply,
)
from tools.permissions import get_pending_manager
from tools.capabilities import resolve_capability
from tools.registry import get_tool_registry
from tools.schema import PermissionLevel
from utils.websocketutils import WebsocketManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

LOG = logging.getLogger(__name__)


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Keeps the legacy HTTP Basic auth behaviour bit-for-bit identical."""

    def __init__(self, app, username: str, password: str):
        super().__init__(app)
        self.required_credentials = base64.b64encode(
            f"{username}:{password}".encode()
        ).decode()

    async def dispatch(self, request: Request, call_next):
        authorization: str = request.headers.get("Authorization")
        if authorization:
            try:
                _schema, credentials = authorization.split()
                if credentials == self.required_credentials:
                    return await call_next(request)
            except ValueError:
                pass
        return Response(status_code=401, headers={"WWW-Authenticate": "Basic"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Eager singletons -- catches obvious config errors on boot.
    cm = get_config_manager()
    get_skill_manager()
    # Register built-in tools on startup.
    try:
        import tools.builtin  # noqa: F401  -- side-effect imports trigger registration
        LOG.info("Built-in tools registered: %d", len(get_tool_registry().list_tools()))
    except Exception as e:
        LOG.warning("Built-in tool registration failed: %r", e)
    persona_manager = get_persona_manager()
    try:
        import sys as _sys
        _db_init_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "db"))
        if _db_init_dir not in _sys.path:
            _sys.path.insert(0, _db_init_dir)
        from init_db import init_database
        _db_url = cm.get_globals_flat().get("DB_URL", "")
        if _db_url:
            _result = init_database(_db_url)
            LOG.info("Database init: %s", _result)
    except Exception as e:
        LOG.warning("Database init failed: %r", e)
    # hippocampus: own chat-history schema + FTS init over the shared db.
    try:
        _hd = cm.get_globals_flat().get("DB_URL", "")
        if _hd:
            os.environ.setdefault("DB_URL", _hd)
        from hippocampus.dao.chat_history import init_fts as _hippo_init_fts
        _hippo_init_fts()
        LOG.info("hippocampus FTS init done")
    except Exception as e:
        LOG.warning("hippocampus FTS init failed: %r", e)
    # Seed the legacy "Tendou Arisu" persona on first boot of an
    # upgraded deployment so existing front-ends keep getting the same
    # character behaviour without manual file authoring. Idempotent.
    try:
        persona_manager.seed_legacy_alice_if_missing(
            character="tendou_arisu",
            display_name="天童爱丽丝",
            setting=LEGACY_ALICE_SETTING,
            reply_instruction=LEGACY_ALICE_REPLY_INSTRUCTION,
            image_setting=LEGACY_ALICE_IMAGE_SETTING,
        )
    except Exception as e:  # pragma: no cover
        LOG.warning("Persona seed failed: %r", e)
    # Best-effort migration; never fatal.
    try:
        summary = migrate_all()
        if summary:
            LOG.info("Embedding migration summary: %s", summary)
    except Exception as e:  # pragma: no cover -- best-effort
        LOG.warning("Embedding migration failed: %r", e)
    # Eager-load embedding model at startup (lazy init otherwise)
    try:
        _get_model()
        LOG.info("Embedding model preloaded")
    except Exception as e:  # pragma: no cover -- best-effort
        LOG.warning("Embedding model preload failed: %r", e)
    # Truncate vLLM request log on every startup for the real-time viewer.
    try:
        truncate_vllm_request_log()
        LOG.info("vLLM request log truncated")
    except Exception as e:  # pragma: no cover
        LOG.warning("Failed to truncate vLLM request log: %r", e)
    try:
        clear_stale_media_cache()
    except Exception as e:
        LOG.warning("Failed to clear stale media cache: %r", e)
    yield
    # Graceful shutdown: stop channels, close MCP sessions, backend HTTP clients.
    try:
        await get_channel_supervisor().stop_all()
    except Exception as e:
        LOG.warning("Channel shutdown failed: %r", e)
    try:
        await get_mcp_manager().shutdown()
    except Exception as e:  # pragma: no cover
        LOG.warning("MCP shutdown failed: %r", e)
    try:
        from llm.backends.registry import invalidate_all

        await invalidate_all()
    except Exception as e:  # pragma: no cover
        LOG.warning("Backend shutdown failed: %r", e)


app = FastAPI(lifespan=lifespan)
websocket_manager = WebsocketManager()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Legacy completion routes (unchanged contract for the existing front-end)
# ---------------------------------------------------------------------------


@app.post("/assistant/v1/chat/completions", response_model=ChatCompletionResponse)
async def completion_without_lora(request: ChatCompletionRequest):
    choice = await chat(request=request, max_tokens=max_analysis_len)
    return ChatCompletionResponse(
        model=request.model, choices=[choice], object="chat.completion"
    )


@app.post("/v1/chat/completions")
async def create_chat_completion(request: ChatCompletionRequest):
    """Non-streaming response by default; streams SSE when ``stream=true``.

    The streaming format follows OpenAI's convention: each SSE ``data:`` line
    carries a ``ChatCompletionResponse`` with ``object="chat.completion.chunk"``,
    terminated by ``data: [DONE]``. This is what every modern OpenAI client
    library and front-end already knows how to consume.
    """
    if request.stream:
        async def _gen():
            try:
                async for resp in chat_on_setting_stream(
                    request=request, max_tokens=max_chat_len, index=0
                ):
                    yield {"data": resp.json()}
                    try:
                        await websocket_manager.broadcast(resp.json())
                    except Exception:
                        pass
            except Exception as e:
                LOG.exception("streaming failure: %r", e)
                yield {"data": '{"error":"stream_failure"}'}
            yield {"data": "[DONE]"}

        return EventSourceResponse(_gen())

    choice = await chat_on_setting(
        request=request, max_tokens=max_chat_len, index=0
    )
    resp = ChatCompletionResponse(
        model=request.model, choices=[choice], object="chat.completion"
    )
    # Keep the WebSocket broadcast contract intact for legacy front-ends.
    await websocket_manager.broadcast(choice.json())
    return ChatCompletionResponse(
        model=request.model, choices=[choice], object="chat.completion"
    )


@app.websocket("/ws/{ws_mode}")
async def websocket_endpoint(ws_mode: str, websocket: WebSocket):
    """Quick-reply WebSocket -- supports non-streaming (legacy) and streaming."""
    await websocket_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json(mode=ws_mode)
            LOG.debug("ws data received: %s", data)
            try:
                request = ChatCompletionRequest.parse_obj(data)
                if request.stream:
                    async for chunk in chat_on_setting_stream(
                        request=request, max_tokens=max_quick_reply, index=1
                    ):
                        await websocket.send_text(chunk.json())
                else:
                    choice = await chat_on_setting(
                        request=request, max_tokens=max_quick_reply, index=1
                    )
                    await websocket.send_text(choice.json())
            except ValidationError as e:
                LOG.warning("ws validation error: %s", e.json())
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)


@app.post("/admin/api/abort/{abort_id}")
async def admin_abort(abort_id: str):
    ok = await abort_request(abort_id)
    if not ok:
        raise HTTPException(status_code=404, detail="abort_id not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin: REST + Vue SPA mount
# ---------------------------------------------------------------------------

@app.post("/v1/tools/execute")
async def tools_execute(body: dict = Body(...)):
    tool_name = body.get("tool_name", "")
    arguments = body.get("arguments", {}) or {}
    confirm = body.get("confirm", True)
    pending_id = body.get("pending_id", "")
    permission_decision = body.get("permission_decision", "")  # "" | "once" | "always"

    reg = get_tool_registry()
    tool = reg.get_tool(tool_name)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_name!r}")

    cm_cfg = get_config_manager()
    cap = resolve_capability(tool_name, arguments)

    # Out-of-workspace file access is governed by per-directory rules, not a
    # global capability state. Deny/allow short-circuit; a miss asks the caller
    # to obtain an explicit decision (allow once / always allow this dir / deny).
    if cap in ("file.read.system", "file.write.system"):
        op = "read" if cap.startswith("file.read") else "write"
        target = arguments.get("filename") or arguments.get("path") or ""
        from tools.file_rules import check_permission, parent_dir_of
        import os as _os
        target_abs = _os.path.realpath(target)
        verdict = check_permission(target_abs, op, cm_cfg.get_file_rules())
        if verdict == "deny":
            return {"success": False, "output": "", "error": f"Path denied by rule: {target_abs}"}
        if verdict == "prompt":
            if permission_decision == "once":
                pass  # execute this once, do not persist
            elif permission_decision == "always":
                await cm_cfg.add_file_rule(op, "allow", parent_dir_of(target_abs))
            else:
                return {
                    "success": False,
                    "output": "",
                    "error": "Out-of-workspace path requires permission",
                    "needs_permission": True,
                    "op": op,
                    "path": target_abs,
                    "dir": parent_dir_of(target_abs),
                }
        # verdict == "allow": execute directly
    else:
        # Global capability authorization (allow/ask/deny).
        state = cm_cfg.get_capability_states().get(cap, "ask")
        if state == "deny":
            return {"success": False, "output": "", "error": f"Capability denied: {cap}"}
        if state == "ask":
            pm = get_pending_manager()
            if pending_id:
                pending = pm.resolve(pending_id, confirm)
                if pending is None:
                    raise HTTPException(status_code=404, detail="Pending request not found or expired")
                if not confirm:
                    return {"success": False, "output": "", "error": "User rejected the operation"}
            elif not confirm:
                return {"success": False, "output": "", "error": "Confirmation required"}
        # state == "allow": execute directly

    result = await reg.call_tool(tool_name, arguments)
    return {
        "success": result.success,
        "output": result.output,
        "error": result.error,
    }


@app.post("/v1/tools/pending")
async def tools_create_pending(body: dict = Body(...)):
    tool_name = body.get("tool_name", "")
    arguments = body.get("arguments", {})
    pending_id = get_pending_manager().create_pending(tool_name, arguments)
    return {"pending_id": pending_id, "tool_name": tool_name}


register_admin_routes(app)
register_hippocampus_routes(app)

_DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "dist")

if os.path.isdir(_DIST_DIR):
    from starlette.staticfiles import StaticFiles
    from starlette.responses import FileResponse

    _assets_dir = os.path.join(_DIST_DIR, "assets")
    if os.path.isdir(_assets_dir):
        app.mount(
            "/admin/assets",
            StaticFiles(directory=_assets_dir),
            name="admin-assets",
        )

    @app.get("/admin")
    async def admin_index():
        return FileResponse(os.path.join(_DIST_DIR, "index.html"))

    @app.get("/admin/{path:path}")
    async def admin_spa_fallback(path: str):
        static_path = os.path.join(_DIST_DIR, path)
        if os.path.isfile(static_path):
            return FileResponse(static_path)
        return FileResponse(os.path.join(_DIST_DIR, "index.html"))

    LOG.info("Admin UI mounted from %s", _DIST_DIR)
else:
    @app.get("/admin")
    async def admin_not_built():
        return Response(
            content=(
                "<h2>Admin UI not built</h2>"
                "<p>Run <code>npm install && npm run build</code> in "
                "<code>ai_core/web/</code> to build the frontend.</p>"
            ),
            media_type="text/html",
        )


if __name__ == "__main__":
    args = _get_args()
    if args.api_auth:
        user, _, pwd = args.api_auth.partition(":")
        app.add_middleware(BasicAuthMiddleware, username=user, password=pwd)
    uvicorn.run(app, host=args.server_name, port=args.server_port, workers=1)
