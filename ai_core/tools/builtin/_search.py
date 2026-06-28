"""Browser-driven web search (DuckDuckGo primary, Bing fallback) + deep-dive.

Drives the shared Chrome (via ``_browser.py``) to query DuckDuckGo; when DDG
yields nothing it falls back to Bing (CAPTCHA is detected and treated as
no-results). Result links are deep-dived for full text from 萌娘百科 /
百度百科 / Wikipedia, with a robust (networkidle + scroll + trafilatura)
fallback for generic JS-heavy sites. The dive keeps going through the result
list — skipping pages that yield nothing — until ``target`` valid pieces are
collected, so a few bad links don't starve the result.

Only the pages opened here are closed; the shared browser context is left
intact, and the whole browser is shut down (profile kept) at the end so the
next operation relaunches Chrome cleanly (QQ-style lifecycle).
"""

from __future__ import annotations

import asyncio
import random
import urllib.parse
from typing import Dict, List, Tuple

# How many valid info blocks we want to collect, and how big a candidate pool
# to pull from the search engine (extra room to skip junk/JS-dead links).
_TARGET_VALID = 5
_POOL = 10


async def _ddg_results(page, query: str, pool: int) -> List[Dict]:
    """Query DuckDuckGo and return [{title,url,snippet}, ...]. Empty on failure."""
    q = urllib.parse.quote(query)
    for attempt in range(3):
        try:
            await page.goto(f"https://duckduckgo.com/?q={q}&t=h_&ia=web")
            await asyncio.sleep(random.uniform(1.5, 2.0))
            cards = await page.query_selector_all('[data-testid="result"]')
            out: List[Dict] = []
            for card in cards:
                a = await card.query_selector('a[data-testid="result-title-a"]')
                if not a:
                    continue
                url = await a.get_attribute("href") or ""
                title = (await a.inner_text()).strip()
                snip_el = await card.query_selector('[data-testid="result-snippet"]')
                if not snip_el:
                    snip_el = await card.query_selector(
                        'div[data-result="snippet"] span, .OgdwYG6KE2qthn9XQWFC span'
                    )
                snippet = (await snip_el.inner_text()).strip() if snip_el else ""
                out.append({"title": title, "url": url, "snippet": snippet})
                if len(out) >= pool:
                    break
            if out:
                return out
            raise RuntimeError("DDG 未返回结果")
        except Exception:
            if attempt >= 2:
                return []
            await asyncio.sleep(1.0)
    return []


def _looks_like_captcha(page_url: str, text: str) -> bool:
    pl = (page_url or "").lower()
    tl = (text or "")[:4000].lower()
    if "captcha" in pl or "captcha" in tl:
        return True
    return any(s in tl for s in ("verify you are human", "请完成安全验证", "为了确认您是真人"))


async def _bing_results(page, query: str, pool: int) -> List[Dict]:
    """Query Bing and return [{title,url,snippet}, ...]. Empty on failure/CAPTCHA."""
    q = urllib.parse.quote(query)
    try:
        await page.goto(f"https://www.bing.com/search?q={q}")
        await asyncio.sleep(random.uniform(1.5, 2.0))
        if _looks_like_captcha(page.url, await page.content()):
            return []
        cards = await page.query_selector_all("#b_results .b_algo")
        out: List[Dict] = []
        for card in cards:
            a = await card.query_selector("h2 a")
            if not a:
                continue
            url = await a.get_attribute("href") or ""
            title = (await a.inner_text()).strip()
            snip_el = await card.query_selector(".b_caption p, .b_lineclamp4, .b_lineclamp3")
            snippet = (await snip_el.inner_text()).strip() if snip_el else ""
            out.append({"title": title, "url": url, "snippet": snippet})
            if len(out) >= pool:
                break
        return out
    except Exception:
        return []


async def _robust_text(page) -> str:
    """Rendered inner_text with a trafilatura fallback (handles JS-heavy sites)."""
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
    return (text or "")[:2000]


async def _open_and_scroll(context, pages, url, wait_until="networkidle", timeout=30000, scroll=True):
    p = await context.new_page()
    pages.append(p)
    await p.goto(url, wait_until=wait_until, timeout=timeout)
    if scroll:
        await asyncio.sleep(random.uniform(0.5, 1.0))
        for _ in range(3):
            await p.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await p.wait_for_timeout(2000)
    return p


async def _extract_moegirl(context, pages, url) -> str:
    p = await _open_and_scroll(context, pages, url)
    info = ""
    box = await p.query_selector(".mw-parser-output >> .moe-infobox")
    if box:
        info += f"根据萌娘百科{url}提供的信息如下：\n{(await box.text_content() or '').replace(chr(10)*3, '')}\n"
    locs = await p.query_selector_all(
        ".mw-parser-output > h2:not(table *), .mw-parser-output > h3:not(table *), "
        ".mw-parser-output > h4:not(table *), .mw-parser-output > p:not(table *), "
        ".mw-parser-output > ul:not(table *)"
    )
    body = "".join((await loc.text_content() or "").replace("\n\n", "") + "\n" for loc in locs)
    return info + body if (info or body).strip() else ""


