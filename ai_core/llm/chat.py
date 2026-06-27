"""High-level chat orchestration.

This module exposes the two entry points the FastAPI layer used to call on
the legacy in-process branch:

* :func:`chat`            -- analysis-style completions (mirrors the old
  ``/assistant/v1/chat/completions`` route).
* :func:`chat_on_setting` -- character-aware completion with embedding
  augmentation (mirrors ``/v1/chat/completions`` + WebSocket).

Both functions now:

1. Pull the active :class:`LLMBackend` from :mod:`llm.backends.registry`.
2. Run the unified content normalizer so that legacy ``[image,file=...]``
   placeholders and OpenAI-style content arrays produce equivalent prompts.
3. Inject knowledge-base retrieval (``setting`` + ``knowledge``) into the
   system prompt, exactly as the legacy code did.
4. Surface MCP-discovered tools when ``mcp_tool_call_mode == "server_side"``.
5. Support both non-streaming and streaming completion; the streaming variant
   is exposed via :func:`chat_on_setting_stream` returning an async iterator
   of ``ChatCompletionResponse(chunk)`` objects.

The signatures of :func:`chat` and :func:`chat_on_setting` were widened so
the FastAPI layer can keep the same handler body. The ``engine`` /
``autoProcessor`` / ``active_lora_path`` parameters from the legacy signature
are accepted and ignored -- this keeps a smaller diff in ``main.py``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Set, Tuple

from core.config_manager import get_config_manager
from core.content_normalizer import (
    clear_stale_media_cache,
    has_media,
    normalize_content,
    to_openai_content,
)
from core.persona_manager import Persona, get_persona_manager
from embedding.embedding import (
    add_knowledge,
    check_emotion,
    find_material_by_index,
    process_embedding,
    remove_reference_url,
)
from models.base import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionResponseChoice,
    ChatCompletionResponseStreamChoice,
    ChatMessage,
    DeltaMessage,
)
# NOTE: Per-character SETTING / REPLY_INSTRUCTION used to live in
# ``template.py`` as hard-coded strings tied to the "天童爱丽丝" persona.
# They now come from ``embedding/<character>/persona.json`` via
# :mod:`core.persona_manager`. ``template.py`` no longer exports those.

from tools.groups import get_group, groups_in_order
from tools.permissions import get_pending_manager
from tools.capabilities import resolve_capability
from tools.registry import get_tool_registry
from tools.schema import PermissionLevel, ToolDef, ToolGroup
from .backends import get_backend
from .backends.base import GenerationResult, StreamChunk

LOG = logging.getLogger(__name__)

# In-flight requests, keyed by ``abort_id`` (set by the client). Used by
# :func:`abort_request` to flip the cooperative abort flag on the backend.
_active_requests: Dict[str, Tuple[str, str]] = {}  # abort_id -> (provider_name, request_id)

# Chat log file path (rotated on restart; max ~10 MB before truncation).
_CHAT_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
_CHAT_LOG_FILE = os.path.join(_CHAT_LOG_DIR, "chat_log.jsonl")
_CHAT_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_VLLM_REQUEST_LOG_FILE = os.path.join(_CHAT_LOG_DIR, "vllm_request_log.jsonl")

_EMBEDDING_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "embedding")


def _append_chat_log(entry: Dict[str, Any]) -> None:
    """Append one JSON line to the chat log file.

    The file is truncated to roughly ``_CHAT_LOG_MAX_BYTES`` when it grows
    beyond that limit (simple truncation -- we drop the oldest entries).
    """
    try:
        os.makedirs(_CHAT_LOG_DIR, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        # Check size and truncate if needed before appending.
        if os.path.isfile(_CHAT_LOG_FILE):
            try:
                size = os.path.getsize(_CHAT_LOG_FILE)
                if size > _CHAT_LOG_MAX_BYTES:
                    # Keep roughly the last 75% of the file.
                    with open(_CHAT_LOG_FILE, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    keep = int(len(lines) * 0.75)
                    with open(_CHAT_LOG_FILE, "w", encoding="utf-8") as f:
                        f.writelines(lines[-keep:])
            except OSError:
                pass
        with open(_CHAT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        LOG.debug("Failed to write chat log: %r", e)


def _append_vllm_request_log(entry: Dict[str, Any]) -> None:
    """Append one JSON line to the vLLM request log file."""
    try:
        os.makedirs(_CHAT_LOG_DIR, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with open(_VLLM_REQUEST_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        LOG.debug("Failed to write vLLM request log: %r", e)


def truncate_vllm_request_log() -> None:
    """Truncate the vLLM request log file to zero bytes."""
    try:
        os.makedirs(_CHAT_LOG_DIR, exist_ok=True)
        with open(_VLLM_REQUEST_LOG_FILE, "w", encoding="utf-8") as f:
            f.write("")
    except Exception as e:
        LOG.debug("Failed to truncate vLLM request log: %r", e)


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


def _sampling_from_request(req: ChatCompletionRequest, max_tokens: int, mode: str = "chat") -> Dict[str, Any]:
    inference = get_config_manager().get_inference_config()
    mode_params = inference.get(mode, inference.get("chat", {}))
    s: Dict[str, Any] = {"max_tokens": max_tokens}
    for k in ("temperature", "top_p", "top_k", "presence_penalty", "repetition_penalty"):
        v = getattr(req, k, None)
        if v is not None:
            s[k] = v
        elif isinstance(mode_params, dict) and k in mode_params and mode_params[k] is not None:
            s[k] = mode_params[k]
    if req.stop:
        s["stop"] = req.stop
    return s


# ---------------------------------------------------------------------------
# Message preparation
# ---------------------------------------------------------------------------


def _provider_supports_media(provider_cfg) -> Tuple[bool, bool, bool]:
    return (
        bool(provider_cfg.supports_vision),
        bool(provider_cfg.supports_audio),
        bool(provider_cfg.supports_video),
    )


def _resolve_media_paths(parts: List[Any], character: str) -> List[Any]:
    """Resolve relative file paths in ContentParts against ``embedding/<char>/image/``."""
    if not character:
        return parts
    image_dir = os.path.join(_EMBEDDING_DIR, character, "image")
    for part in parts:
        ref = getattr(part, "ref", None)
        if ref and ref.get("source") == "file":
            path = ref.get("path", "")
            if path and not os.path.isabs(path):
                ref["path"] = os.path.join(image_dir, path)
    return parts


def _prepare_messages(
    raw_messages: List[ChatMessage],
    *,
    provider_cfg,
    system_prefix: str = "",
    character: str = "",
) -> List[Dict[str, Any]]:
    """Turn the request's pydantic messages into upstream payload dicts.

    ``system_prefix``, if non-empty, is prepended as a system message at index
    0. Any incoming ``role="system"`` message is concatenated to it.

    Legacy ``role="function"`` messages are converted to ``role="tool"`` with
    content wrapped in ``<tool_response>...</tool_response>`` tags, matching
    the Qwen3.6 chat template expectations. Legacy ``function_call`` on
    assistant messages is converted to the ``tool_calls`` format.

    If ``character`` is provided, relative file paths in media placeholders
    (``[image,file=...]``) are resolved against ``embedding/<char>/image/``.
    """
    supports_vision, supports_audio, supports_video = _provider_supports_media(provider_cfg)
    prefetch = bool(provider_cfg.prefetch_media)

    system_parts: List[str] = []
    if system_prefix:
        system_parts.append(system_prefix)
    converted: List[Dict[str, Any]] = []
    for m in raw_messages:
        if m.role == "system":
            # Merge into the system prefix so we never send duplicate system
            # messages (some providers reject that).
            if isinstance(m.content, str):
                system_parts.append(m.content)
            continue

        # --- Legacy function-call support (Qwen3.6 template uses ``tool`` role) ---
        if m.role == "function":
            # Convert legacy ``function`` role to ``tool`` role.
            # Process multimodal content (base64 images etc.) via normalize_content.
            parts = normalize_content(m.content)
            _resolve_media_paths(parts, character)
            content_payload = to_openai_content(parts, prefetch_files=False)
            converted.append({
                "role": "tool",
                "content": content_payload,
            })
            continue

        parts = normalize_content(m.content)

        # Filter unsupported modalities so we never silently get a 400 from a
        # text-only provider just because the client sent an image.
        filtered = []
        for p in parts:
            if p.kind == "image" and not supports_vision:
                filtered.append(p.__class__(kind="text", text="[图片已省略]"))
            elif p.kind == "audio" and not supports_audio:
                filtered.append(p.__class__(kind="text", text="[音频已省略]"))
            elif p.kind == "video" and not supports_video:
                filtered.append(p.__class__(kind="text", text="[视频已省略]"))
            else:
                filtered.append(p)
        _resolve_media_paths(filtered, character)
        content_payload = to_openai_content(filtered, prefetch_files=prefetch)
        msg: Dict[str, Any] = {"role": m.role, "content": content_payload}
        # Convert legacy ``function_call`` to ``tool_calls`` (Qwen3.6 format).
        if m.function_call:
            if "tool_calls" not in msg:
                msg["tool_calls"] = []
            msg["tool_calls"].append({
                "id": m.function_call.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                "type": "function",
                "function": {
                    "name": m.function_call.get("name", ""),
                    "arguments": m.function_call.get("arguments", ""),
                },
            })
        if m.tool_calls:
            msg["tool_calls"] = m.tool_calls
        converted.append(msg)

    out: List[Dict[str, Any]] = []
    if system_parts:
        out.append({"role": "system", "content": "\n\n".join(system_parts)})
    out.extend(converted)
    return out


# ---------------------------------------------------------------------------
# Persona-driven system prompt
# ---------------------------------------------------------------------------


_STATUS_TEMPLATE = (
    "## 当前时间\n"
    "今天是{date}，星期{weekday}，{time_period}{time}。"
)

_DEFAULT_SLEEP_SCHEDULE = "23:00,09:00"


def _build_status_from_globals() -> str:
    """Fill status template with current time. Template and schedule are
    constants for now; sleep schedule will be managed by the set_daily_schedule
    tool in a future phase."""
    template = _STATUS_TEMPLATE
    now = datetime.now()
    schedule = _DEFAULT_SLEEP_SCHEDULE
    try:
        parts = schedule.split(",")
        sleep_h, sleep_m = parts[0].strip().split(":")
        wake_h, wake_m = parts[1].strip().split(":")
    except (ValueError, IndexError):
        sleep_h, sleep_m, wake_h, wake_m = "23", "00", "09", "00"
    hour = now.hour
    if 0 <= hour < 5:    period = "凌晨"
    elif 5 <= hour < 9:  period = "早上"
    elif 9 <= hour < 12: period = "上午"
    elif 12 <= hour < 14: period = "中午"; hour -= 12
    elif 14 <= hour < 17: period = "下午"; hour -= 12
    elif 17 <= hour < 19: period = "傍晚"; hour -= 12
    else:                period = "晚上"; hour -= 12
    weekday_map = ["一", "二", "三", "四", "五", "六", "日"]
    return template.format(
        date=now.strftime("%Y年%m月%d日"),
        weekday=weekday_map[now.weekday()],
        time_period=period,
        time=now.strftime(f"%H点%M分%S秒"),
        sleep_h=sleep_h.zfill(2),
        sleep_m=sleep_m.zfill(2),
        wake_h=wake_h.zfill(2),
        wake_m=wake_m.zfill(2),
    )


def _build_persona_system_prefix(character: str, embeddings_text: str, channel: str = "default") -> Tuple[str, Optional[str]]:
    """Build the system prompt prefix from the character's ``persona.json``.

    Returns ``(system_prefix, image_setting)``.  ``image_setting`` is the
    character's image-setting text (may contain ``[image,...]`` placeholders)
    and should be inserted as a *user* message (not system) after the
    system prompt, matching the legacy main-branch behaviour.

    If the character has no persona on disk we return ``("", None)`` — the
    request becomes a generic completion without any character framing.
    This is intentional: the legacy hard-coded Alice prompt is gone, every
    persona is now data the operator can edit at runtime.

    ``setting`` may contain a ``{embeddings}`` placeholder; if it does, we
    fill it with the retrieved knowledge text. If it doesn't, the retrieved
    knowledge is appended verbatim at the end of the prefix.
    """
    persona = get_persona_manager().get_persona(character)
    if persona is None:
        return "", None
    setting = persona.setting or ""
    if setting:
        if "{embeddings}" in setting:
            try:
                setting = setting.format(embeddings=embeddings_text)
            except (KeyError, IndexError):
                # Malformed format spec -- fall back to literal + suffix so
                # the user at least gets *something* useful.
                setting = setting + "\n" + (embeddings_text or "")
        elif embeddings_text:
            setting = setting + "\n" + embeddings_text
    elif embeddings_text:
        setting = embeddings_text
    system_prefix = setting + "\n" + get_config_manager().get_expression_config().instruction + "\n" + (persona.reply_instruction or "")
    status_text = _build_status_from_globals()
    if status_text:
        system_prefix = system_prefix + "\n" + status_text
    user_desc = get_config_manager().get_globals_flat().get("USER_DESCRIPTION", "").strip()
    if user_desc:
        system_prefix = system_prefix + "\n" + user_desc
    identity = get_config_manager().get_globals_flat().get("IDENTITY", "").strip()
    tool_guidance = _build_tool_guidance(channel, identity)
    if tool_guidance:
        system_prefix = system_prefix + "\n" + tool_guidance
    image_setting = persona.image_setting or None
    return system_prefix, image_setting


_CONVERSATION_START_SEPARATOR = (
    "----------------------CONVERSATION START FROM HERE------------------------------"
)


# Display order of sub-categories inside the "system" group. Categories not
# listed here (e.g. future ones) are appended after, alphabetically.
_CATEGORY_ORDER = ["文件操作", "终端命令", "桌面操作", "进程管理", "网络检索", "代码运行"]


def _channel_builtin_tools(channel: str) -> List[ToolDef]:
    """Built-in ToolDefs enabled for ``channel`` (empty list if none).

    Shared by :func:`_gather_tools` (what we advertise to the model) and
    :func:`_build_tool_guidance` (what we teach the model) so the two never
    drift apart.
    """
    enabled = get_config_manager().get_channel_tools(channel or "default")
    if not enabled:
        return []
    return [d for d in get_tool_registry().list_defs() if d.name in enabled]


def _build_tool_guidance(channel: str, identity: str) -> str:
    """Render the tool-calling guidance for ``channel`` from tool metadata.

    Returns "" when no built-in tools are enabled for the channel, so a bare
    ``default`` channel advertises nothing it cannot actually call. Tools are
    grouped by :class:`ToolGroup`; each group renders its own guidance, and
    within a group distinct ``category`` values become ``###`` sub-headings.
    """
    defs = _channel_builtin_tools(channel)
    if not defs:
        return ""
    ident = identity or "老师"

    by_group: Dict[str, List[ToolDef]] = {}
    for d in defs:
        by_group.setdefault(d.group, []).append(d)

    # Known groups first (in their defined order), then any unknown group names.
    ordered_groups: List[Tuple[str, Optional[ToolGroup], List[ToolDef]]] = []
    known = set()
    for g in groups_in_order():
        known.add(g.name)
        if g.name in by_group:
            ordered_groups.append((g.name, g, by_group[g.name]))
    for gname, tools in by_group.items():
        if gname not in known:
            ordered_groups.append((gname, get_group(gname), tools))

    sections: List[str] = []
    for gname, group, tools_in_group in ordered_groups:
        display = group.display if group else gname
        sections.append(f"## {display}")
        if group:
            sections.append(group.guidance.replace("{identity}", ident))

        by_cat: Dict[str, List[ToolDef]] = {}
        for t in tools_in_group:
            by_cat.setdefault(t.category, []).append(t)
        non_empty = [c for c in by_cat if c]
        if len(non_empty) <= 1:
            for t in tools_in_group:
                if t.guidance:
                    sections.append(f"- {t.guidance}")
        else:
            cats = [c for c in _CATEGORY_ORDER if c in by_cat]
            cats += sorted(c for c in non_empty if c not in _CATEGORY_ORDER)
            for cat in cats:
                sections.append(f"### {cat}")
                for t in by_cat[cat]:
                    if t.guidance:
                        sections.append(f"- {t.guidance}")

    return "\n".join(sections)



def _insert_image_setting(messages: List[Dict[str, Any]], image_setting: str, prefetch_files: bool = False, character: str = "", provider_cfg=None) -> None:
    """Insert ``image_setting`` as a user message after the system prompt.

    Replicates the legacy main-branch behaviour: the character's visual
    setting (containing ``[image,file=...]`` placeholders) is placed as a
    ``role="user"`` message, followed by a separator line, so that images
    are sent as user content (not system) and the model can see them.

    If ``provider_cfg`` is provided, media types unsupported by that
    provider are replaced with text placeholders (same logic as
    ``_prepare_messages``).
    """
    parts = normalize_content(image_setting)
    _resolve_media_paths(parts, character)

    if provider_cfg is not None:
        supports_vision = bool(provider_cfg.supports_vision)
        supports_audio = bool(provider_cfg.supports_audio)
        supports_video = bool(provider_cfg.supports_video)
        filtered = []
        for p in parts:
            if p.kind == "image" and not supports_vision:
                filtered.append(p.__class__(kind="text", text="[图片已省略]"))
            elif p.kind == "audio" and not supports_audio:
                filtered.append(p.__class__(kind="text", text="[音频已省略]"))
            elif p.kind == "video" and not supports_video:
                filtered.append(p.__class__(kind="text", text="[视频已省略]"))
            else:
                filtered.append(p)
        parts = filtered

    img_content = to_openai_content(parts, prefetch_files=prefetch_files)
    insert_pos = 1 if (messages and messages[0].get("role") == "system") else 0
    messages.insert(insert_pos, {"role": "user", "content": img_content})
    messages.insert(
        insert_pos + 1,
        {"role": "user", "content": _CONVERSATION_START_SEPARATOR},
    )


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------


_EMOTION_RE = re.compile(r"【\s*\{\s*'expression'\s*:\s*'([^']+)'\s*\}\s*】")


def _split_thought_and_answer(text: str, enable_thinking: bool = False) -> Tuple[str, str]:
    """Split a Qwen3-style ``<think>...</think>...`` payload.

    When ``enable_thinking=True`` and no ``</think>`` tag is found, the
    entire output is treated as thought (MTP may drop the closing tag).
    """
    if "<think>" in text and "</think>" in text:
        m = re.search(r"<think>(.*?)</think>", text, re.DOTALL)
        thought = m.group(1).strip() if m else ""
        last_idx = text.rfind("</think>")
        answer = text[last_idx + len("</think>"):].strip() if last_idx >= 0 else ""
        return thought, answer
    # Qwen chat_template injects <think>, model outputs only </think>
    if "</think>" in text:
        parts = text.split("</think>", 1)
        return parts[0].strip(), parts[1].strip()
    if enable_thinking:
        return text, ""
    return "", text


def _postprocess_answer(answer: str, character: str) -> str:
    """Snap emotion + strip control tokens."""
    answer = answer.replace("<|endoftext|>", "").replace("<|im_end|>", "").strip()
    if not answer:
        return answer
    m = _EMOTION_RE.search(answer)
    if m:
        snapped = check_emotion(m.group(1), character)
        fmt = get_config_manager().get_expression_config().format
        answer = answer.replace(m.group(0), fmt.replace("{expression}", snapped), 1)
    return answer


# ---------------------------------------------------------------------------
# Tool gathering
# ---------------------------------------------------------------------------


async def _execute_mcp_tool(
    mm,  # MCPManager
    tool_name: str,
    arguments: str,
    messages: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Execute an MCP tool and append tool_call + tool_result to messages.

    Returns a log entry dict if successful, None on failure.
    """
    try:
        args = json.loads(arguments) if isinstance(arguments, str) and arguments else {}
    except json.JSONDecodeError:
        args = {}
    try:
        tool_result = await mm.call_tool(tool_name, args)
    except Exception as e:
        LOG.warning("MCP tool %s failed: %r", tool_name, e)
        tool_result = f"Error: {e!r}"
    result_str = json.dumps(tool_result, ensure_ascii=False) if not isinstance(tool_result, str) else tool_result
    messages.append({
        "role": "assistant",
        "content": "",
        "tool_calls": [{
            "id": f"call_{uuid.uuid4().hex[:12]}",
            "type": "function",
            "function": {"name": tool_name, "arguments": arguments},
        }],
    })
    messages.append({
        "role": "tool",
        "content": f"<tool_response>\n{result_str}\n</tool_response>",
    })
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "mcp_tool_execution",
        "tool_name": tool_name,
        "arguments": arguments,
        "result": result_str[:2000],
    }


