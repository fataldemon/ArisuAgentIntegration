import asyncio
import random
import traceback

from playwright.async_api import async_playwright


async def online_search_func(item: str) -> str:
    async with async_playwright() as p:
        try:
            # 设置 User-Agent
            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
            )

            # 启动浏览器并设置上下文
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=user_agent)  # 设置 User-Agent
            page = await context.new_page()

            # 初始化变量
            pages = []
            info = ""
            page_no = 0
            moegirl_token = False
            baike_token = False
            wiki_token = False
            max_retries = 5
            retries = 0

            while retries < max_retries:
                try:
                    await page.goto("https://www.bing.com/search?q="+item)
                    await asyncio.sleep(random.uniform(1, 2))  # 添加随机延迟
                    # 检查页面是否加载成功（以搜索结果为例）
                    url_list = await page.query_selector_all(".b_algo >> .tilk")
                    # summary_list = await page.query_selector_all(".b_algo >> .b_lineclamp2")
                    # 获取 .b_algo >> .b_lineclamp2 的元素
                    lineclamp_elements = await page.query_selector_all(".b_algo >> .b_lineclamp2")
                    # 获取 .qna_body 的元素
                    qna_body_elements = await page.query_selector_all(".qna_body")
                    # 获取 .qna_body 的元素
                    core_layer_elements = await page.query_selector_all(".wtr_core")
                    # 合并两个列表
                    summary_list = core_layer_elements + qna_body_elements + lineclamp_elements
                    if not url_list:
                        raise Exception("未找到搜索结果，重试中...")
                    break
                except Exception as e:
                    retries += 1
                    print(f"尝试第 {retries} 次加载失败: {e}")
                    if retries >= max_retries:
                        raise Exception("多次尝试加载失败，停止重试。")
                        return "ERROR"

            for i in url_list:
                url = await i.get_attribute("href")
                if page_no >= 2 or (moegirl_token and baike_token):
                    break
                try:
                    if url.startswith("https://zh.moegirl.org.cn") and (not moegirl_token):
                        pages.append(await context.new_page())
                        await pages[page_no].goto(url)
                        await asyncio.sleep(random.uniform(1, 2))
                        box_locator = await pages[page_no].query_selector(".mw-parser-output >> .moe-infobox")
                        box_content = await box_locator.text_content()
                        box_content = box_content.replace("\n\n\n", "")
                        info += f"根据{url}网站提供的信息如下：\n{box_content}\n"
                        context_locator = await pages[page_no].query_selector_all(
                            ".mw-parser-output > h2:not(table *), .mw-parser-output > h3:not(table *), "
                            ".mw-parser-output > h4:not(table *), .mw-parser-output > p:not(table *), "
                            ".mw-parser-output > ul:not(table *)")
                        for item in context_locator:
                            search_info = await item.text_content()
                            search_info = search_info.replace("\n\n", "")
                            info += search_info + "\n"
                        page_no += 1
                        moegirl_token = True
                    elif url.startswith("https://baike.baidu") and (not baike_token):
                        pages.append(await context.new_page())
                        await pages[page_no].goto(url)
                        await asyncio.sleep(random.uniform(1, 2))
                        # context_locator = await pages[page_no].query_selector(".lemmaSummary_c2Xg9")
                        context_locator = await pages[page_no].query_selector(".J-summary")
                        summary = await context_locator.text_content()
                        box_locator = await pages[page_no].query_selector(".J-basic-info")
                        brief_info = await box_locator.text_content()
                        info += f"根据{url}网站提供的信息如下：\n{brief_info}\n{summary}\n"
                        page_no += 1
                        baike_token = True
                    elif url.startswith("https://zh.wikipedia.org") or url.startswith("https://en.wikipedia.org") and (not wiki_token):
                        pages.append(await context.new_page())
                        await pages[page_no].goto(url)
                        await asyncio.sleep(random.uniform(1, 2))
                        context_locator = await pages[page_no].query_selector_all(
                            ".mw-parser-output > h2:not(table *), .mw-parser-output > h3:not(table *), "
                            ".mw-parser-output > h4:not(table *), .mw-parser-output > p:not(table *), "
                            ".mw-parser-output > ul:not(table *)")
                        for item in context_locator:
                            search_info = await item.text_content()
                            print(search_info.replace("\n\n", ""))
                        page_no += 1
                except Exception as e:
                    traceback.print_exc()
                    info += f"地址{url}上或许能得到有用的信息，但是目前无法访问......\n"
            info += f"其他网站的摘要信息：\n"
            num = 1
            for summary_item in summary_list:
                info += f"摘要{num}:[{await summary_item.text_content()}]"
                info += "\n"
                num += 1
            await context.close()
            await browser.close()
        except Exception as e:
            info = "ERROR"
        return info


if __name__ == "__main__":
    info = asyncio.run(online_search_func("上海天气"))
    print(info)
