"""Per-session in-memory context state.

A :class:`Session` mirrors the runtime state the QQ bot's ``Qwen`` instance
used to hold per group (``history``, ``embedding_buffer``, ``summary``,
``last_reply``, dataset ``conversations``), but keyed by an explicit
``session_id`` (e.g. ``qq:12345``) owned by the calling channel.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List


@dataclass
class Session:
    session_id: str
    max_history: int = 40
    history: List[Dict] = field(default_factory=list)
    embedding_buffer: List[int] = field(default_factory=list)
    summary: str = ""
    last_reply: datetime = field(default_factory=datetime.now)
    conversations: List = field(default_factory=list)
    _summarizing: bool = False
    _trunc_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @property
    def cut_point(self) -> int:
        return min(20, int(self.max_history / 2))
