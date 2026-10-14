"""Persistence for chats, messages and long-term user memories."""

import json
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from src.memory.db import connect


@dataclass
class Chat:
    id: str
    user_id: str
    repo_url: str
    title: str
    summary: str
    summarized_upto: int
    created_at: float
    updated_at: float


@dataclass
class Message:
    id: int
    chat_id: str
    role: str
    content: str
    sources: list[str]
    standalone_question: str | None
    created_at: float


@dataclass
class Memory:
    id: str
    content: str
    source: str  # "explicit" (user asked) or "auto" (learned from conversation)
    created_at: float


@dataclass
class RelatedQA:
    question: str
    answer: str
    similarity: float


# ---------- Chats ----------


def _chat(row) -> Chat:
    return Chat(**{k: row[k] for k in row.keys()})


def create_chat(user_id: str, repo_url: str, title: str) -> Chat:
    now = time.time()
    chat = Chat(uuid.uuid4().hex, user_id, repo_url, title, "", 0, now, now)
    with connect() as conn:
        conn.execute(
            "INSERT INTO chats (id, user_id, repo_url, title, summary, summarized_upto, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (chat.id, user_id, repo_url, title, "", 0, now, now),
        )
    return chat


def get_chat(user_id: str, chat_id: str) -> Chat | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM chats WHERE id = ? AND user_id = ?", (chat_id, user_id)).fetchone()
    return _chat(row) if row else None


def list_chats(user_id: str, repo_url: str | None = None, limit: int = 50) -> list[Chat]:
    """Chats with at least one message; one whose first answer failed or was stopped early stays hidden."""
    has_messages = "EXISTS (SELECT 1 FROM messages m WHERE m.chat_id = chats.id)"
    with connect() as conn:
        if repo_url:
            rows = conn.execute(
                f"SELECT * FROM chats WHERE user_id = ? AND repo_url = ? AND {has_messages}"
                " ORDER BY updated_at DESC LIMIT ?",
                (user_id, repo_url, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT * FROM chats WHERE user_id = ? AND {has_messages} ORDER BY updated_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
    return [_chat(r) for r in rows]


def delete_chat(user_id: str, chat_id: str) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM chats WHERE id = ? AND user_id = ?", (chat_id, user_id))
    return cur.rowcount > 0


def update_summary(chat_id: str, summary: str, summarized_upto: int) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE chats SET summary = ?, summarized_upto = ? WHERE id = ? AND summarized_upto < ?",
            (summary, summarized_upto, chat_id, summarized_upto),
        )


# ---------- Messages ----------


def _message(row) -> Message:
    return Message(
        id=row["id"],
        chat_id=row["chat_id"],
        role=row["role"],
        content=row["content"],
        sources=json.loads(row["sources"]),
        standalone_question=row["standalone_question"],
        created_at=row["created_at"],
    )


def add_message(
    chat_id: str,
    role: str,
    content: str,
    sources: Sequence[str] = (),
    standalone_question: str | None = None,
    embedding: Sequence[float] | None = None,
    embedding_model: str | None = None,
) -> Message:
    now = time.time()
    blob = np.asarray(embedding, dtype=np.float32).tobytes() if embedding is not None else None
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO messages (chat_id, role, content, sources, standalone_question, embedding,"
            " embedding_model, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (chat_id, role, content, json.dumps(list(sources)), standalone_question, blob, embedding_model, now),
        )
        conn.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id))
    return Message(cur.lastrowid, chat_id, role, content, list(sources), standalone_question, now)


def get_messages(chat_id: str, after_id: int = 0) -> list[Message]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE chat_id = ? AND id > ? ORDER BY id", (chat_id, after_id)
        ).fetchall()
    return [_message(r) for r in rows]


def related_qa(
    user_id: str,
    repo_url: str,
    exclude_chat_id: str,
    query_vector: Sequence[float],
    embedding_model: str,
    top_k: int,
    min_similarity: float,
    scan_limit: int = 500,
) -> list[RelatedQA]:
    """Past Q&A from the user's *other* chats about this repo, most similar to the query first."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT m.standalone_question, m.content, m.embedding FROM messages m"
            " JOIN chats c ON c.id = m.chat_id"
            " WHERE c.user_id = ? AND c.repo_url = ? AND m.chat_id != ? AND m.role = 'assistant'"
            " AND m.embedding IS NOT NULL AND m.embedding_model = ?"
            " ORDER BY m.id DESC LIMIT ?",
            (user_id, repo_url, exclude_chat_id, embedding_model, scan_limit),
        ).fetchall()
    if not rows:
        return []

    query = np.asarray(query_vector, dtype=np.float32)
    matrix = np.stack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
    if matrix.shape[1] != query.shape[0]:
        return []
    denom = np.linalg.norm(matrix, axis=1) * (np.linalg.norm(query) or 1.0)
    scores = matrix @ query / np.where(denom == 0, 1.0, denom)

    ranked = sorted(zip(rows, scores), key=lambda pair: pair[1], reverse=True)
    return [
        RelatedQA(row["standalone_question"] or "", row["content"], float(score))
        for row, score in ranked[:top_k]
        if score >= min_similarity
    ]


# ---------- Long-term memories ----------


def _memory(row) -> Memory:
    return Memory(row["id"], row["content"], row["source"], row["created_at"])


def list_memories(user_id: str) -> list[Memory]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM memories WHERE user_id = ? ORDER BY created_at", (user_id,)).fetchall()
    return [_memory(r) for r in rows]


def _normalize(text: str) -> str:
    return " ".join(text.lower().strip().rstrip(".!").split())


def add_memory(user_id: str, content: str, source: str, max_per_user: int) -> Memory | None:
    """Store a memory unless an identical one exists. Oldest auto-learned memories are
    dropped first when the user is over the cap. Returns None for duplicates."""
    content = content.strip()
    existing = list_memories(user_id)
    if any(_normalize(m.content) == _normalize(content) for m in existing):
        return None

    memory = Memory(uuid.uuid4().hex, content, source, time.time())
    with connect() as conn:
        conn.execute(
            "INSERT INTO memories (id, user_id, content, source, created_at) VALUES (?, ?, ?, ?, ?)",
            (memory.id, user_id, memory.content, source, memory.created_at),
        )
        overflow = len(existing) + 1 - max_per_user
        if overflow > 0:
            conn.execute(
                "DELETE FROM memories WHERE id IN (SELECT id FROM memories WHERE user_id = ? AND id != ?"
                " ORDER BY source = 'explicit', created_at LIMIT ?)",
                (user_id, memory.id, overflow),
            )
    return memory


def delete_memory(user_id: str, memory_id: str) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM memories WHERE id = ? AND user_id = ?", (memory_id, user_id))
    return cur.rowcount > 0


def clear_memories(user_id: str) -> int:
    with connect() as conn:
        cur = conn.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))
    return cur.rowcount
