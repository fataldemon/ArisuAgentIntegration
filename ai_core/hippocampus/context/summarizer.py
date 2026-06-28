"""Summary generation for history truncation.

The summary step needs an LLM. To keep hippocampus transport-agnostic, the
actual call is provided as an injectable async callable ``summarize_fn``.
When running embedded in AI Core, :func:`default_summarize` calls the
in-process ``llm.chat.chat`` assistant path directly (no self-HTTP).
"""

from __future__ import annotations

from typing import Awaitable, Callable, Optional

# async (prompt: str) -> str | None
SummarizeFn = Callable[[str], Awaitable[Optional[str]]]


async def default_summarize(prompt: str) -> Optional[str]:
    """In-process assistant call against AI Core's ``llm.chat.chat``.

    Imported lazily so that the hippocampus package does not depend on the
    AI Core LLM stack at import time (and stays importable on its own).
    """
    try:
        from llm.chat import chat  # type: ignore
        from models.base import ChatCompletionRequest, ChatMessage  # type: ignore
        from template import max_analysis_len  # type: ignore
    except Exception as e:  # pragma: no cover -- not embedded in AI Core
        print(f"[hippocampus] default_summarize unavailable: {e}")
        return None

    request = ChatCompletionRequest(
        model="gpt-3.5-turbo",
        messages=[ChatMessage(role="user", content=prompt)],
        character="tendou_arisu",
        enable_thinking=False,
        on_embedding=False,
        stream=False,
        type=2,
    )
    try:
        choice = await chat(request=request, max_tokens=max_analysis_len)
    except Exception as e:  # pragma: no cover
        print(f"[hippocampus] summary generation failed: {e}")
        return None
    if choice.finish_reason in ("abort", "error"):
        return None
    content = (choice.message.content or "").strip()
    return content or None