def _parse_arguments(arguments: str) -> Dict[str, Any]:
    """Parse a JSON string or dict into a dict of arguments."""
    if isinstance(arguments, dict):
        return arguments
    try:
        return json.loads(arguments) if arguments else {}
    except (json.JSONDecodeError, TypeError):
        return {}


async def _gather_tools(req: ChatCompletionRequest) -> Tuple[Optional[List[Dict[str, Any]]], Set[str], Set[str]]:
    """Combine request ``functions`` + MCP server tools + Skill virtual tools + builtin tools.

    Returns ``(tools, mcp_tool_names, builtin_names)`` where ``mcp_tool_names``
    is the set of tool names that originate from MCP servers and ``builtin_names``
    is the set of built-in tool names (used for server_side routing).
    """
    tools: List[Dict[str, Any]] = []
    mcp_names: Set[str] = set()
    builtin_names: Set[str] = set()
    if req.functions:
        tools.extend(req.functions)
    cm = get_config_manager()
    if cm.get_mcp_tool_call_mode() == "server_side":
        try:
            from core.mcp_manager import get_mcp_manager

            mm = get_mcp_manager()
            mcp_tools = await mm.list_all_tools()
            for t in mcp_tools:
                name = (t.get("function") or {}).get("name", "")
                if name:
                    mcp_names.add(name)
            tools.extend(mcp_tools)
        except Exception as e:
            LOG.warning("Failed to gather MCP tools: %r", e)
    try:
        channel = req.channel or "default"
        builtin_defs = _channel_builtin_tools(channel)
        for d in builtin_defs:
            builtin_names.add(d.name)
            tools.append({
                "type": "function",
                "function": {
                    "name": d.name,
                    "description": d.description,
                    "parameters": d.parameters,
                },
            })
    except Exception as e:
        LOG.warning("Failed to gather builtin tools: %r", e)
    try:
        from core.skill_manager import get_skill_manager
        existing = {(t.get("function") or {}).get("name", "") for t in tools}
        for vt in get_skill_manager().virtual_tools():
            if (vt.get("function") or {}).get("name", "") not in existing:
                tools.append(vt)
    except Exception as e:
        LOG.warning("Failed to gather skill tools: %r", e)
    return tools or None, mcp_names, builtin_names


