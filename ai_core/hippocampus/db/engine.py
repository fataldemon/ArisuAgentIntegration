"""Dedicated SQLite engine for hippocampus.

This is intentionally independent of the QQ bot's SQLAlchemy ``dbengine``:
hippocampus owns its own raw-``sqlite3`` access layer over the *same*
shared database file (``db/tendou_arisu.db``). Two engines writing the
same file is fine because we enable WAL + a busy timeout; the two writers
also operate on disjoint ``group_id`` namespaces (hippocampus stores
``session_id`` values such as ``qq:12345`` which never collide with the
QQ bot's bare numeric group ids).

Resolution order for the DB location:
    1. ``HIPPOCAMPUS_DB_URL`` env (sqlite URL or plain path)
    2. ``DB_URL`` env (the value AI Core's config_manager auto-derives)
    3. auto-computed ``<project_root>/db/tendou_arisu.db``
"""

from __future__ import annotations

import os
import sqlite3
import threading

_lock = threading.Lock()
_db_path: str | None = None


def _strip_sqlite_url(value: str) -> str:
    """Accept either a plain filesystem path or a ``sqlite:///`` URL."""
    if not value:
        return value
    for prefix in ("sqlite:////", "sqlite:///", "sqlite://"):
        if value.startswith(prefix):
            return value[len(prefix):]
    return value


def _auto_db_path() -> str:
    # engine.py -> db -> hippocampus -> ai_core -> <project_root>
    here = os.path.abspath(__file__)
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(here)))
    )
    return os.path.join(project_root, "db", "tendou_arisu.db")


def resolve_db_path() -> str:
    global _db_path
    if _db_path is not None:
        return _db_path
    with _lock:
        if _db_path is not None:
            return _db_path
        raw = os.environ.get("HIPPOCAMPUS_DB_URL") or os.environ.get("DB_URL") or ""
        path = _strip_sqlite_url(raw) if raw else _auto_db_path()
        path = os.path.normpath(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _db_path = path
    return _db_path


def get_connection() -> sqlite3.Connection:
    """Return a fresh connection with WAL + busy timeout + row access by name."""
    conn = sqlite3.connect(resolve_db_path(), timeout=15.0)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=10000")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()
    return conn
