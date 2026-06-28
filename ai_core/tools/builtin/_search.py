"""Browser-driven web search (DuckDuckGo primary, Bing fallback) + deep-dive.

Replaces the retired SearXNG backend. Drives the shared Chrome (via
``_browser.py``) to query DuckDuckGo; when DDG yields nothing it falls back
to Bing (which may occasionally hit a CAPTCHA — treated as "no results").
Then it deep-dives the result links for full text from 萌娘百科 / 百度百科 /
Wikipedia, with a generic body-text fallback for everything else.

Only the pages opened here are closed. The shared browser context is left
intact so ``access_website`` and other tools keep working.
"""

from __future__ import annotations

import asyncio
import random
import urllib.parse
from typing import Dict, List, Tuple

# Per-site deep-dive cap so a single search never opens dozens of tabs.
_MAX_DEEP_PAGES = 5


async def _ddg_results(page, query: str, max_results: int) -> List[Dict]:
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
                if len(out) >= max_results:
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


async def _bing_results(page, query: str, max_results: int) -> List[Dict]:
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
            if len(out) >= max_results:
                break
        return out
    except Exception:
        return []


async def _deep_dive(context, results: List[Dict], pages: List) -> str:
    """Open up to _MAX_DEEP_PAGES result links and extract full text.

    Priority: 萌娘百科 / 百度百科 / Wikipedia (once each), then generic sites.
    Opened pages are appended to ``pages`` so the caller can close them.
    """
    info = ""
    page_no = 0
    moegirl_token = baike_token = wiki_token = False

    for r in results:
        if page_no >= _MAX_DEEP_PAGES:
            break
        url = r.get("url", "")
        if not url:
            continue
        try:
            if url.startswith("https://zh.moegirl.org.cn") and not moegirl_token:
                p = await context.new_page()
                pages.append(p)
                await p.goto(url)
                await asyncio.sleep(random.uniform(1.0, 2.0))
                box = await p.query_selector(".mw-parser-output >> .moe-infobox")
                if box:
                    box_text = (await box.text_content() or "").replace("\n\n\n", "")
                    info += f"根据萌娘百科{url}提供的信息如下：\n{box_text}\n"
                locs = await p.query_selector_all(
                    ".mw-parser-output > h2:not(table *), .mw-parser-output > h3:not(table *), "
                    ".mw-parser-output > h4:not(table *), .mw-parser-output > p:not(table *), "
                    ".mw-parser-output > ul:not(table *)"
                )
                for loc in locs:
                    info += (await loc.text_content() or "").replace("\n\n", "") + "\n"
                page_no += 1
                moegirl_token = True
            elif url.startswith("https://baike.baidu") and not baike_token:
                p = await context.new_page()
                pages.append(p)
                await p.goto(url)
                await asyncio.sleep(random.uniform(1.0, 2.0))
                summary_el = await p.query_selector(".J-summary")
                summary = (await summary_el.text_content() or "") if summary_el else ""
                box_el = await p.query_selector(".J-basic-info")
                brief = (await box_el.text_content() or "") if box_el else ""
                info += f"根据百度百科{url}提供的信息如下：\n{brief}\n{summary}\n"
                page_no += 1
                baike_token = True
            elif (url.startswith("https://zh.wikipedia.org") or url.startswith("https://en.wikipedia.org")) and not wiki_token:
                p = await context.new_page()
                pages.append(p)
                await p.goto(url)
                await asyncio.sleep(random.uniform(1.0, 2.0))
                locs = await p.query_selector_all(
                    ".mw-parser-output > h2:not(table *), .mw-parser-output > h3:not(table *), "
                    ".mw-parser-output > h4:not(table *), .mw-parser-output > p:not(table *), "
                    ".mw-parser-output > ul:not(table *)"
                )
                info += f"根据Wikipedia{url}提供的信息如下：\n"
                for loc in locs:
                    info += (await loc.text_content() or "") + "\n"
                page_no += 1
                wiki_token = True
            else:
                p = await context.new_page()
                pages.append(p)
                await p.goto(url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(0.5)
                body = await p.query_selector("body")
                if body:
                    text = (await body.text_content() or "")[:2000]
                    info += f"根据网站{url}提供的信息：\n{text}\n"
                page_no += 1
        except Exception:
            info += f"地址{url}上或许有有用信息，但目前无法访问……\n"

    return info


async def online_search(query: str, max_results: int = 5) -> str:
    """Search the web via the shared browser and return concatenated raw text.

    DuckDuckGo is tried first; if it returns nothing, Bing is used as a
    fallback. Result links are deep-dived for full text (萌娘/baike/wiki/generic),
    then the remaining snippets are appended. Suitable input for a follow-up
    summarisation step.
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
        results = await _ddg_results(page, query, max_results)
        if not results:
            results = await _bing_results(page, query, max_results)
        if not results:
            return f"未找到与 {query!r} 相关的搜索结果（DuckDuckGo 和 Bing 都没有返回）。"

        info = await _deep_dive(context, results, pages)
        info += "其他网站的摘要信息：\n"
        for r in results:
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
        # Deliberately do NOT close the context — it is the shared singleton
        # also used by access_website; closing it would break the other tools.