# ---------------------------------------------------------------------------
# Public: non-streaming chat()
# ---------------------------------------------------------------------------


async def chat(
    *,
    request: ChatCompletionRequest,
    max_tokens: int,
    engine: Any = None,  # legacy: ignored
    autoProcessor: Any = None,  # legacy: ignored
) -> ChatCompletionResponseChoice:
    """Analysis-style completion: no embedding augmentation, no character framing."""
    backend = get_backend()
    provider_cfg = backend.config  # type: ignore[attr-defined]
    messages = _prepare_messages(request.messages, provider_cfg=provider_cfg)
    tools, mcp_names, _builtin_names = await _gather_tools(request)

    request_id = request.request_id or str(uuid.uuid4())
    request_ts = datetime.now(timezone.utc).isoformat()

    # Legacy abort: in the main-branch protocol, abort_id IS the request_id to cancel
    if request.abort_id:
        LOG.info("Legacy abort via chat request for abort_id=%r", request.abort_id)
        await backend.abort(request.abort_id)  # direct: abort_id == request_id

    if request.abort_id:
        _active_requests[request.abort_id] = (provider_cfg.name, request_id)

    rtype = request.type or 0
    extra_body = None
    if rtype == 1:
        extra_body = {"chat_template_kwargs": {"enable_thinking": False}}

    try:
        result = await backend.generate(
            messages=messages,
            sampling=_sampling_from_request(request, max_tokens, mode="assistant"),
            tools=tools,
            request_id=request_id,
            extra_body=extra_body,
        )
        effective_thinking = False if rtype == 1 else bool(request.enable_thinking)
        thought, answer = _split_thought_and_answer(result.text, enable_thinking=effective_thinking)
        if result.reasoning and not thought:
            thought = result.reasoning
        _append_vllm_request_log({
            "ts": datetime.now(timezone.utc).isoformat(),
            "character": "",
            "provider": provider_cfg.name,
            "model": provider_cfg.model,
            "base_url": provider_cfg.base_url,
            "type": "assistant",
            "request": {
                "messages": messages,
                "sampling": _sampling_from_request(request, max_tokens, mode="assistant"),
                "tools": tools,
                "extra_body": extra_body,
            },
            "response": {
                "finish_reason": result.finish_reason,
                "function_calls": result.function_calls or None,
                "tokens": {
                    "prompt": result.prompt_tokens,
                    "completion": result.completion_tokens,
                },
                "answer": answer,
                "thought": thought,
                "raw_text": result.text,
                "raw_events": result.raw_events,
            },
        })
    finally:
        if request.abort_id:
            _active_requests.pop(request.abort_id, None)

    if rtype == 1:
        add_knowledge(content=answer, character="_shared")
        _append_chat_log({
            "ts": request_ts,
            "character": "",
            "user": _last_user_text(request.messages),
            "assistant": answer,
            "thought": "",
            "finish_reason": result.finish_reason,
            "tokens": {
                "prompt": result.prompt_tokens,
                "completion": result.completion_tokens,
            },
        })
        return ChatCompletionResponseChoice(
            index=0,
            thought="",
            embedding_list=[],
            message=ChatMessage(role="assistant", content=answer),
            finish_reason="stop",
        )

    if result.function_calls:
        fc = result.function_calls[0]
        _append_chat_log({
            "ts": request_ts,
            "character": "",
            "user": _last_user_text(request.messages),
            "assistant": answer or "",
            "thought": thought,
            "finish_reason": result.finish_reason,
            "tokens": {
                "prompt": result.prompt_tokens,
                "completion": result.completion_tokens,
            },
        })
        return ChatCompletionResponseChoice(
            index=0,
            thought=thought,
            embedding_list=[],
            message=ChatMessage(
                role="assistant",
                content=answer or "",
                function_call={"name": fc.get("name", ""), "arguments": fc.get("arguments", "")},
            ),
            finish_reason="function_call",
        )
    _append_chat_log({
        "ts": request_ts,
        "character": "",
        "user": _last_user_text(request.messages),
        "assistant": answer,
        "thought": thought,
        "finish_reason": result.finish_reason,
        "tokens": {
            "prompt": result.prompt_tokens,
            "completion": result.completion_tokens,
        },
    })
    return ChatCompletionResponseChoice(
        index=0,
        thought=thought,
        embedding_list=[],
        message=ChatMessage(role="assistant", content=answer),
        finish_reason=_map_finish_reason(result.finish_reason),
    )


