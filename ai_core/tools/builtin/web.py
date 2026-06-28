"""Web tools: search (browser-driven DuckDuckGo/Bing) and website access (CDP).

``web_search`` drives the shared Chrome (see ``_browser.py``) to query
DuckDuckGo first, falling back to Bing, then deep-dives 萌娘百科 / 百度百科 /
Wikipedia for full text (see ``_search.py``). The raw text is condensed via a
type-1 assistant call — which also persists the summary to the shared
knowledge base — so the model receives a concise summary instead of a dump.

``access_website`` opens a page in the same shared browser, takes a
screenshot (returned as an ``[image,base64=...]`` placeholder so a
vision-capable model can *see* it), extracts the main text, and either
closes the tab or leaves it open for the operator to browse.
"""

from __future__ import annotations

import asyncio
import base64

from tools.registry import get_tool_registry
from tools.schema import PermissionLevel, ToolDef

# Instruction appended to raw search text for the type-1 summarisation call.
# Matches the QQ bot's prompt: concise summary + keyword tags + reference URLs.
_SUMMARY_INSTRUCTION = (
    "\n\n在400字以内总结上面关于\"{q}\"的搜索结果。"
    "输出时不需要换行符，并根据内容在末尾用##的方式加上搜索的核心关键词tag，多个tag用空格隔开。"
    "在这之后，你还需要以<reference_url:https://...>这样的格式在末尾列出参考的网页链接。\n"
    "你给出的总结："
)

# Per-turn screenshot budget for access_website. Screenshots are full-page and
# can be large, so capping them bounds the vision-token cost of a browsing
# turn. Reset at the start of each chat_on_setting(_stream) call.
_SCREENSHOT_CAP = 3
_screenshot_count = 0


def reset_screenshot_cap() -> None:
    global _screenshot_count
    _screenshot_count = 0


