"""Web tools: search (via SearXNG) and website access (via CDP browser).

``web_search`` talks to a self-hosted SearXNG instance's JSON API — no API
key, no fragile scraping, multi-engine aggregation with graceful fallback.

``access_website`` drives the shared CDP browser (see ``_browser.py``): it opens
the page, takes a screenshot (returned as an ``[image,base64=...]`` placeholder
so a vision-capable model can *see* it), extracts the main text with
trafilatura, and either closes the tab (the model just needed the info) or
leaves it open in the foreground for the operator to browse.
"""

from __future__ import annotations

import asyncio
import base64
import os
from typing import Dict, List

import httpx

from tools.registry import get_tool_registry
from tools.schema import PermissionLevel, ToolDef

_SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8888").rstrip("/")


async def _web_search(query: str, category: str = "general", max_results: int = 5) -> str:
    if not query.strip():
        return "Error: empty query"
    params = {
        "q": query,
        "format": "json",
        "categories": "images" if category == "images" else "general",
        "safesearch": 1,
        "language": "auto",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(f"{_SEARXNG_URL}/search", params=params, headers={"User-Agent": "ArisuAgent/1.0"})
            if resp.status_code != 200:
                return f"Error: SearXNG returned HTTP {resp.status_code}. 确认 SearXNG 已启动且开启了 json 输出（docker start searxng）。"
            data = resp.json()
    except httpx.ConnectError:
        return f"Error: 无法连接 SearXNG（{_SEARXNG_URL}）。请先启动：docker start searxng"
    except Exception as e:
        return f"Error: 搜索失败 — {e}"

    results: List[Dict] = data.get("results", []) or []
    if not results:
        return f"未找到与 {query!r} 相关的结果。"

    results = results[: max_results]
    if category == "images":
        lines = [f"找到 {len(results)} 张与 {query!r} 相关的图片："]
        for r in results:
            img = r.get("img_src") or r.get("thumbnail_src") or ""
            title = (r.get("title") or "").strip()
            src = r.get("url") or ""
            if img:
                lines.append(f'[image,url={img}] {title}（来源：{src}）')
            else:
                lines.append(f"{title}（{src}）")
        return "\n".join(lines)

    lines = [f"找到 {len(results)} 条与 {query!r} 相关的结果："]
    for i, r in enumerate(results, 1):
        title = (r.get("title") or "").strip()
        url = r.get("url") or ""
        snippet = (r.get("content") or "").strip()
        lines.append(f"\n[{i}] {title}\n    {url}\n    {snippet}")
    return "\n".join(lines)


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
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        title = await page.title()
        html = await page.content()

        text = ""
        try:
            import trafilatura
            text = await asyncio.to_thread(trafilatura.extract, html) or ""
        except Exception:
            text = await page.inner_text("body")
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
            try:
                png = await page.screenshot(full_page=False)
                out += f"\n[image,base64={base64.b64encode(png).decode()}]"
            except Exception as e:
                out += f"\n（截图失败：{e}）"

        if not close:
            try:
                await page.bring_to_front()
            except Exception:
                pass
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


def register() -> None:
    reg = get_tool_registry()
    reg.register(ToolDef(
        name="web_search",
        description=(
            "通过网络搜索信息或图片（由 SearXNG 聚合多个引擎，无需 API key）。"
            "category='general' 返回网页结果（标题/链接/摘要）；category='images' 返回图片（含图片URL，视觉模型可直接查看）。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词。"},
                "category": {"type": "string", "enum": ["general", "images"], "description": "general=网页，images=图片。默认 general。"},
                "max_results": {"type": "integer", "description": "最多返回多少条（默认5）。"},
            },
            "required": ["query"],
        },
        permission_level=PermissionLevel.READ,
        handler=_web_search,
        group="web",
        category="搜索",
        guidance="要查资料/最新信息 → web_search；要找图片 → web_search(category=images)",
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