# ---------------------------------------------------------------------------
# Public: chat_on_setting()
# ---------------------------------------------------------------------------


def _last_user_text(messages: List[ChatMessage]) -> str:
    for m in reversed(messages):
        if m.role == "user":
            parts = normalize_content(m.content)
            return "".join(p.text or "" for p in parts if p.kind == "text").strip()
    return ""


async def chat_on_setting(
    *,
    request: ChatCompletionRequest,
    max_tokens: int,
    index: int,
    engine: Any = None,
    autoProcessor: Any = None,
    active_lora_path: str = "",
) -> ChatCompletionResponseChoice:
    """Character chat with embedding-based knowledge augmentation."""
    backend = get_backend()
    provider_cfg = backend.config  # type: ignore[attr-defined]

    # Special "type" branches (1 = summarise to memory, 2 = long-term memory).
    rtype = request.type or 0
    if rtype == 1:
        # Treat the last assistant message as the new knowledge to remember.
        for m in request.messages:
            if m.role == "assistant" and isinstance(m.content, str):
                add_knowledge(m.content, "_shared")
        return ChatCompletionResponseChoice(
            index=index,
            thought="",
            embedding_list=[],
            message=ChatMessage(role="assistant", content="ok"),
            finish_reason="stop",
        )

    # Build embedding-augmented system prompt.
    user_text = _last_user_text(request.messages)
    embeddings_text = ""
    embedding_index_list: List[int] = list(request.embeddings_buffer or [])
    if request.on_embedding and user_text:
        try:
            embeddings_text, embedding_index_list = process_embedding(
                content=remove_reference_url(user_text),
                top_k=5,
                character=request.character or "",
                client_buffer=embedding_index_list,
                max_length=8,
                client_information=request.information or "",
            )
        except Exception as e:
            LOG.warning("process_embedding failed: %r", e)
            embeddings_text = ""
    system_prefix, image_setting = _build_persona_system_prefix(
        request.character or "", embeddings_text, request.channel or "default"
    )

    messages = _prepare_messages(
        request.messages, provider_cfg=provider_cfg, system_prefix=system_prefix,
        character=request.character or "",
    )
    if image_setting:
        _insert_image_setting(messages, image_setting,
                              prefetch_files=bool(provider_cfg.prefetch_media),
                              character=request.character or "",
                              provider_cfg=provider_cfg)
    tools, mcp_names, builtin_names = await _gather_tools(request)
    sampling = _sampling_from_request(request, max_tokens)
    extra_body = (
        {"chat_template_kwargs": {"enable_thinking": bool(request.enable_thinking)}}
        if request.enable_thinking is not None
        else None
    )

    request_ts = datetime.now(timezone.utc).isoformat()

    # Legacy abort: in the main-branch protocol, abort_id IS the request_id to cancel
    if request.abort_id:
        LOG.info("Legacy abort via chat request for abort_id=%r", request.abort_id)
        await backend.abort(request.abort_id)  # direct: abort_id == request_id

    request_id = request.request_id or str(uuid.uuid4())
    if request.abort_id:
        _active_requests[request.abort_id] = (provider_cfg.name, request_id)

    max_rounds = get_config_manager().get_mcp_max_tool_rounds()
    result = None
    thought = ""
    answer = ""
    round_num = 0
    async def _mcp_execute():
        nonlocal result, thought, answer, round_num
        round_num += 1
        try:
            result = await backend.generate(
                messages=messages,
                sampling=sampling,
                tools=tools,
                request_id=request_id,
                extra_body=extra_body,
            )
        finally:
            if request.abort_id and result is None:
                _active_requests.pop(request.abort_id, None)
        thought, answer = _split_thought_and_answer(result.text, enable_thinking=bool(request.enable_thinking))
        if result.reasoning and not thought:
            thought = result.reasoning
        answer = _postprocess_answer(answer, request.character or "")
        _append_vllm_request_log({
            "ts": datetime.now(timezone.utc).isoformat(),
            "character": request.character or "",
            "provider": provider_cfg.name,
            "model": provider_cfg.model,
            "base_url": provider_cfg.base_url,
            "type": f"mcp_round/{round_num}",
            "request": {
                "messages": messages,
                "sampling": sampling,
                "tools": tools,
                "extra_body": extra_body,
            },
            "response": {
                "finish_reason": result.finish_reason,
                "function_calls": result.function_calls or None,
                "tokens": {
                    "prompt": result.prompt_tokens,
                    "completion": result.completion_tokens,
                },
                "answer": answer,
                "thought": thought,
                "raw_text": result.text,
                "raw_events": result.raw_events,
            },
        })

    async def _mcp_loop() -> Optional[ChatCompletionResponseChoice]:
        nonlocal result, thought, answer
        for _round in range(max_rounds):
            await _mcp_execute()
            if not result.function_calls:
                return ChatCompletionResponseChoice(
                    index=index,
                    thought=thought,
                    embedding_list=embedding_index_list,
                    message=ChatMessage(role="assistant", content=answer),
                    finish_reason=_map_finish_reason(result.finish_reason),
                )
            executed_any = False
            for fc in result.function_calls:
                name = fc.get("name", "")
                if name in mcp_names:
                    from core.mcp_manager import get_mcp_manager
                    mm = get_mcp_manager()
                    log_entry = await _execute_mcp_tool(mm, name, fc.get("arguments", "{}"), messages)
                    if log_entry is not None:
                        _append_vllm_request_log(log_entry)
                    executed_any = True
                elif name in builtin_names:
                    args = _parse_arguments(fc.get("arguments", "{}"))
                    cap = resolve_capability(name, args)
                    state = get_config_manager().get_capability_states().get(cap, "ask")
                    if state == "allow":
                        result_str = await get_tool_registry().call_tool(name, args)
                        output = result_str.output if result_str.success else f"Error: {result_str.error}"
                        messages.append({
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [{
                                "id": f"call_{uuid.uuid4().hex[:12]}",
                                "type": "function",
                                "function": {"name": name, "arguments": fc.get("arguments", "{}")},
                            }],
                        })
                        messages.append({
                            "role": "tool",
                            "content": f"<tool_response>\n{output}\n</tool_response>",
                        })
                        _append_vllm_request_log({
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "type": "builtin_tool_execution",
                            "tool_name": name,
                            "arguments": fc.get("arguments", ""),
                            "result": output[:2000],
                        })
                        executed_any = True
                    else:
                        # ask (needs confirmation) or deny (treated as ask):
                        # return the function_call to the caller for confirmation.
                        fc_first = result.function_calls[0]
                        return ChatCompletionResponseChoice(
                            index=index,
                            thought=thought,
                            embedding_list=embedding_index_list,
                            message=ChatMessage(
                                role="assistant",
                                content=answer or "",
                                function_call={
                                    "name": fc_first.get("name", ""),
                                    "arguments": fc_first.get("arguments", ""),
                                },
                            ),
                            finish_reason="function_call",
                        )
                else:
                    fc = result.function_calls[0]
                    return ChatCompletionResponseChoice(
                        index=index,
                        thought=thought,
                        embedding_list=embedding_index_list,
                        message=ChatMessage(
                            role="assistant",
                            content=answer or "",
                            function_call={
                                "name": fc.get("name", ""),
                                "arguments": fc.get("arguments", ""),
                            },
                        ),
                        finish_reason="function_call",
                    )
            if not executed_any:
                break
        # Max rounds exhausted — return whatever text we have.
        return ChatCompletionResponseChoice(
            index=index,
            thought=thought,
            embedding_list=embedding_index_list,
            message=ChatMessage(role="assistant", content=answer),
            finish_reason=_map_finish_reason(result.finish_reason if result else "stop"),
        )

    # --- Run tool loop -------------------------------------------------------
    choice = await _mcp_loop()
    if request.abort_id:
        _active_requests.pop(request.abort_id, None)

    # Log the conversation turn to the chat log file.
    try:
        log_entry = {
            "ts": request_ts,
            "character": request.character or "",
            "user": user_text,
            "assistant": answer,
            "thought": thought,
            "finish_reason": result.finish_reason,
            "tokens": {
                "prompt": result.prompt_tokens,
                "completion": result.completion_tokens,
            },
        }
        _append_chat_log(log_entry)
    except Exception:
        pass  # Logging failure must never break the response.

    return choice


