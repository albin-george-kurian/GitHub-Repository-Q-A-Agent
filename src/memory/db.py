import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from src.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    repo_url        TEXT NOT NULL,
    title           TEXT NOT NULL,
    summary         TEXT NOT NULL DEFAULT '',
    summarized_upto INTEGER NOT NULL DEFAULT 0,  -- id of the last message folded into summary
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chats_user_repo ON chats (user_id, repo_url, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id             TEXT NOT NULL REFERENCES chats (id) ON DELETE CASCADE,
    role                TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content             TEXT NOT NULL,
    sources             TEXT NOT NULL DEFAULT '[]',
    standalone_question TEXT,     -- assistant rows: the rewritten question that was searched
    embedding           BLOB,     -- assistant rows: float32 vector of standalone_question
    embedding_model     TEXT,
    created_at          REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages (chat_id, id);

CREATE TABLE IF NOT EXISTS memories (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    content    TEXT NOT NULL,
    source     TEXT NOT NULL CHECK (source IN ('explicit', 'auto')),
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_user ON memories (user_id, created_at);
"""

_init_lock = threading.Lock()
_initialized: set[str] = set()


def _ensure_schema(path: str) -> None:
    with _init_lock:
        if path in _initialized:
            return
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        conn = sqlite3.connect(path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)
        finally:
            conn.close()
        _initialized.add(path)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Short-lived connection per unit of work; commits on success, rolls back on error."""
    path = settings.memory_db_path
    _ensure_schema(path)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()
