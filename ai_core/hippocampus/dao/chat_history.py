"""Dedicated chat-history persistence for hippocampus (raw sqlite3).

This is an *independent* re-implementation of the QQ bot's
``src/dao/chat_history.py`` (which uses SQLAlchemy). It writes to the same
``t_chat_history`` table + ``t_chat_history_fts`` FTS5 virtual table, but:

* uses raw ``sqlite3`` (no new dependency, matches ``db/init_db.py`` style);
* takes an explicit ``session_id`` instead of the QQ-bot ContextVar; the
  ``session_id`` value is stored in the existing ``group_id`` column.

Because hippocampus uses namespaced session ids (e.g. ``qq:12345``) while
the QQ bot stores bare ids (e.g. ``12345``), the two writers never read
each other's rows even though they share the table.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from hippocampus.db.engine import get_connection

_TS_FMT = "%Y-%m-%d %H:%M:%S"


def _now_str() -> str:
    return datetime.now().strftime(_TS_FMT)


def _fmt_ts(dt: datetime) -> str:
    return dt.strftime(_TS_FMT)


def _parse_ts(value) -> datetime:
    if isinstance(value, datetime):
        return value
    s = str(value)
    for fmt in (_TS_FMT, "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return datetime.now()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_schema() -> None:
    """Create the t_chat_history table + indexes if absent (idempotent)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS t_chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id VARCHAR(50) NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                role VARCHAR(20) NOT NULL,
                content TEXT,
                thought TEXT,
                action_name VARCHAR(50),
                action_input TEXT,
                function_output TEXT,
                request_id VARCHAR(50),
                is_summary INTEGER DEFAULT 0
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_group_summary_time "
            "ON t_chat_history (group_id, is_summary, timestamp)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_request_id ON t_chat_history (request_id)"
        )
        conn.commit()
    finally:
        conn.close()


def init_fts() -> None:
    """Initialise FTS5 virtual table + triggers (idempotent)."""
    init_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        existing = {
            r[0]
            for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
            ).fetchall()
        }
        if "t_chat_history_fts" not in existing:
            cur.execute(
                "CREATE VIRTUAL TABLE t_chat_history_fts "
                "USING fts5(content, tokenize = 'unicode61')"
            )
            print("[FTS] virtual table t_chat_history_fts created")
        count = cur.execute("SELECT COUNT(*) FROM t_chat_history_fts").fetchone()[0]
        if count == 0:
            cur.execute(
                "INSERT INTO t_chat_history_fts(rowid, content) "
                "SELECT id, content FROM t_chat_history "
                "WHERE content IS NOT NULL AND content != ''"
            )
            synced = cur.execute("SELECT COUNT(*) FROM t_chat_history_fts").fetchone()[0]
            print(f"[FTS] synced {synced} rows into full-text index")
        for sql in (
            """
            CREATE TRIGGER IF NOT EXISTS t_chat_history_ai
            AFTER INSERT ON t_chat_history
            BEGIN
                INSERT INTO t_chat_history_fts(rowid, content)
                VALUES (new.id, new.content);
            END;
            """,
            """
            CREATE TRIGGER IF NOT EXISTS t_chat_history_ad
            AFTER DELETE ON t_chat_history
            BEGIN
                DELETE FROM t_chat_history_fts WHERE rowid = old.id;
            END;
            """,
            """
            CREATE TRIGGER IF NOT EXISTS t_chat_history_au
            AFTER UPDATE OF content ON t_chat_history
            BEGIN
                UPDATE t_chat_history_fts SET content = new.content WHERE rowid = old.id;
            END;
            """,
        ):
            cur.execute(sql)
        conn.commit()
        print("[FTS] triggers ensured")
    except Exception as e:  # pragma: no cover -- best-effort, mirrors QQ bot
        print(f"[FTS] init failed: {e}")
        conn.rollback()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Write / read
# ---------------------------------------------------------------------------

