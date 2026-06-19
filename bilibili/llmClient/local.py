import asyncio
import os.path
import logging
import requests
import json
from typing import Optional, List, Dict, Mapping, Any, Iterator
import re
from datetime import datetime
from utils.utils import remove_emotion

from functions.function_call import skill_call
from functions.dataset_collection import create_first_conversation, create_conversation, get_json
from llmClient.llm import LLM

logging.basicConfig(level=logging.INFO)


def get_value_in_brackets(tool_call):
    pattern = r'\((.*?)\)'
    match = re.search(pattern, tool_call)
    if match:
        return match.group(1)
    else:
        return None


def extract_code(text: str) -> str:
    pattern = r'```([^\n]*)\n(.*?)```'
    matches = re.findall(pattern, text, re.DOTALL)
    return matches[-1][1]


class LocalLLMObject(LLM):
    def record_dialog_in_file(self, content: str):
        current_date = datetime.now()
        formatted_date = current_date.strftime("%Y-%m-%d")
        file = f"MyDataset-{formatted_date}.json"
        if not os.path.exists(file):
            with open(file, 'a', encoding="utf-8") as f:
                f.write(content)
        else:
            with open(file, 'a', encoding="utf-8") as f:
                f.write(',\n' + content)
        self.conversations = []

    async def shorten_history(self):
        # 总结历史并缩短上下文，以节省空间
        if len(self.history) > self.max_history:
            # 存储数据集
            self.record_dialog_in_file(get_json(self.conversations, ""))
            # temp_history = self.history[-self.max_history:]
            int_index = 8
            while self.history[-int_index]["role"] != "user":
                int_index += 2
            await self.conclude_summary(int_index)
            print(f"历史总结：{self.summary}")
            user_content = self.history[-int_index:][0]["content"]
            temp_history = [{"role": "user",
                             "content": f"（{self.summary}）\n{user_content}"}] + self.history[-int_index + 1:]
            self.history = temp_history
            self.history_display = [{"role": "user",
                                     "content": f"（{self.summary}）\n{user_content}"}] + self.history_display[-int_index + 1:]
            print("Head of history: " + str(temp_history[0]))

        print(f"历史长度：{len(self.history)}")

    def _construct_query(self, prompt: str, tools, **kwargs) -> Dict:
        """构造请求体
        """
        embedding = []
        status = ""
        for key, value in kwargs.items():
            if key == "embedding":
                embedding = value
            elif key == "status":
                status = value
        prompt = prompt.replace("\n（提示：）", "")

        time_diff = datetime.now() - self.last_reply
        # 若时间超过10分钟就描述时间的流逝
        if self.history != [] and time_diff.seconds > 10 * 60:
            if time_diff.seconds < 60 * 60:
                minutes_diff = time_diff.seconds // 60
                prompt = f"（{minutes_diff}分钟过去了。）\n{prompt}"
            else:
                self.history = []
                self.history_display = []
                # 存储数据集
                self.record_dialog_in_file(get_json(self.conversations, ""))

        messages = self.history + [{"role": "user", "content": prompt}]
        query = {
            "character": "tendou_arisu",
            "functions": tools,
            "system": self.system,
            "model": "gpt-3.5-turbo",
            "messages": messages,
            "information": f"{embedding}\n{status}",
            "on_embedding": True,
            "embeddings_buffer": self.embedding_buffer,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stream": False,  # 不启用流式API
        }
        if self.repetition_penalty is not None:
            query["repetition_penalty"] = self.repetition_penalty
        if self.top_k is not None:
            query["top_k"] = self.top_k
        # 查找提示信息的位置，不加入历史
        tip_p = prompt.rfind("\n（提示：")
        if tip_p >= 0:
            raw_prompt = prompt[:tip_p]
        else:
            raw_prompt = prompt

        # 格式化数据集
        if not self.history:
            self.conversations.append(
                create_first_conversation({"role": "user", "content": raw_prompt}, self.functions))
        else:
            self.conversations.append(create_conversation({"role": "user", "content": raw_prompt}))
        self.history = self.history + [{"role": "user", "content": raw_prompt}]
        self.history_display = self.history_display + [{"role": "user", "content": raw_prompt}]

        # 记录上次会话时间
        self.last_reply = datetime.now()

        return query

    def _construct_assistant_query(self, prompt: str, type: int, **kwargs) -> Dict:
        """构造请求体
        """
        status = ""
        for key, value in kwargs.items():
            if key == "embedding":
                embedding = value
            elif key == "status":
                status = value
        messages = [{"role": "user", "content": prompt}]
        query = {
            "functions": self.functions,
            "system": self.system,
            "model": "gpt-3.5-turbo",
            "messages": messages,
            "embeddings": "",
            "temperature": 0.9,
            "top_p": 0.6,
            "stream": False,  # 不启用流式API
            "type": type
        }
        return query

    def _construct_observation(self, prompt: str, tools, **kwargs) -> Dict:
        """构造请求体
        """
        embedding = []
        for key, value in kwargs.items():
            if key == "embedding":
                embedding = value
        messages = self.history + [{"role": "function", "content": prompt}]
        query = {
            "functions": tools,
            "system": self.system,
            "model": "gpt-3.5-turbo",
            "messages": messages,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stream": False,  # 不启用流式API
        }
        # 格式化数据集
        self.conversations.append(create_conversation({"role": "function", "content": f"Observation: {prompt}"}))
        self.history = messages
        self.history_display = self.history_display + [{"role": "function", "content": prompt}]
        return query

    def clear_memory(self):
        """
        清除聊天记忆
        :return:
        """
        self.history = []
        self.history_display = []
        # 存储数据集
        self.record_dialog_in_file(get_json(self.conversations, ""))

    async def call_assistant(self, prompt: str, get_think: bool = False, type: int = 0, **kwargs) -> str:
        """调用函数
        """
        embedding = []
        status = ""
        for key, value in kwargs.items():
            if key == "embedding":
                embedding = value
            elif key == "status":
                status = value
        # construct query
        query = self._construct_assistant_query(prompt=prompt, embedding=embedding, status=status, type=type)
        # post
        resp = self._post(url=self.url_assistant, query=query)
        if resp.status_code == 200:
            resp_json = json.loads(resp.text)

            predictions = resp_json['choices'][0]['message']['content'].strip()
            if "<think>" in predictions and "</think>" in predictions:
                index_t = predictions.rfind("</think>\n\n")
                if index_t != -1:
                    thought = predictions[:index_t + len("</think>")]
                    thought = thought.replace("<think>", "").replace("</think>", "").strip()
                    if thought == "":
                        thought = "无"
                    reply = predictions[index_t + len("</think>\n\n"):]
                if get_think:
                    predictions = f"【思路】\n{thought}\n\n【回答】\n{reply}"
                else:
                    predictions = reply
            return predictions
        else:
            return "爱丽丝现在不在线，请于滴声后留言~"

    async def conclude_summary(self, cut_point) -> str:
        if self.summary != "":
            summary_temp = self.summary
        else:
            summary_temp = "无"

        dialog_history = ""
        for conversation in self.history[:-cut_point]:
            dialog_history += conversation["content"] + "\n"

        summary_prompt = f"前情提要：{summary_temp}\n\n对话历史：{dialog_history}\n\n" \
                         f"综合上面的前情提要和对话历史中的剧情，为爱丽丝汇总成150字以内的记忆片段，并提取出需要长期记忆的重要细节信息。" \
                         f"对话历史要求用讲述故事的语气，长度适中，需要保留对话历史中的人物和关键信息，并且反映最近的对话内容："
        self.summary = await self.call_assistant(summary_prompt)
        return self.summary

    async def call(self, prompt: str, tools, **kwargs) -> tuple:
        """调用函数
        """
        embedding = []
        status = ""
        for key, value in kwargs.items():
            if key == "embedding":
                embedding = value
            elif key == "status":
                status = value
        # construct query
        query = self._construct_query(prompt=prompt, embedding=embedding, status=status, tools=tools)
        # self.record_dialog_in_file(role="user", content=prompt)
        try:
            resp = self._post(url=self.url, query=query)
        except requests.exceptions.ConnectionError:
            self.history = self.history[:-1]
            self.history_display = self.history_display[:-1]
            return "", "爱丽丝现在不在线，请于滴声后留言~", "", "", ""
        if resp.status_code == 200:
            resp_json = json.loads(resp.text)
            finish_reason = resp_json['choices'][0]['finish_reason']
            if finish_reason == "function_call":
                predictions = resp_json['choices'][0]['message']['content'].strip()
                thought = resp_json['choices'][0]['thought'].strip()
                action = resp_json['choices'][0]['message']['function_call']
                action_name = action['name']
                action_input = action['arguments']
                try:
                    feedback = await skill_call(action_name, json.loads(action_input))
                except json.decoder.JSONDecodeError:
                    feedback = "（不合法的输入参数）"
                if predictions != "":
                    if thought != "":
                        # 格式化数据集
                        self.conversations.append(create_conversation({"role": "assistant",
                                                                       "content": f"Thought: {thought}\nAnswer: {predictions}\nAction: {action_name}\nAction Input: {action_input}"}))
                        self.history = self.history + [{"role": "assistant",
                                                        "content": f"Thought: {thought}\nAnswer: {predictions}\nAction: {action_name}\nAction Input: {action_input}"}]
                        self.history_display = self.history_display + [
                            {"role": "assistant", "content": remove_emotion(predictions)}]
                    else:
                        # 格式化数据集
                        self.conversations.append(create_conversation({"role": "assistant",
                                                                       "content": f"Answer: {predictions}\nAction: {action_name}\nAction Input: {action_input}"}))
                        self.history = self.history + [{"role": "assistant",
                                                        "content": f"Answer: {predictions}\nAction: {action_name}\nAction Input: {action_input}"}]
                        self.history_display = self.history_display + [
                            {"role": "assistant", "content": remove_emotion(predictions)}]
                else:
                    # 格式化数据集
                    self.conversations.append(create_conversation({"role": "assistant",
                                                                   "content": f"Thought: {thought}\nAction: {action_name}\nAction Input: {action_input}"}))
                    self.history = self.history + [{"role": "assistant",
                                                    "content": f"Thought: {thought}\nAction: {action_name}\nAction Input: {action_input}"}]

                print(f"历史长度：{len(self.history)}")
                return thought, predictions, feedback, finish_reason, action_name
            else:
                predictions = resp_json['choices'][0]['message']['content'].strip()
                thought = resp_json['choices'][0]['thought'].strip()
                self.embedding_buffer = resp_json['choices'][0]['embedding_list']
                print(f"查到的设定信息编号为：{self.embedding_buffer}")
                # 格式化数据集
                self.conversations.append(create_conversation(
                    {"role": "assistant", "content": f"Thought: {thought}\nFinal Answer: {predictions}"}))
                self.history = self.history + [
                    {"role": "assistant", "content": f"Thought: {thought}\nFinal Answer: {predictions}"}]
                self.history_display = self.history_display + [
                    {"role": "assistant", "content": remove_emotion(predictions)}]

                return thought, predictions, "", finish_reason, ""
        else:
            return "", "爱丽丝现在不在线，请于滴声后留言~", "", "", ""

    async def send_feedback(self, feedback: str, tools, stop: Optional[List[str]] = None, **kwargs) -> tuple:
        observation = self._construct_observation(prompt=feedback, tools=tools)
        resp = self._post(url=self.url, query=observation)
        if resp.status_code == 200:
            resp_json = json.loads(resp.text)
            finish_reason = resp_json['choices'][0]['finish_reason']
            if finish_reason == "function_call":
                predictions = resp_json['choices'][0]['message']['content'].strip()
                thought = resp_json['choices'][0]['thought'].strip()
                action = resp_json['choices'][0]['message']['function_call']
                action_name = action['name']
                action_input = action['arguments']
                print(f"Action Input: {action_input}")
                feedback = await skill_call(action_name, json.loads(action_input))
                if predictions != "":
                    # 格式化数据集
                    self.conversations.append(create_conversation(
                        {"role": "assistant",
                         "content": f"Thought: {thought}\nAnswer: {predictions}\nAction: {action_name}\nAction Input: {action_input}"}))
                    self.history = self.history + [{"role": "assistant",
                                                    "content": f"Thought: {thought}\nAnswer: {predictions}\nAction: {action_name}\nAction Input: {action_input}"}]
                    self.history_display = self.history_display + [
                        {"role": "assistant", "content": remove_emotion(predictions)}]
                else:
                    # 格式化数据集
                    self.conversations.append(create_conversation(
                        {"role": "assistant",
                         "content": f"Thought: {thought}\nAction: {action_name}\nAction Input: {action_input}"}))
                    self.history = self.history + [{"role": "assistant",
                                                    "content": f"Thought: {thought}\nAction: {action_name}\nAction Input: {action_input}"}]
                    self.history_display = self.history_display + [
                        {"role": "assistant", "content": remove_emotion(predictions)}]

                print(f"历史长度：{len(self.history)}")
                return thought, predictions, feedback, finish_reason, action_name
            else:
                predictions = resp_json['choices'][0]['message']['content'].strip()
                thought = resp_json['choices'][0]['thought'].strip()
                # 格式化数据集
                self.conversations.append(create_conversation(
                    {"role": "assistant", "content": f"Thought: {thought}\nFinal Answer: {predictions}"}))
                self.history = self.history + [
                    {"role": "assistant", "content": f"Thought: {thought}\nFinal Answer: {predictions}"}]
                self.history_display = self.history_display + [{"role": "assistant", "content": predictions}]

                return thought, predictions, "", finish_reason, ""
        else:
            return "", "爱丽丝现在不在线，请于滴声后留言~", "", "", ""


if __name__ == "__main__":
    llm = LocalLLMObject(temperature=0.94, top_p=0.6, max_history=30, repetition_penalty=1.08)
    response = asyncio.run(llm.call("邦邦咔邦", tools=[]))
    print(response)
