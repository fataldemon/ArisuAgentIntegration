"""Admin REST routes.

Every route under ``/admin/api/*`` is meant to be called from the Gradio UI
(or any other admin client). Routes are intentionally kept JSON-in / JSON-out
with very little input validation -- :mod:`core.config_manager` is the
source of truth for schema invariants, and any error there bubbles up here
as a 400.

There is no authentication on these routes beyond the optional HTTP Basic
middleware in ``main.py``. If you expose ``/admin`` publicly, **set
``--api-auth``**.

Endpoints
---------

Providers:

* ``GET    /admin/api/providers``                  -- list
* ``GET    /admin/api/providers/{name}``           -- detail
* ``PUT    /admin/api/providers/{name}``           -- upsert
* ``DELETE /admin/api/providers/{name}``           -- remove
* ``POST   /admin/api/providers/{name}/activate``  -- make active

MCP:

* ``GET    /admin/api/mcp/servers``                -- list
* ``GET    /admin/api/mcp/servers/{name}``         -- detail
* ``PUT    /admin/api/mcp/servers/{name}``         -- upsert
* ``DELETE /admin/api/mcp/servers/{name}``         -- remove
* ``POST   /admin/api/mcp/mode``                   -- set passthrough/server_side
* ``GET    /admin/api/mcp/health``                 -- connection states

Skills:

* ``GET    /admin/api/skills``                     -- list
* ``GET    /admin/api/skills/{name}``              -- body
* ``POST   /admin/api/skills/reload``              -- rescan disk

Personas (per-character system prompt):

* ``GET    /admin/api/personas``                   -- list characters with persona.json
* ``GET    /admin/api/personas/{character}``       -- detail
* ``PUT    /admin/api/personas/{character}``       -- upsert
* ``DELETE /admin/api/personas/{character}``       -- remove
* ``POST   /admin/api/personas/{character}/preview`` -- render the full system
  prompt that ``chat_on_setting`` would inject (handy when editing in the UI).
  Body: ``{"user_text": "...", "information": "..."}``; both optional.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Body, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse

from core.channel_manager import get_channel_supervisor
from core.config_manager import get_config_manager
from core.mcp_manager import get_mcp_manager
from core.persona_manager import get_persona_manager
from core.skill_manager import get_skill_manager
from llm.backends.registry import invalidate as invalidate_backend

_EMBEDDING_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "embedding"
)
_VLLM_REQUEST_LOG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "logs",
    "vllm_request_log.jsonl",
)


def register_admin_routes(app: FastAPI) -> None:
    """Attach every ``/admin/api/*`` route to ``app``."""

    # ------------------- providers -------------------

    @app.get("/admin/api/providers")
    async def list_providers():
        cm = get_config_manager()
        return {
            "active": cm.get_active_provider_name(),
            "providers": [p.to_dict() | {"name": p.name} for p in cm.list_providers()],
        }

    @app.get("/admin/api/providers/{name}")
    async def get_provider(name: str):
        p = get_config_manager().get_provider(name)
        if p is None:
            raise HTTPException(404, "provider not found")
        return p.to_dict() | {"name": p.name}

    @app.put("/admin/api/providers/{name}")
    async def upsert_provider(name: str, body: Dict[str, Any]):
        try:
            cm = get_config_manager()
            cfg = await cm.upsert_provider(name, body)
            # Drop any cached HTTP client so the new config takes effect on
            # the next request.
            await invalidate_backend(name)
            return cfg.to_dict() | {"name": cfg.name}
        except Exception as e:
            raise HTTPException(400, str(e))

    @app.delete("/admin/api/providers/{name}")
    async def delete_provider(name: str):
        ok = await get_config_manager().delete_provider(name)
        if not ok:
            raise HTTPException(404, "provider not found")
        await invalidate_backend(name)
        return {"ok": True}

    @app.post("/admin/api/providers/{name}/activate")
    async def activate_provider(name: str):
        ok = await get_config_manager().activate_provider(name)
        if not ok:
            raise HTTPException(404, "provider not found")
        return {"ok": True, "active": name}

    # ------------------- mcp -------------------

    @app.get("/admin/api/mcp/servers")
    async def list_mcp_servers():
        cm = get_config_manager()
        return {
            "tool_call_mode": cm.get_mcp_tool_call_mode(),
            "tool_call_timeout": cm.get_mcp_tool_call_timeout(),
            "servers": [s.to_dict() | {"name": s.name} for s in cm.list_mcp_servers()],
        }

    @app.get("/admin/api/mcp/servers/{name}")
    async def get_mcp_server(name: str):
        s = get_config_manager().get_mcp_server(name)
        if s is None:
            raise HTTPException(404, "mcp server not found")
        return s.to_dict() | {"name": s.name}

    @app.put("/admin/api/mcp/servers/{name}")
    async def upsert_mcp_server(name: str, body: Dict[str, Any]):
        try:
            s = await get_config_manager().upsert_mcp_server(name, body)
            # Force a reconnect on next use so toggling ``enabled`` takes
            # effect immediately.
            await get_mcp_manager().invalidate(name)
            return s.to_dict() | {"name": s.name}
        except Exception as e:
            raise HTTPException(400, str(e))

    @app.delete("/admin/api/mcp/servers/{name}")
    async def delete_mcp_server(name: str):
        ok = await get_config_manager().delete_mcp_server(name)
        if not ok:
            raise HTTPException(404, "mcp server not found")
        await get_mcp_manager().invalidate(name)
        return {"ok": True}

    @app.post("/admin/api/mcp/mode")
    async def set_mcp_mode(body: Dict[str, Any]):
        try:
            await get_config_manager().set_mcp_tool_call_mode(body.get("mode", ""))
            return {"ok": True, "mode": body.get("mode")}
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.get("/admin/api/mcp/health")
    async def mcp_health():
        return await get_mcp_manager().health()

    # ------------------- skills -------------------

    @app.get("/admin/api/skills")
    async def list_skills():
        return {"skills": get_skill_manager().list_skills()}

    @app.get("/admin/api/skills/{name}")
    async def read_skill(name: str):
        body = get_skill_manager().read_skill(name)
        if body is None:
            raise HTTPException(404, "skill not found")
        return {"name": name, "body": body}

    @app.post("/admin/api/skills/reload")
    async def reload_skills():
        get_skill_manager().reload()
        return {"ok": True, "skills": get_skill_manager().list_skills()}

    # ------------------- personas -------------------

    @app.get("/admin/api/personas")
    async def list_personas():
        pm = get_persona_manager()
        return {
            "personas": [
                {"character": p.character, **p.to_dict()}
                for p in pm.list_personas()
            ],
        }

    @app.get("/admin/api/personas/{character}")
    async def get_persona(character: str):
        p = get_persona_manager().get_persona(character)
        if p is None:
            raise HTTPException(404, "persona not found")
        return {"character": p.character, **p.to_dict()}

    @app.put("/admin/api/personas/{character}")
    async def upsert_persona(character: str, body: Dict[str, Any]):
        try:
            p = await get_persona_manager().upsert_persona(character, body)
        except Exception as e:
            raise HTTPException(400, str(e))
        return {"character": p.character, **p.to_dict()}

    @app.delete("/admin/api/personas/{character}")
    async def delete_persona(character: str):
        ok = await get_persona_manager().delete_persona(character)
        if not ok:
            raise HTTPException(404, "persona not found")
        return {"ok": True}

    @app.post("/admin/api/personas/{character}/expression/image")
    async def upload_expression_image(character: str, file: UploadFile = File(...)):
        """Upload an emoji image for a character's expressions.

        The image is normalised to the character's ``expression_image_size``
        (longest edge, default 480) and saved as PNG under
        ``embedding/<character>/expression/image/``. Returns the saved
        filename + public URL. The persona's ``expressions`` mapping still
        has to reference this filename (edit persona.json).
        """
        if not character or "/" in character or "\\" in character:
            raise HTTPException(400, "invalid character name")
        from core.expression_image import save_expression_image, expression_image_url

        data = await file.read()
        if not data:
            raise HTTPException(400, "empty file")
        max_size = 480
        p = get_persona_manager().get_persona(character)
        if p is not None:
            try:
                max_size = int(p.extra.get("expression_image_size") or 480)
            except (TypeError, ValueError):
                max_size = 480
        try:
            saved = save_expression_image(
                character, file.filename or "expr.png", data, max_size
            )
        except Exception as e:
            raise HTTPException(400, f"image processing failed: {e}")
        return {
            "ok": True,
            "filename": saved,
            "url": expression_image_url(character, saved),
        }

    @app.get("/admin/characters/{character}/expression/{filename}")
    async def get_expression_image(character: str, filename: str):
        """Serve a character's expression image (shared by Chat UI + QQ bot)."""
        from core.expression_image import expression_image_path

        if "/" in character or "\\" in character or ".." in character:
            raise HTTPException(404, "not found")
        path = expression_image_path(character, filename)  # basename'd internally
        if not os.path.isfile(path):
            raise HTTPException(404, "not found")
        return FileResponse(path)

    # ---- persona character images (no resizing; for image_setting) ----

    _PERSONA_IMAGE_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "embedding",
    )

    @app.post("/admin/api/personas/{character}/image")
    async def upload_persona_image(character: str, file: UploadFile = File(...)):
        """Upload a character image (portrait, illustration, etc.).
        Saved as-is (no resizing) under ``embedding/<character>/image/``."""
        if not character or "/" in character or "\\" in character:
            raise HTTPException(400, "invalid character name")
        data = await file.read()
        if not data:
            raise HTTPException(400, "empty file")
        stem = os.path.splitext(os.path.basename(file.filename or "img.png"))[0]
        safe_name = stem + ".png"
        dest_dir = os.path.join(_PERSONA_IMAGE_DIR, character, "image")
        os.makedirs(dest_dir, exist_ok=True)
        try:
            with open(os.path.join(dest_dir, safe_name), "wb") as f:
                f.write(data)
        except Exception as e:
            raise HTTPException(400, f"image save failed: {e}")
        return {
            "ok": True,
            "filename": safe_name,
            "url": f"/admin/characters/{character}/image/{safe_name}",
        }

    @app.get("/admin/characters/{character}/image/{filename}")
    async def get_persona_image(character: str, filename: str):
        """Serve a character's persona image (portrait etc.)."""
        if "/" in character or "\\" in character or ".." in character:
            raise HTTPException(404, "not found")
        path = os.path.join(
            _PERSONA_IMAGE_DIR, character, "image", os.path.basename(filename)
        )
        if not os.path.isfile(path):
            raise HTTPException(404, "not found")
        return FileResponse(path)

    @app.post("/admin/api/personas/{character}/preview")
    async def preview_persona(character: str, body: Dict[str, Any]):
        """Render the full system prompt that would be injected.

        This is a *dry run*: it calls ``process_embedding`` with whatever
        ``user_text`` the caller supplies (or an empty string), splices the
        result into the persona's ``setting``/``reply_instruction``, and
        returns the final text. No LLM call is made.
        """
        from llm.chat import _build_persona_system_prefix
        from embedding.embedding import process_embedding, remove_reference_url

        user_text = (body.get("user_text") or "").strip()
        information = body.get("information") or ""
        embeddings_text = ""
        if user_text:
            try:
                embeddings_text, _ = process_embedding(
                    content=remove_reference_url(user_text),
                    top_k=5,
                    character=character,
                    client_buffer=[],
                    max_length=8,
                    client_information=information,
                )
            except Exception as e:
                # Fall through with empty embeddings so the user still
                # sees the literal persona text in the preview.
                return {
                    "character": character,
                    "system_prompt": _build_persona_system_prefix(character, ""),
                    "embeddings_text": "",
                    "warning": f"process_embedding failed: {e!r}",
                }
        return {
            "character": character,
            "system_prompt": _build_persona_system_prefix(
                character, embeddings_text
            ),
            "embeddings_text": embeddings_text,
        }

    # ------------------- channels -------------------

    @app.get("/admin/api/channels")
    async def list_channels():
        return {"channels": get_channel_supervisor().list_status()}

    @app.post("/admin/api/channels/{name}/start")
    async def start_channel(name: str):
        ok = await get_channel_supervisor().start_channel(name)
        if not ok:
            raise HTTPException(400, f"failed to start channel '{name}'")
        return {"ok": True, "name": name}

    @app.post("/admin/api/channels/{name}/stop")
    async def stop_channel(name: str):
        ok = await get_channel_supervisor().stop_channel(name)
        if not ok:
            raise HTTPException(404, f"channel '{name}' not running")
        return {"ok": True, "name": name}

    @app.post("/admin/api/channels/{name}/restart")
    async def restart_channel(name: str):
        ok = await get_channel_supervisor().restart_channel(name)
        if not ok:
            raise HTTPException(400, f"failed to restart channel '{name}'")
        return {"ok": True, "name": name}

    @app.get("/admin/api/channels/{name}/log")
    async def channel_log_tail(name: str, lines: int = 200, format: str = ""):
        html = format == "html"
        log_text = get_channel_supervisor().get_log_tail(name, lines, html=html)
        return {"name": name, "log": log_text}

    @app.get("/admin/logs/{channel_name}", response_class=HTMLResponse)
    async def channel_log_viewer(channel_name: str):
        from admin.log_viewer import render_log_viewer

        api_url = f"/admin/api/channels/{channel_name}/log"
        return render_log_viewer(channel_name, api_url)

    # ------------------- expression config -------------------

    @app.get("/admin/api/expression")
    async def get_expression():
        return get_config_manager().get_expression_config().to_dict()

    @app.put("/admin/api/expression")
    async def set_expression(body: Dict[str, Any]):
        fmt = (body.get("format") or "").strip()
        instruction = (body.get("instruction") or "").strip()
        if not fmt:
            raise HTTPException(400, "format must not be empty")
        ec = await get_config_manager().set_expression_config(fmt, instruction)
        return ec.to_dict()

    # ------------------- active character -------------------

    @app.get("/admin/api/characters/active")
    async def get_active_character():
        return {"character": get_config_manager().get_active_character()}

    @app.post("/admin/api/characters/activate")
    async def activate_character(body: Dict[str, Any]):
        character = (body.get("character") or "").strip()
        await get_config_manager().set_active_character(character)
        return {"ok": True, "character": character}

    # ------------------- mcp max tool rounds -------------------

    @app.post("/admin/api/mcp/max-tool-rounds")
    async def set_mcp_max_tool_rounds(body: Dict[str, Any]):
        try:
            rounds = int(body.get("rounds", 5))
            await get_config_manager().set_mcp_max_tool_rounds(rounds)
            return {"ok": True, "rounds": get_config_manager().get_mcp_max_tool_rounds()}
        except (ValueError, TypeError) as e:
            raise HTTPException(400, str(e))

    # ------------------- skills CRUD -------------------

    @app.get("/admin/api/skills/{name}/raw")
    async def read_skill_raw(name: str):
        raw = get_skill_manager().read_skill_raw(name)
        if raw is None:
            raise HTTPException(404, "skill not found")
        return {"name": name, "raw": raw}

    @app.put("/admin/api/skills/{name}")
    async def write_skill(name: str, body: Dict[str, Any]):
        content = body.get("body") or body.get("content") or ""
        ok = get_skill_manager().write_skill(name, content)
        if not ok:
            raise HTTPException(500, f"failed to write skill '{name}'")
        return {"ok": True, "name": name}

    @app.delete("/admin/api/skills/{name}")
    async def delete_skill(name: str):
        ok = get_skill_manager().delete_skill(name)
        if not ok:
            raise HTTPException(404, "skill not found")
        return {"ok": True}

    @app.post("/admin/api/skills")
    async def create_skill(body: Dict[str, Any]):
        name = (body.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "name is required")
        template = (
            f"---\nname: {name}\ndescription: \"\"\n"
            f"version: \"0.1.0\"\nauto_inject: false\n"
            f"triggers:\n  keywords: []\n  regex: []\n---\n"
        )
        content = body.get("body") or body.get("content") or template
        ok = get_skill_manager().write_skill(name, content)
        if not ok:
            raise HTTPException(500, f"failed to create skill '{name}'")
        return {"ok": True, "name": name}

    # ------------------- knowledge base -------------------

    @app.get("/admin/api/kb/characters")
    async def list_kb_characters():
        if not os.path.isdir(_EMBEDDING_ROOT):
            return {"characters": []}
        chars = sorted(
            d for d in os.listdir(_EMBEDDING_ROOT)
            if os.path.isdir(os.path.join(_EMBEDDING_ROOT, d))
            and not d.startswith("__")
            and d != "_shared"
        )
        return {"characters": chars}

    @app.get("/admin/api/kb/{character}/{subject}/files")
    async def list_kb_files(character: str, subject: str):
        subject_dir = os.path.join(_EMBEDDING_ROOT, character, subject)
        if not os.path.isdir(subject_dir):
            return {"files": []}
        files = sorted(f for f in os.listdir(subject_dir) if f.endswith(".mem"))
        return {"files": files}

    @app.get("/admin/api/kb/{character}/{subject}/files/{filename}")
    async def read_kb_file(character: str, subject: str, filename: str):
        filepath = os.path.join(_EMBEDDING_ROOT, character, subject, filename)
        if not os.path.isfile(filepath):
            raise HTTPException(404, "file not found")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return {"filename": filename, "content": f.read()}
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.put("/admin/api/kb/{character}/{subject}/files/{filename}")
    async def save_kb_file(character: str, subject: str, filename: str, body: Dict[str, Any]):
        content = body.get("content", "")
        filepath = os.path.join(_EMBEDDING_ROOT, character, subject, filename)
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            return {"ok": True, "filename": filename}
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.post("/admin/api/kb/{character}/{subject}/files")
    async def create_kb_file(character: str, subject: str, body: Dict[str, Any]):
        filename = (body.get("filename") or "").strip()
        if not filename:
            raise HTTPException(400, "filename is required")
        if not filename.endswith(".mem"):
            filename += ".mem"
        filepath = os.path.join(_EMBEDDING_ROOT, character, subject, filename)
        if os.path.isfile(filepath):
            raise HTTPException(409, f"'{filename}' already exists")
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("")
            return {"ok": True, "filename": filename}
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.delete("/admin/api/kb/{character}/{subject}/files/{filename}")
    async def delete_kb_file(character: str, subject: str, filename: str):
        filepath = os.path.join(_EMBEDDING_ROOT, character, subject, filename)
        if not os.path.isfile(filepath):
            raise HTTPException(404, "file not found")
        try:
            os.remove(filepath)
            return {"ok": True}
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.post("/admin/api/kb/{character}/{subject}/rebuild")
    async def rebuild_kb_index(character: str, subject: str):
        from embedding.embedding import generate_vector
        try:
            result = generate_vector(character, subject)
            return {"ok": True, "result": result}
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.get("/admin/api/kb/{character}/{subject}/index-status")
    async def kb_index_status(character: str, subject: str):
        from embedding.data_store import load_materials, index_path
        p = index_path(character, subject)
        n_vectors = 0
        if os.path.exists(p):
            try:
                import faiss
                idx = faiss.read_index(p)
                n_vectors = int(idx.ntotal)
            except Exception:
                pass
        materials = load_materials(character, subject)
        return {
            "vectors": n_vectors,
            "materials": len(materials),
            "index_file": os.path.basename(p) if os.path.exists(p) else None,
        }

    # ------------------- request monitor -------------------

    @app.get("/admin/api/monitor/log")
    async def get_monitor_log(page: int = -1, page_size: int = 20):
        if not os.path.isfile(_VLLM_REQUEST_LOG_FILE):
            return {"entries": [], "total": 0, "page": 1, "page_size": page_size, "total_pages": 0}
        try:
            all_entries: List[Dict[str, Any]] = []
            with open(_VLLM_REQUEST_LOG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        all_entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            total = len(all_entries)
            total_pages = max(1, (total + page_size - 1) // page_size)
            if page < 0:
                page = total_pages
            page = max(1, min(page, total_pages))
            start = (page - 1) * page_size
            end = start + page_size
            return {
                "entries": all_entries[start:end],
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
            }
        except Exception as e:
            raise HTTPException(500, str(e))

    # ------------------- identity -------------------

    @app.get("/admin/api/identity")
    async def get_identity():
        return {"identity": get_config_manager().get_identity()}

    @app.put("/admin/api/identity")
    async def set_identity(body: Dict[str, Any]):
        identity = (body.get("identity") or "").strip()
        await get_config_manager().set_identity(identity)
        return {"ok": True, "identity": identity}

    # ------------------- globals -------------------

    @app.get("/admin/api/globals")
    async def get_globals():
        return get_config_manager().get_all_globals()

    @app.put("/admin/api/globals")
    async def set_globals(body: Dict[str, Any]):
        variables = body.get("variables", {})
        await get_config_manager().set_globals(variables)
        _propagate_all_mappings()
        return {"ok": True}

    @app.get("/admin/api/globals/flat")
    async def get_globals_flat():
        return {"variables": get_config_manager().get_globals_flat()}

    # ------------------- inference params -------------------

    @app.get("/admin/api/inference")
    async def get_inference():
        return get_config_manager().get_inference_config()

    @app.put("/admin/api/inference")
    async def set_inference(body: Dict[str, Any]):
        result = await get_config_manager().set_inference_config(body)
        return result

    # ------------------- tool capabilities -------------------

    @app.get("/admin/api/tools/capabilities")
    async def get_tool_capabilities():
        from tools.capabilities import CAPABILITIES, DOMAIN_ORDER, tools_for_capability
        cm_cfg = get_config_manager()
        states = cm_cfg.get_capability_states()
        known = ["chat", "default"]
        channel_caps = {ch: sorted(cm_cfg.get_channel_capabilities(ch)) for ch in known}
        return {
            "domains": DOMAIN_ORDER,
            "capabilities": [
                {
                    "key": c.key,
                    "display": c.display,
                    "domain": c.domain,
                    "description": c.description,
                    "default_state": c.default_state,
                    "state": states.get(c.key, c.default_state),
                    "tools": tools_for_capability(c.key),
                }
                for c in CAPABILITIES
            ],
            "channels": channel_caps,
        }

    @app.put("/admin/api/tools/capabilities")
    async def set_tool_capabilities(body: Dict[str, Any]):
        states = body.get("states", {})
        await get_config_manager().set_capability_states(states)
        return {"ok": True}

    @app.put("/admin/api/tools/channels/{channel}")
    async def set_channel_capabilities(channel: str, body: Dict[str, Any]):
        caps = body.get("capabilities", [])
        await get_config_manager().set_channel_capabilities(channel, caps)
        return {"ok": True}

    @app.get("/admin/api/tools/registry")
    async def get_tool_registry_meta():
        from tools.capabilities import all_capabilities_for
        from tools.registry import get_tool_registry
        out = []
        for d in get_tool_registry().list_defs():
            out.append({
                "name": d.name,
                "description": d.description,
                "group": d.group,
                "category": d.category,
                "permission_level": d.permission_level.value,
                "capabilities": all_capabilities_for(d.name),
            })
        return {"tools": out}

    # ------------------- channel config -------------------

    _CHANNELS_FILE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "channels.json"
    )

    def _find_channel_config_path(name: str):
        cs = get_channel_supervisor()
        cfg = cs._configs.get(name)
        if not cfg:
            return None, None
        if cfg.config_file:
            resolved = os.path.expandvars(cfg.config_file)
            resolved = os.path.normpath(resolved)
            if os.path.isfile(resolved):
                ext = os.path.splitext(resolved)[1].lower()
                fmt = "json" if ext == ".json" else "dotenv"
                return resolved, fmt
        cwd = cfg.resolve_cwd()
        if not cwd:
            return None, None
        env_path = os.path.join(cwd, ".env")
        if os.path.isfile(env_path):
            return env_path, "dotenv"
        json_path = os.path.join(cwd, "settings.json")
        if os.path.isfile(json_path):
            return json_path, "json"
        env_example = os.path.join(cwd, ".env.example")
        if os.path.isfile(env_example):
            import shutil
            shutil.copy2(env_example, env_path)
            return env_path, "dotenv"
        return None, None

    def _read_dotenv(path: str) -> Dict[str, str]:
        config: Dict[str, str] = {}
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    config[key.strip()] = value.strip()
        return config

    def _write_dotenv(path: str, config: Dict[str, str]) -> None:
        lines: List[str] = []
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        written_keys: set = set()
        new_lines: List[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.partition("=")[0].strip()
                if key in config:
                    new_lines.append(f"{key}={config[key]}\n")
                    written_keys.add(key)
                else:
                    new_lines.append(line if line.endswith("\n") else line + "\n")
            else:
                new_lines.append(line if line.endswith("\n") else line + "\n")
        for key, value in config.items():
            if key not in written_keys:
                new_lines.append(f"{key}={value}\n")
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    def _read_json_config(path: str) -> Dict[str, Any]:
        for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
            try:
                with open(path, "r", encoding=enc) as f:
                    return json.load(f)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        return {}

    def _write_json_config_safe(path: str, config: Dict[str, Any]) -> None:
        import shutil
        import tempfile
        if os.path.isfile(path):
            shutil.copy2(path, path + ".bak")
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            os.replace(tmp, path)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    def _save_channel_mappings(name: str, mappings: Dict[str, str]) -> None:
        cs = get_channel_supervisor()
        cfg = cs._configs.get(name)
        if cfg:
            cfg.config_mappings = mappings
        try:
            with open(_CHANNELS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            ch = data.get("channels", {}).get(name)
            if ch is not None:
                ch["config_mappings"] = mappings
                with open(_CHANNELS_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _propagate_channel_mapping(name: str) -> None:
        cs = get_channel_supervisor()
        cfg = cs._configs.get(name)
        if not cfg or not cfg.config_mappings:
            return
        path, fmt = _find_channel_config_path(name)
        if not path or fmt != "json":
            return
        cm = get_config_manager()
        try:
            full = _read_json_config(path)
            changed = False
            for key, mapping in cfg.config_mappings.items():
                resolved = cm.resolve_variables(mapping)
                if full.get(key) != resolved:
                    full[key] = resolved
                    changed = True
            if changed:
                _write_json_config_safe(path, full)
        except Exception:
            pass

    def _propagate_all_mappings() -> None:
        cs = get_channel_supervisor()
        for name in cs._configs:
            _propagate_channel_mapping(name)

    @app.get("/admin/api/channels/{name}/config")
    async def get_channel_config(name: str):
        path, fmt = _find_channel_config_path(name)
        if not path:
            raise HTTPException(404, f"no config file found for channel '{name}'")
        try:
            if fmt == "json":
                config = _read_json_config(path)
                if not config:
                    raise HTTPException(500, "cannot decode config file")
            else:
                config = _read_dotenv(path)
                prod_path = os.path.join(os.path.dirname(path), ".env.prod")
                if os.path.isfile(prod_path):
                    config.update(_read_dotenv(prod_path))
            cm = get_config_manager()
            cs = get_channel_supervisor()
            cfg = cs._configs.get(name)
            mappings = cfg.config_mappings if cfg else {}
            display_config = dict(config)
            for key, mapping in mappings.items():
                expected = cm.resolve_variables(mapping)
                actual = config.get(key)
                if actual is not None and str(actual) == str(expected):
                    display_config[key] = mapping
            resolved = {}
            for k, v in display_config.items():
                resolved[k] = cm.resolve_variables(str(v)) if isinstance(v, str) else v
            return {"format": fmt, "config": display_config, "resolved": resolved}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.put("/admin/api/channels/{name}/config")
    async def set_channel_config(name: str, body: Dict[str, Any]):
        path, fmt = _find_channel_config_path(name)
        if not path:
            raise HTTPException(404, f"no config file found for channel '{name}'")
        config = body.get("config", {})
        cm = get_config_manager()
        resolved_config = {}
        new_mappings: Dict[str, str] = {}
        for k, v in config.items():
            sv = str(v) if v is not None else ""
            if "${" in sv:
                new_mappings[k] = sv
                resolved_config[k] = cm.resolve_variables(sv)
            else:
                resolved_config[k] = sv
        try:
            if fmt == "json":
                existing = _read_json_config(path)
                existing.update(resolved_config)
                _write_json_config_safe(path, existing)
                cs = get_channel_supervisor()
                cfg = cs._configs.get(name)
                if cfg:
                    updated_mappings = dict(cfg.config_mappings)
                    for k in config:
                        if k in new_mappings:
                            updated_mappings[k] = new_mappings[k]
                        elif k in updated_mappings:
                            del updated_mappings[k]
                    _save_channel_mappings(name, updated_mappings)
            else:
                env_keys = set(_read_dotenv(path).keys())
                prod_path = os.path.join(os.path.dirname(path), ".env.prod")
                prod_keys = set(_read_dotenv(prod_path).keys()) if os.path.isfile(prod_path) else set()
                env_part = {k: str(v) for k, v in resolved_config.items() if k not in prod_keys}
                prod_part = {k: str(v) for k, v in resolved_config.items() if k in prod_keys}
                if env_part:
                    _write_dotenv(path, env_part)
                if prod_part and os.path.isfile(prod_path):
                    _write_dotenv(prod_path, prod_part)
            return {"ok": True, "name": name}
        except Exception as e:
            raise HTTPException(500, str(e))
