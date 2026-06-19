from datetime import datetime
from typing import Optional, List, Dict, Mapping, Any, Iterator
import requests
from abc import ABC, abstractmethod


class LLM(ABC):
    temperature: float = 0.95
    top_p: float = 0.7
    top_k: int = None
    repetition_penalty: float = None
    system: str = ""
    max_history = 20
    embedding_buffer = []
    history: Any = []
    history_display: Any = []
    conversations = []
    summary = ""
    functions = []
    # 部署大模型服务的url
    url = "http://localhost:8000/v1/chat/completions"
    url_assistant = "http://localhost:8000/assistant/v1/chat/completions"

    # 上次对话的时间
    last_reply = datetime.now()

    def __init__(self, url: str, url_assistant: str, temperature: float = 0.95, top_p: float = 0.7, top_k: int = None,
                 repetition_penalty: float = None, max_history: int = 20):
        self.url = url
        self.url_assistant = url_assistant if url_assistant else ""
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.repetition_penalty = repetition_penalty
        self.max_history = max_history

    @property
    def _llm_type(self) -> str:
        return "local_llm"

    @classmethod
    def _post(cls, url: str, query: Dict) -> Any:
        """POST请求
        """
        _headers = {"Content-Type": "application/json"}
        with requests.session() as sess:
            resp = sess.post(
                url,
                headers=_headers,
                json=query,
                timeout=60,
            )
        return resp

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        """Get the identifying parameters.
        """
        _param_dict = {
            "url": self.url,
            "url": self.url_assistant if self.url_assistant else self.url,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "repetition_penalty": self.repetition_penalty,
            "max_history": self.max_history,
        }
        return _param_dict

    @abstractmethod
    async def _construct_query(self, prompt, tools, **kwargs): pass

    @abstractmethod
    async def call(self, prompt, tools, **kwargs): pass

    @abstractmethod
    async def shorten_history(self): pass







