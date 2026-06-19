import asyncio
import datetime
import queue
import time

from dao.status import get_status_description
from functions.function_call import get_general_tools
from llmClient.llm import LLM
from llmClient.local import LocalLLMObject


def init_status() -> str:
    status = get_status_description()

    current_time = datetime.datetime.now()
    current_date_str = current_time.strftime("今天是%Y年%m月%d日")
    hour = current_time.hour
    if 0 <= hour < 5:
        time_period = "凌晨"
    elif 5 <= hour < 9:
        time_period = "早上"
    elif 9 <= hour < 12:
        time_period = "上午"
    elif 12 <= hour < 14:
        time_period = "中午"
        hour = hour - 12
    elif 14 <= hour < 17:
        time_period = "下午"
        hour = hour - 12
    elif 17 <= hour < 19:
        time_period = "傍晚"
        hour = hour - 12
    elif 19 <= hour < 24:
        time_period = "晚上"
        hour = hour - 12
    current_time_str = current_time.strftime(f"当前时间：{time_period}%H点%M分%S秒。")
    if current_time.weekday() == 0:
        weekday = "一"
    elif current_time.weekday() == 1:
        weekday = "二"
    elif current_time.weekday() == 2:
        weekday = "三"
    elif current_time.weekday() == 3:
        weekday = "四"
    elif current_time.weekday() == 4:
        weekday = "五"
    elif current_time.weekday() == 5:
        weekday = "六"
    else:
        weekday = "日"
    dater = f"{current_date_str}，星期{weekday}，{current_time_str}"
    status = status + "\n" + dater
    return status


class LLMManager:
    llm: LLM = None

    def __init__(self):
        self.lock = False
        self.comments_queue = ""

    def start_llm(self, url: str, url_assistant: str, temperature: float = 0.94, top_p: float = 0.7, top_k: int = 20,
                  repetition_penalty: float = None, max_history: int = 20) -> LLM:
        self.llm = LocalLLMObject(
            url=url,
            url_assistant=url_assistant,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            repetition_penalty=repetition_penalty,
            max_history=max_history
        )
        return self.llm

    def end_llm(self):
        self.llm = None

    def call_llm(self, prompt) -> str:
        if self.llm is not None:
            # 初始化工具类
            tools = get_general_tools()
            status = init_status()
            while self.lock:
                time.sleep(0.1)
            self.lock = True
            thought, response, feedback, finish_reason, action_name = asyncio.run(
                self.llm.call(
                    prompt,
                    embedding="",
                    status=status,
                    tools=tools
                )
            )
            asyncio.run(self.llm.shorten_history())
            self.lock = False
            return response
        else:
            return "..."

    def call_llm_by_comments(self, prompt) -> str:
        default_embedding = "你现在正在bilibili进行直播，代替老师和观众互动。你需要尽量作出多样性的回答，避免重复的回答。"
        if self.llm is not None:
            # 初始化工具类
            tools = get_general_tools()
            status = init_status()
            # 将弹幕存入缓存
            if self.comments_queue:
                self.comments_queue += f"\n{prompt}"
            else:
                self.comments_queue = prompt
            while self.lock:
                time.sleep(0.1)
            if self.comments_queue != "":
                self.lock = True
                # 提取组合的弹幕，并清除弹幕缓存
                comments = self.comments_queue
                self.comments_queue = ""
                thought, response, feedback, finish_reason, action_name = asyncio.run(
                    self.llm.call(
                        comments,
                        embedding=default_embedding,
                        status=status,
                        tools=tools
                    )
                )
                asyncio.run(self.llm.shorten_history())
                self.lock = False
                return response
            else:
                return
        else:
            return "..."
