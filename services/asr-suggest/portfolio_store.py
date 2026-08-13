import os
import sqlite3
import threading
from datetime import datetime, timezone

import config

MAX_NAME_LEN = 100
MAX_CONTENT_LEN = 30000  # keep in sync with the client-side PDF truncation guard (F-2)

_lock = threading.Lock()
# WI-A4 (audit v0.3.2): a dedicated init lock, separate from _lock. Two threads could both
# pass `if _conn is None` before either finished sqlite3.connect() - one connection leaked,
# the other silently became the module's _conn, and any in-flight query on the leaked
# connection referenced a now-orphaned handle. Double-checked locking closes that window.
_init_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    """One shared connection for the process lifetime - check_same_thread=False because
    endpoints are dispatched via asyncio.to_thread (a different thread per call), guarded
    by _lock since sqlite3 connections are not safe for concurrent use across threads."""
    global _conn
    if _conn is None:  # fast path - no lock once initialized
        with _init_lock:  # serialize the one-time init
            if _conn is None:  # double-checked: another thread may have won the race
                os.makedirs(os.path.dirname(config.PORTFOLIO_DB_PATH), exist_ok=True)
                _conn = sqlite3.connect(config.PORTFOLIO_DB_PATH, check_same_thread=False)
                # WI-B3: WAL lets readers and the single writer proceed without blocking
                # each other - the default rollback-journal mode serializes all access.
                _conn.execute("PRAGMA journal_mode=WAL")
                _conn.execute("PRAGMA synchronous=NORMAL")
                _conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS portfolios (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        content TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                _conn.commit()
    return _conn


def validate(name: str, content: str) -> str | None:
    """Pure guard, no I/O - returns an error reason string, or None if valid."""
    if not name.strip():
        return "empty-name"
    if len(name) > MAX_NAME_LEN:
        return "name-too-long"
    if not content.strip():
        return "empty-content"
    if len(content) > MAX_CONTENT_LEN:
        return "content-too-long"
    return None


def list_portfolios() -> list[dict]:
    """No `content` in the list response - WI-13: keep the list endpoint cheap."""
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            "SELECT id, name, created_at, length(content) FROM portfolios ORDER BY created_at DESC"
        ).fetchall()
    return [{"id": r[0], "name": r[1], "created_at": r[2], "size": r[3]} for r in rows]


def get_portfolio(portfolio_id: int) -> dict | None:
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            "SELECT id, name, content, created_at FROM portfolios WHERE id = ?", (portfolio_id,)
        ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "name": row[1], "content": row[2], "created_at": row[3]}


def upsert_portfolio(name: str, content: str) -> dict:
    """Duplicate name -> replace content in place (natural "update CV" flow, WI-13). Explicit
    select-then-update/insert under _lock rather than an ON CONFLICT upsert, since the schema
    above has no UNIQUE constraint on name and a single local writer has no real race to guard."""
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        existing = conn.execute("SELECT id FROM portfolios WHERE name = ?", (name,)).fetchone()
        if existing:
            portfolio_id = existing[0]
            conn.execute(
                "UPDATE portfolios SET content = ?, created_at = ? WHERE id = ?",
                (content, now, portfolio_id),
            )
        else:
            cur = conn.execute(
                "INSERT INTO portfolios (name, content, created_at) VALUES (?, ?, ?)",
                (name, content, now),
            )
            portfolio_id = cur.lastrowid
        conn.commit()
    return {"id": portfolio_id, "name": name, "created_at": now}


def delete_portfolio(portfolio_id: int) -> bool:
    conn = _get_conn()
    with _lock:
        cur = conn.execute("DELETE FROM portfolios WHERE id = ?", (portfolio_id,))
        conn.commit()
    return cur.rowcount > 0


def _reset_connection_for_tests() -> None:
    """Test-only: the module-level connection is a process-lifetime singleton, which would
    otherwise keep pointing at a previous test's PORTFOLIO_DB_PATH. Call after monkeypatching
    config.PORTFOLIO_DB_PATH so the next _get_conn() reopens at the new path."""
    global _conn
    if _conn is not None:
        _conn.close()
    _conn = None