def _resize_screenshot_bytes(png: bytes, max_width: int = 1280) -> bytes:
    """Downscale a screenshot by WIDTH (keep aspect) so text stays legible.

    Unlike the media normaliser's max-dimension resize, capping only the width
    keeps tall full-page captures readable instead of shrinking them to a
    sliver. Falls back to the raw bytes if PIL is unavailable.
    """
    try:
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(png))
        w, h = img.size
        if w > max_width:
            img = img.resize((max_width, int(h * max_width / w)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return png


async def _web_search(query: str, max_results: int = 5) -> str:
    """Browser-driven search (DDG→Bing + deep-dive) condensed via a type-1 call.

    The raw fetched text is summarised by the assistant path with type=1, which
    both yields a concise result and persists it to the shared knowledge base
    (``add_knowledge(..., "_shared")``) for future turns — matching the QQ bot.
    """
    if not (query or "").strip():
        return "Error: empty query"
    from tools.builtin import _search
    raw = await _search.online_search(query, max_results=max_results)
    # Surface upstream errors / "no results" verbatim, without summarising them.
    if raw.startswith("Error") or raw.startswith("未找到"):
        return raw
    try:
        from llm.chat import chat
        from models.base import ChatCompletionRequest, ChatMessage
        req = ChatCompletionRequest(
            model="",
            messages=[ChatMessage(role="user", content=raw + _SUMMARY_INSTRUCTION.format(q=query))],
            type=1,
        )
        choice = await chat(request=req, max_tokens=2000)
        summary = (choice.message.content or "").strip()
        if summary:
            return summary
    except Exception:
        pass  # fall through to a truncated raw dump
    # Summarisation unavailable / failed — return a truncated raw dump.
    return raw[:2000] + ("…[已截断]" if len(raw) > 2000 else "")


async def _access_website(url: str, close: bool = True, screenshot: bool = True) -> str:
    if not url.strip():
        return "Error: empty url"
    try:
        from tools.builtin import _browser
    except ImportError:
        return "Error: 浏览器模块不可用"

    try:
        browser = await _browser.get_browser()
    except Exception as e:
        return f"Error: 浏览器启动失败 — {e}"

    contexts = browser.contexts
    context = contexts[0] if contexts else await browser.new_context()
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        # Scroll to trigger lazy-loaded content (JS-heavy sites like GameKee)
        for _ in range(3):
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(2000)
        # Always bring to front so the user can see what's being accessed
        try:
            await page.bring_to_front()
        except Exception:
            pass
        title = await page.title()

        # Use rendered inner_text as primary (captures JS-rendered content);
        # fall back to trafilatura on raw HTML for static sites.
        text = ""
        try:
            text = await page.inner_text("body")
        except Exception:
            pass
        if not text or len(text) < 100:
            try:
                import trafilatura
                html = await page.content()
                text = await asyncio.to_thread(trafilatura.extract, html) or ""
            except Exception:
                text = ""
        text = (text or "")[:4000]

        links = []
        try:
            raw = await page.eval_on_selector_all(
                "a",
                """els => els.map(a => ({t: (a.innerText||'').trim(), h: a.href}))
                         .filter(x => x.t && x.h && !x.h.startsWith('javascript:')).slice(0, 8)""",
            )
            links = [f"{x['t']} — {x['h']}" for x in raw if isinstance(x, dict)]
        except Exception:
            pass

        out = f"# {title}\nURL: {url}\n\n{text}"
        if links:
            out += "\n\n相关链接：\n- " + "\n- ".join(links)

        if screenshot:
            global _screenshot_count
            if _screenshot_count < _SCREENSHOT_CAP:
                try:
                    png = await page.screenshot(full_page=True)
                    png = _resize_screenshot_bytes(png)
                    out += f"\n[image,base64={base64.b64encode(png).decode()}]"
                    _screenshot_count += 1
                except Exception as e:
                    out += f"\n（截图失败：{e}）"
            else:
                out += "\n（本回合截图已达上限，本次仅返回文本。）"

        if not close:
            out += "\n\n（页面已在浏览器中为你打开，未关闭。）"
        return out
    except Exception as e:
        return f"Error: 访问 {url} 失败 — {e}"
    finally:
        if close:
            try:
                await page.close()
            except Exception:
                pass
            # QQ-style: free the browser process but keep the profile, so
            # cookies/login survive and the next call relaunches Chrome.
            try:
                await _browser.close_browser()
            except Exception:
                pass


def register() -> None:
    reg = get_tool_registry()
    reg.register(ToolDef(
        name="web_search",
        description=(
            "通过网络搜索引擎查询最新信息（浏览器驱动 DuckDuckGo，失败回退 Bing，"
            "并深入抓取萌娘百科/百度百科/Wikipedia 等页面）。结果会被总结成精简摘要返回，"
            "并自动存入共享知识库供后续参考。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词。"},
                "max_results": {"type": "integer", "description": "最多返回多少条（默认5）。"},
            },
            "required": ["query"],
        },
        permission_level=PermissionLevel.READ,
        handler=_web_search,
        group="web",
        category="搜索",
        guidance="要查资料/最新信息 → web_search",
    ))
    reg.register(ToolDef(
        name="access_website",
        description=(
            "在浏览器中打开指定网页：截图（视觉模型可查看页面）、抽取正文与链接。"
            "close=true（默认）=AI 自己查看后关闭页面；close=false=为用户打开并留在前台（用户可直接浏览）。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "要访问的完整 URL。"},
                "close": {"type": "boolean", "description": "true=用完关闭页面（AI 自用）；false=留在前台供用户浏览。默认 true。"},
                "screenshot": {"type": "boolean", "description": "是否截图（视觉分析）。默认 true。"},
            },
            "required": ["url"],
        },
        permission_level=PermissionLevel.READ,
        handler=_access_website,
        group="web",
        category="访问",
        guidance="要读某个网页的内容/截图 → access_website；要给用户打开页面 → access_website(close=false)",
    ))