async def _extract_baike(context, pages, url) -> str:
    p = await _open_and_scroll(context, pages, url)
    summary_el = await p.query_selector(".J-summary")
    summary = (await summary_el.text_content() or "") if summary_el else ""
    box_el = await p.query_selector(".J-basic-info")
    brief = (await box_el.text_content() or "") if box_el else ""
    body = f"根据百度百科{url}提供的信息如下：\n{brief}\n{summary}\n"
    return body if body.strip() else ""


async def _extract_wiki(context, pages, url) -> str:
    p = await _open_and_scroll(context, pages, url)
    locs = await p.query_selector_all(
        ".mw-parser-output > h2:not(table *), .mw-parser-output > h3:not(table *), "
        ".mw-parser-output > h4:not(table *), .mw-parser-output > p:not(table *), "
        ".mw-parser-output > ul:not(table *)"
    )
    body = "".join((await loc.text_content() or "") + "\n" for loc in locs)
    return (f"根据Wikipedia{url}提供的信息如下：\n" + body) if body.strip() else ""


async def _extract_generic(context, pages, url) -> str:
    # Robust: networkidle + scroll + inner_text, trafilatura fallback.
    p = await _open_and_scroll(context, pages, url, wait_until="networkidle", timeout=30000)
    text = await _robust_text(p)
    return f"根据网站{url}提供的信息：\n{text}\n" if text.strip() else ""


async def _deep_dive(context, results: List[Dict], pages: List, target: int) -> str:
    """Collect up to ``target`` valid info blocks, skipping pages that yield none.

    Priority: 萌娘百科 / 百度百科 / Wikipedia (once each), then generic sites.
    Pages that fail to load or return empty text are skipped and the next
    result is tried, so a few dead links don't starve the result.
    """
    info = ""
    valid = 0
    moegirl_token = baike_token = wiki_token = False
    for r in results:
        if valid >= target:
            break
        url = r.get("url", "")
        if not url:
            continue
        try:
            if url.startswith("https://zh.moegirl.org.cn") and not moegirl_token:
                block = await _extract_moegirl(context, pages, url)
                moegirl_token = True
            elif url.startswith("https://baike.baidu") and not baike_token:
                block = await _extract_baike(context, pages, url)
                baike_token = True
            elif (url.startswith("https://zh.wikipedia.org") or url.startswith("https://en.wikipedia.org")) and not wiki_token:
                block = await _extract_wiki(context, pages, url)
                wiki_token = True
            else:
                block = await _extract_generic(context, pages, url)
            # Only count blocks that actually carry content.
            if block and len(block.strip()) > 60:
                info += block
                valid += 1
        except Exception:
            continue  # skip this result, try the next
    return info


async def online_search(query: str, max_results: int = _TARGET_VALID) -> str:
    """Search the web via the shared browser and return concatenated raw text.

    DuckDuckGo is tried first (pool of ``_POOL`` candidates); if it returns
    nothing, Bing is used. Result links are deep-dived, skipping empty ones,
    until ``max_results`` valid pieces are gathered. Suitable input for a
    follow-up summarisation step.
    """
    query = (query or "").strip()
    if not query:
        return "Error: empty query"

    from tools.builtin import _browser

    try:
        browser = await _browser.get_browser()
    except Exception as e:
        return f"Error: 浏览器启动失败 — {e}"

    contexts = browser.contexts
    context = contexts[0] if contexts else await browser.new_context()
    page = await context.new_page()
    pages: List = []
    try:
        results = await _ddg_results(page, query, _POOL)
        if not results:
            results = await _bing_results(page, query, _POOL)
        if not results:
            return f"未找到与 {query!r} 相关的搜索结果（DuckDuckGo 和 Bing 都没有返回）。"

        info = await _deep_dive(context, results, pages, max_results)
        info += "其他网站的摘要信息：\n"
        for r in results[: _POOL]:
            info += "URL：{url} 标题：{title} 摘要：{snippet}\n".format(
                url=r.get("url", ""), title=r.get("title", ""), snippet=r.get("snippet", "")
            )
        return info
    except Exception as e:
        return f"Error: 搜索失败 — {e}"
    finally:
        for p in pages:
            try:
                await p.close()
            except Exception:
                pass
        try:
            await page.close()
        except Exception:
            pass
        # Deliberately do NOT close the shared context. But DO tear down the
        # browser process (profile kept) so Chrome doesn't linger — matches the
        # QQ bot's per-operation cleanup.
        try:
            await _browser.close_browser()
        except Exception:
            pass
