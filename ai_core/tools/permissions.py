"""Permission model and pending-confirmation queue.

When the Agent Loop encounters a tool whose ``permission_level`` is WRITE or
CONTROL, it creates a *pending request* and returns the ``function_call`` to
the front-end so the user can confirm or reject it.

PendingManager
    create_pending(tool_name, args) -> request_id
    resolve(request_id, approved) -> ToolResult | None
    get(request_id) -> PendingRequest | None
    expire(ttl_seconds) -> remove stale requests
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class PendingRequest:
    request_id: str
    tool_name: str
    arguments: Dict[str, Any]
    created_at: float = field(default_factory=time.time)


class PendingManager:
    def __init__(self, ttl_seconds: int = 300) -> None:
        self._pending: Dict[str, PendingRequest] = {}
        self._ttl = ttl_seconds

    def create_pending(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        request_id = uuid.uuid4().hex[:12]
        self._pending[request_id] = PendingRequest(
            request_id=request_id,
            tool_name=tool_name,
            arguments=arguments,
        )
        return request_id

    def get(self, request_id: str) -> Optional[PendingRequest]:
        self._expire_stale()
        return self._pending.get(request_id)

    def resolve(self, request_id: str, approved: bool) -> Optional[PendingRequest]:
        self._expire_stale()
        req = self._pending.pop(request_id, None)
        if req is None:
            return None
        if not approved:
            req.arguments = {"_rejected": True}
        return req

    def _expire_stale(self) -> None:
        now = time.time()
        stale = [rid for rid, r in self._pending.items() if now - r.created_at > self._ttl]
        for rid in stale:
            self._pending.pop(rid, None)


_singleton: Optional[PendingManager] = None


def get_pending_manager() -> PendingManager:
    global _singleton
    if _singleton is None:
        _singleton = PendingManager()
    return _singleton