def save_chat_record(
    session_id: str,
    role: str,
    content: str = "",
    thought: str = "",
    action_name: str = "",
    action_input: str = "",
    function_output: str = "",
    request_id: str = "",
    timestamp: Optional[datetime] = None,
    is_summary: int = 0,
) -> int:
    ts = _fmt_ts(timestamp) if timestamp else _now_str()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO t_chat_history
                (group_id, timestamp, role, content, thought,
                 action_name, action_input, function_output, request_id, is_summary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id, ts, role, content, thought,
                action_name, action_input, function_output, request_id, is_summary,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def load_recent_history(
    session_id: str, limit: int = 20
) -> Tuple[List[Dict], str, datetime]:
    """Most recent ``limit`` non-summary messages + latest summary + last ts."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        rows = cur.execute(
            """
            SELECT role, content, timestamp FROM t_chat_history
            WHERE group_id = ? AND is_summary = 0
            ORDER BY timestamp DESC LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        rows = list(reversed(rows))
        history = [
            {"role": r["role"], "content": r["content"], "_timestamp": _parse_ts(r["timestamp"])}
            for r in rows
        ]

        summary_row = cur.execute(
            """
            SELECT content FROM t_chat_history
            WHERE group_id = ? AND is_summary = 1
            ORDER BY timestamp DESC LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        summary = summary_row["content"] if summary_row else ""

        last_row = cur.execute(
            "SELECT timestamp FROM t_chat_history WHERE group_id = ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        last_ts = _parse_ts(last_row["timestamp"]) if last_row else datetime.now()

        return history, summary, last_ts
    finally:
        conn.close()


def delete_session(session_id: str) -> None:
    """Permanently delete all rows and FTS entries for a session."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM t_chat_history_fts WHERE rowid IN "
            "(SELECT id FROM t_chat_history WHERE group_id = ?)",
            (session_id,),
        )
        cur.execute("DELETE FROM t_chat_history WHERE group_id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()


def list_sessions_by_prefix(prefix: str) -> list[dict]:
    """Return all distinct session_ids starting with ``prefix``, with
    metadata for a session list sidebar (first-message preview, timestamp)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        rows = cur.execute(
            """
            SELECT group_id, MIN(timestamp) as created, MAX(timestamp) as updated
            FROM t_chat_history
            WHERE group_id LIKE ?
            GROUP BY group_id
            ORDER BY updated DESC
            """,
            (prefix + "%",),
        ).fetchall()
        result = []
        for r in rows:
            sid = r["group_id"]
            first = cur.execute(
                "SELECT content FROM t_chat_history WHERE group_id=? "
                "ORDER BY timestamp ASC LIMIT 1",
                (sid,),
            ).fetchone()
            preview = (first["content"] or "")[:60] if first else ""
            result.append({
                "session_id": sid,
                "created": r["created"] or "",
                "updated": r["updated"] or "",
                "preview": preview,
            })
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# recall_memory (explicit session_id; ported from the QQ bot, raw SQL)
# ---------------------------------------------------------------------------

def recall_memory(
    session_id: str,
    time_range: str = "",
    keywords: str = "",
    limit: int = 5,
    context_lines: int = 1,
) -> str:
    """Recall historical messages by time + keyword, with surrounding context."""
    try:
        limit = int(limit) if limit is not None else 5
    except (ValueError, TypeError):
        limit = 5
    try:
        context_lines = int(context_lines) if context_lines is not None else 1
    except (ValueError, TypeError):
        context_lines = 1

    if not session_id:
        return "无法获取当前会话ID，请稍后再试。"

    MAX_SPAN_DAYS = 90
    MAX_LIMIT = 10
    MAX_CONTEXT = 5
    MAX_TOTAL_MSGS = 30

    limit = min(limit, MAX_LIMIT)
    context_lines = min(context_lines, MAX_CONTEXT)

    conn = get_connection()
    try:
        cur = conn.cursor()

        # --- 1. time range ---
        start_dt, end_dt = None, None
        if time_range:
            start_dt, end_dt = parse_natural_time(time_range)
            if start_dt is None and end_dt is None:
                start_dt, end_dt = parse_explicit_time(time_range)
            if start_dt is None and end_dt is None:
                return f"时间格式无法识别：'{time_range}'。请使用自然语言或具体时间格式。"
            if start_dt is not None and end_dt is None:
                end_dt = datetime.now()
            if end_dt is not None and start_dt is None:
                start_dt = end_dt - timedelta(days=7)
            if start_dt > end_dt:
                return "开始时间不能晚于结束时间。"
            if (end_dt - start_dt).days > MAX_SPAN_DAYS:
                return f"时间跨度不能超过 {MAX_SPAN_DAYS} 天。"

        def _time_clause(params: list) -> str:
            clause = ""
            if start_dt:
                clause += " AND timestamp >= ?"
                params.append(_fmt_ts(start_dt))
            if end_dt:
                clause += " AND timestamp <= ?"
                params.append(_fmt_ts(end_dt))
            return clause

        anchor_ids: List[int] = []

        # --- 2. keyword handling ---
        if keywords:
            advanced_patterns = [r'\bAND\b', r'\bOR\b', r'\bNOT\b', r'"', r'\*', r'\bNEAR\b']
            is_advanced = any(re.search(p, keywords, re.IGNORECASE) for p in advanced_patterns)

            def _fts_match_ids(fts_query: str) -> List[int]:
                return [
                    row[0]
                    for row in cur.execute(
                        "SELECT rowid FROM t_chat_history_fts WHERE content MATCH ?",
                        (fts_query,),
                    ).fetchall()
                ]

            def _filter_anchor(match_ids: List[int], remaining: int) -> List[int]:
                if not match_ids:
                    return []
                placeholders = ",".join("?" for _ in match_ids)
                params: list = [session_id]
                clause = _time_clause(params)
                params.extend(match_ids)
                sql = (
                    f"SELECT id FROM t_chat_history "
                    f"WHERE group_id = ?{clause} AND id IN ({placeholders}) "
                    f"ORDER BY timestamp DESC LIMIT ?"
                )
                params.append(remaining)
                return [r[0] for r in cur.execute(sql, params).fetchall()]

            if is_advanced:
                match_ids = _fts_match_ids(keywords)
                if not match_ids:
                    return "未找到匹配关键词的历史记录。"
                anchor_ids = _filter_anchor(match_ids, limit)
            else:
                kw_list = keywords.strip().split()
                if kw_list:
                    collected: List[int] = []
                    seen = set()
                    for n in range(len(kw_list), 0, -1):
                        if len(collected) >= limit:
                            break
                        fts_query = " ".join(kw_list[:n])
                        match_ids = _fts_match_ids(fts_query)
                        if not match_ids:
                            continue
                        for rid in _filter_anchor(match_ids, limit - len(collected)):
                            if rid not in seen:
                                seen.add(rid)
                                collected.append(rid)
                    anchor_ids = collected
                    if not anchor_ids:
                        return "未找到匹配关键词的历史记录。"
        else:
            params = [session_id]
            clause = _time_clause(params)
            params.append(limit)
            anchor_ids = [
                r[0]
                for r in cur.execute(
                    f"SELECT id FROM t_chat_history WHERE group_id = ?{clause} "
                    f"ORDER BY timestamp DESC LIMIT ?",
                    params,
                ).fetchall()
            ]

        if not anchor_ids:
            return "未找到相关历史记录。"

        # --- 3. context ids around each anchor ---
        ordered = cur.execute(
            "SELECT id FROM t_chat_history WHERE group_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        ordered_ids = [r[0] for r in ordered]
        pos = {rid: i for i, rid in enumerate(ordered_ids)}

        context_ids = set()
        for aid in anchor_ids:
            idx = pos.get(aid)
            if idx is None:
                continue
            lo = max(0, idx - context_lines)
            hi = min(len(ordered_ids), idx + context_lines + 1)
            context_ids.update(ordered_ids[lo:hi])
        all_ids = context_ids.union(anchor_ids)
        if not all_ids:
            return "未找到相关历史记录。"

        # --- 4. fetch + format ---
        placeholders = ",".join("?" for _ in all_ids)
        records = cur.execute(
            f"SELECT role, content, timestamp FROM t_chat_history "
            f"WHERE id IN ({placeholders}) ORDER BY timestamp",
            tuple(all_ids),
        ).fetchall()
        if len(records) > MAX_TOTAL_MSGS:
            records = records[-MAX_TOTAL_MSGS:]

        role_name = {"user": "用户", "assistant": "爱丽丝", "function": "系统"}
        lines = []
        for rec in records:
            time_str = _parse_ts(rec["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
            name = role_name.get(rec["role"], rec["role"])
            content = rec["content"] or ""
            preview = content[:200] + ("..." if len(content) > 200 else "")
            lines.append(f"[{time_str}] {name}: {preview}")
        return "\n".join(lines)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Time parsing (ported verbatim from the QQ bot)
# ---------------------------------------------------------------------------

def parse_natural_time(text: str) -> Tuple[Optional[datetime], Optional[datetime]]:
    now = datetime.now()
    text = text.strip().lower()
    match = re.search(r'最近\s*(\d+)\s*(小时|小时前|天|天前|周|周前)', text)
    if match:
        num = int(match.group(1))
        unit = match.group(2)
        if '小时' in unit:
            return now - timedelta(hours=num), now
        elif '天' in unit:
            return now - timedelta(days=num), now
        elif '周' in unit:
            return now - timedelta(weeks=num), now
    if '今天' in text:
        return now.replace(hour=0, minute=0, second=0, microsecond=0), now
    if '昨天' in text:
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1) - timedelta(seconds=1)
    if '前天' in text:
        start = (now - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1) - timedelta(seconds=1)
    if '本周' in text:
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    if '上周' in text:
        start = (now - timedelta(days=now.weekday() + 7)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=7) - timedelta(seconds=1)
    return None, None


def parse_explicit_time(text: str) -> Tuple[Optional[datetime], Optional[datetime]]:
    if ' to ' in text.lower():
        parts = text.lower().split(' to ')
        if len(parts) == 2:
            start = parse_single_datetime(parts[0].strip())
            end = parse_single_datetime(parts[1].strip())
            if start and end:
                return start, end
    dt = parse_single_datetime(text)
    if dt:
        return dt, None
    return None, None


def parse_single_datetime(dt_str: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(dt_str.strip(), fmt)
        except ValueError:
            continue
    return None