# ---------------------------------------------------------------------------
# Streaming variants
# ---------------------------------------------------------------------------


async def chat_on_setting_stream(
    *,
    request: ChatCompletionRequest,
    max_tokens: int,
    index: int,
) -> AsyncIterator[ChatCompletionResponse]:
    """Yield :class:`ChatCompletionResponse` chunks (``object="chat.completion.chunk"``).

    The first chunk carries ``delta.role="assistant"``; subsequent chunks
    carry incremental text; the terminal chunk carries ``finish_reason``.
    """
    backend = get_backend()
    provider_cfg = backend.config  # type: ignore[attr-defined]

    user_text = _last_user_text(request.messages)
    embeddings_text = ""
    embedding_index_list: List[int] = list(request.embeddings_buffer or [])
    if request.on_embedding and user_text:
        try:
            embeddings_text, embedding_index_list = process_embedding(
                content=remove_reference_url(user_text),
                top_k=5,
                character=request.character or "",
                client_buffer=embedding_index_list,
                max_length=8,
                client_information=request.information or "",
            )
        except Exception as e:
            LOG.warning("process_embedding failed: %r", e)

    system_prefix, image_setting = _build_persona_system_prefix(
        request.character or "", embeddings_text, request.channel or "default"
    )
    messages = _prepare_messages(
        request.messages, provider_cfg=provider_cfg, system_prefix=system_prefix,
        character=request.character or "",
    )
    if image_setting:
        _insert_image_setting(messages, image_setting,
                              prefetch_files=bool(provider_cfg.prefetch_media),
                              character=request.character or "",
                              provider_cfg=provider_cfg)
    tools, mcp_names, _builtin_names = await _gather_tools(request)
    sampling = _sampling_from_request(request, max_tokens)
    extra_body = (
        {"chat_template_kwargs": {"enable_thinking": bool(request.enable_thinking)}}
        if request.enable_thinking is not None
        else None
    )

    request_ts = datetime.now(timezone.utc).isoformat()

    request_id = request.request_id or str(uuid.uuid4())
    # Legacy abort: in the main-branch protocol, abort_id IS the request_id to cancel
    if request.abort_id:
        LOG.info("Legacy abort via chat request for abort_id=%r", request.abort_id)
        await backend.abort(request.abort_id)  # direct: abort_id == request_id
    if request.abort_id:
        _active_requests[request.abort_id] = (provider_cfg.name, request_id)
    # Emit the opening role chunk.
    yield ChatCompletionResponse(
        model=request.model,
        object="chat.completion.chunk",
        choices=[
            ChatCompletionResponseStreamChoice(
                index=index,
                delta=DeltaMessage(role="assistant", content=""),
                finish_reason=None,
            )
        ],
    )

    collected_text: List[str] = []
    collected_function_calls: List[Dict[str, Any]] = []
    collected_raw_events: List[Dict[str, Any]] = []
    last_finish_reason: Optional[str] = None

    try:
        it = await backend.generate_stream(
            messages=messages,
            sampling=sampling,
            tools=tools,
            request_id=request_id,
            extra_body=extra_body,
        )
        async for chunk in it:  # type: StreamChunk
            if chunk.raw is not None:
                collected_raw_events.append(chunk.raw)
            if chunk.text:
                collected_text.append(chunk.text)
            if chunk.function_calls:
                collected_function_calls = chunk.function_calls
            if not chunk.text and not chunk.finish_reason:
                continue
            last_finish_reason = chunk.finish_reason
            yield ChatCompletionResponse(
                model=request.model,
                object="chat.completion.chunk",
                choices=[
                    ChatCompletionResponseStreamChoice(
                        index=index,
                        delta=DeltaMessage(content=chunk.text or None),
                        finish_reason=(
                            _map_finish_reason(chunk.finish_reason)
                            if chunk.finish_reason
                            else None
                        ),
                    )
                ],
            )
    finally:
        if request.abort_id:
            _active_requests.pop(request.abort_id, None)

    if collected_function_calls:
        fc = collected_function_calls[0]
        yield ChatCompletionResponse(
            model=request.model,
            object="chat.completion.chunk",
            choices=[
                ChatCompletionResponseStreamChoice(
                    index=index,
                    delta=DeltaMessage(
                        function_call={
                            "id": fc.get("id", ""),
                            "name": fc.get("name", ""),
                            "arguments": fc.get("arguments", ""),
                        },
                    ),
                    finish_reason="function_call",
                )
            ],
        )

    # Log the full conversation turn after streaming ends.
    try:
        full_answer = "".join(collected_text).strip()
        thought, clean_answer = _split_thought_and_answer(full_answer, enable_thinking=bool(request.enable_thinking))
        if not thought:
            thought = ""
        log_entry = {
            "ts": request_ts,
            "character": request.character or "",
            "user": user_text,
            "assistant": clean_answer or full_answer,
            "thought": thought,
            "finish_reason": "stop",
            "tokens": {},
        }
        _append_chat_log(log_entry)
        _append_vllm_request_log({
            "ts": request_ts,
            "character": request.character or "",
            "provider": provider_cfg.name,
            "model": provider_cfg.model,
            "base_url": provider_cfg.base_url,
            "type": "streaming",
            "request": {
                "messages": messages,
                "sampling": sampling,
                "tools": tools,
                "extra_body": extra_body,
            },
            "response": {
                "finish_reason": last_finish_reason or "stop",
                "function_calls": collected_function_calls or None,
                "answer": clean_answer or full_answer,
                "thought": thought,
                "raw_text": full_answer,
                "raw_events": collected_raw_events,
            },
        })
    except Exception:
        pass  # Logging failure must never break the response.


# ---------------------------------------------------------------------------
# Abort
# ---------------------------------------------------------------------------


async def abort_request(abort_id: str) -> bool:
    """Cooperatively abort the in-flight request with ``abort_id``."""
    entry = _active_requests.get(abort_id)
    if entry is None:
        return False
    provider_name, request_id = entry
    backend = get_backend(provider_name)
    try:
        await backend.abort(request_id)
        return True
    except Exception as e:
        LOG.warning("abort failed for %s: %r", abort_id, e)
        return False


def _map_finish_reason(reason: str) -> str:
    if reason in ("stop", "function_call", "abort", "error"):
        return reason
    if reason == "tool_calls":
        return "function_call"
    if reason == "length":
        return "overthink"
    if reason == "":
        return "stop"
    return "stop"