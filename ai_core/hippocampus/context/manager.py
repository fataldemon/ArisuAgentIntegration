"""ContextManager -- the central conversation-context API.

Owns per-session in-memory state and durable persistence (via the
hippocampus chat-history DAO). Channels reach this over HTTP today
(see ``hippocampus.router``); AI Core can call it in-process later.

History truncation + summary are *self-managed*: triggered automatically
in the background after a message is saved, so callers never block and
never need to know about it.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from hippocampus.context.session import Session
from hippocampus.context.summarizer import SummarizeFn, default_summarize
from hippocampus.context import dataset as ds
from hippocampus.dao import chat_history as dao


def _build_msg(role: str, content: str, ts: Optional[datetime] = None) -> Dict:
    return {"role": role, "content": content, "_timestamp": ts or datetime.now()}


class ContextManager:
    def __init__(self, summarize_fn: Optional[SummarizeFn] = None):
        self._sessions: Dict[str, Session] = {}
        self._create_lock = asyncio.Lock()
        self._summarize_fn: Optional[SummarizeFn] = summarize_fn

    def set_summarize_fn(self, fn: Optional[SummarizeFn]) -> None:
        self._summarize_fn = fn

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------
    async def get_session(self, session_id: str, max_history: int = 40) -> Session:
        sess = self._sessions.get(session_id)
        if sess is not None:
            return sess
        async with self._create_lock:
            sess = self._sessions.get(session_id)
            if sess is not None:
                return sess
            sess = Session(session_id=session_id, max_history=max_history)
            history, summary, last_reply = await asyncio.to_thread(
                dao.load_recent_history, session_id, sess.cut_point
            )
            sess.history = history
            sess.summary = summary
            sess.last_reply = last_reply
            self._sessions[session_id] = sess
            return sess

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str = "",
        thought: str = "",
        action_name: str = "",
        action_input: str = "",
        request_id: str = "",
        is_summary: int = 0,
        append_to_history: bool = True,
        max_history: int = 40,
    ) -> int:
        sess = await self.get_session(session_id, max_history=max_history)
        ts = datetime.now()
        row_id = await asyncio.to_thread(
            dao.save_chat_record,
            session_id, role, content, thought, action_name, action_input,
            "", request_id, ts, is_summary,
        )
        if is_summary:
            sess.summary = content
        elif append_to_history:
            sess.history.append(_build_msg(role, content, ts))
            if role in ("user", "assistant", "function"):
                sess.last_reply = ts
            self._schedule_truncate(sess)
        return row_id

    async def load_history(self, session_id: str, limit: int = 40) -> List[Dict]:
        history, summary, last_reply = await asyncio.to_thread(
            dao.load_recent_history, session_id, limit
        )
        sess = await self.get_session(session_id)
        sess.history = history
        sess.summary = summary
        sess.last_reply = last_reply
        return history

    # ------------------------------------------------------------------
    # Time annotation (>10min -> "X分钟过去了", >12h -> reset history)
    # ------------------------------------------------------------------
    async def build_time_annotation(self, session_id: str) -> Tuple[str, bool]:
        sess = await self.get_session(session_id)
        if not sess.history:
            return "", False
        diff = int((datetime.now() - sess.last_reply).total_seconds())
        if diff <= 10 * 60:
            return "", False
        if diff < 3600:
            return f"（{diff // 60}分钟过去了。）\n", False
        if diff < 3600 * 12:
            return f"（{diff // 3600}小时过去了。）\n", False
        # long gap: reset in-memory history from DB
        history, summary, last_reply = await asyncio.to_thread(
            dao.load_recent_history, session_id, sess.cut_point
        )
        sess.history = history
        sess.summary = summary
        sess.last_reply = last_reply
        if diff < 3600 * 24:
            return "（半天之后。）\n", True
        return f"（{diff // (3600 * 24)}天之后。）\n", True

    # ------------------------------------------------------------------
    # Memory recall
    # ------------------------------------------------------------------
    async def recall(
        self,
        session_id: str,
        time_range: str = "",
        keywords: str = "",
        limit: int = 5,
        context_lines: int = 1,
    ) -> str:
        return await asyncio.to_thread(
            dao.recall_memory, session_id, time_range, keywords, limit, context_lines
        )

    # ------------------------------------------------------------------
    # Turn context (full delegation: one call gets everything a channel
    # needs to build the next LLM request)
    # ------------------------------------------------------------------
    async def turn_context(self, session_id: str, max_history: int = 40) -> Dict:
        """Return the current in-memory history + time annotation + summary.

        The in-memory ``session.history`` is the source of truth here (kept up
        to date by save_message / background truncation / >12h reset), so a
        fully-delegated channel never needs to hold history itself.
        """
        sess = await self.get_session(session_id, max_history=max_history)
        annotation, was_reset = await self.build_time_annotation(session_id)
        return {
            "history": list(sess.history),
            "time_annotation": annotation,
            "was_reset": was_reset,
            "summary": sess.summary,
        }

    async def clear_session(self, session_id: str) -> None:
        """Clear the in-memory session (history/summary/dataset). The DB rows
        are NOT deleted -- mirrors the QQ bot's ``clear_memory`` (forget for
        the current conversation; rows remain for recall + restart recovery).
        """
        sess = await self.get_session(session_id)
        if sess.conversations:
            convs = list(sess.conversations)
            sess.conversations = []
            await asyncio.to_thread(ds.record_dialog_in_file, convs, "")
        sess.history = []
        sess.summary = ""

    def list_sessions(self) -> List[Dict]:
        """Active in-memory sessions with their last_reply (for reminder
        scheduling -- picking the most-recently-active group, etc.)."""
        return [
            {"session_id": s.session_id, "last_reply": s.last_reply.isoformat()}
            for s in self._sessions.values()
        ]

    def list_user_sessions(self, prefix: str) -> List[Dict]:
        """All sessions matching a prefix (e.g. ``chat:老师:``), queried from
        the DB so they survive AI Core restarts. Used for the Chat page's
        session sidebar."""
        return dao.list_sessions_by_prefix(prefix)

    # ------------------------------------------------------------------
    # Dataset collection
    # ------------------------------------------------------------------
    async def record_dataset(
        self,
        session_id: str,
        role: str,
        content: str,
        functions: Optional[List[Dict]] = None,
        is_first: bool = False,
    ) -> None:
        sess = await self.get_session(session_id)
        if is_first:
            conv = ds.create_first_conversation({"role": role, "content": content}, functions or [])
        else:
            conv = ds.create_conversation({"role": role, "content": content})
        sess.conversations.append(conv)

    async def flush_dataset(self, session_id: str, embeddings: str = "") -> None:
        sess = await self.get_session(session_id)
        if not sess.conversations:
            return
        convs = list(sess.conversations)
        sess.conversations = []
        await asyncio.to_thread(ds.record_dialog_in_file, convs, embeddings)

    # ------------------------------------------------------------------
    # Self-managed truncation (background, channel-transparent)
    # ------------------------------------------------------------------
    def _schedule_truncate(self, sess: Session) -> None:
        if len(sess.history) <= sess.max_history or sess._summarizing:
            return
        if self._summarize_fn is None:
            return  # no LLM available -> skip (don't drop history)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        asyncio.create_task(self._truncate(sess))

    async def _truncate(self, sess: Session) -> None:
        # Serialise truncation per session: concurrent saves may keep
        # appending during the summary await (history only grows), but two
        # truncations must never interleave (that is what corrupts drop_count).
        async with sess._trunc_lock:
            if len(sess.history) <= sess.max_history:
                return
            sess._summarizing = True
            try:
                # flush pending dataset turns first (mirrors QQ bot behaviour)
                if sess.conversations:
                    convs = list(sess.conversations)
                    sess.conversations = []
                    await asyncio.to_thread(ds.record_dialog_in_file, convs, "")

                cut_point = sess.cut_point
                while cut_point > 0 and sess.history[-cut_point]["role"] != "user":
                    cut_point -= 1
                if cut_point == 0:
                    cut_point = 1
                drop_count = len(sess.history) - cut_point

                summary = await self._conclude_summary(sess, cut_point)
                if not summary:
                    print(f"[hippocampus] summary aborted for {sess.session_id}")
                    return

                # history may have grown (new saves) during the await; clamp.
                if drop_count >= len(sess.history):
                    drop_count = len(sess.history) - 1
                if drop_count < 0:
                    return
                user_content = sess.history[drop_count]["content"]
                new_history = [
                    _build_msg("user", f"（{summary}）\n{user_content}")
                ] + sess.history[drop_count + 1:]
                sess.history = new_history
                print(f"[hippocampus] truncated {sess.session_id}: new length {len(sess.history)}")
            finally:
                sess._summarizing = False

    async def _conclude_summary(self, sess: Session, cut_point: int) -> Optional[str]:
        prev_summary = sess.summary if sess.summary else "无"
        dialog_history = [m["content"] for m in sess.history[:-cut_point] if "content" in m]
        prompt = (
            f"前情提要：{prev_summary}\n\n对话历史：{dialog_history}\n\n"
            "综合上面的前情提要和对话历史中的剧情，为爱丽丝汇总成400字以内的记忆摘要，"
            "记忆摘要要求用讲述故事的语气，长度适中，"
            "需要忠实地反映出最近的对话内容，思考过程尽量简略。另外，需要用markdown的格式记录下对话历史中需要长期记忆的人物和关键细节信息。"
            "下面是记忆摘要："
        )
        fn = self._summarize_fn
        if fn is None:
            return None
        try:
            raw = await fn(prompt)
        except Exception as e:
            print(f"[hippocampus] summarize_fn failed: {e}")
            return None
        if not raw:
            return None
        summary = (
            f"**历史摘要**\n{raw}\n"
            "提示：你可以通过**recall_memory**函数回忆之前的具体对话信息。"
        )
        sess.summary = summary
        await asyncio.to_thread(
            dao.save_chat_record,
            sess.session_id, "system", summary, "", "", "", "", "", None, 1,
        )
        return summary


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------
_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    global _manager
    if _manager is None:
        _manager = ContextManager(summarize_fn=default_summarize)
    return _manager
