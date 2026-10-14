"""Conversational Q&A with memory.

Memory layers, mirroring how an assistant like Claude keeps context:
  1. Recent turns of this chat, sent verbatim (short-term / context window).
  2. A running summary of older turns (compaction), updated after the response.
  3. Chats persisted in SQLite, so they survive reloads and can be resumed.
  4. A repo overview written at index time (project brief).
  5. Long-term memories about the user, explicit ("remember that …") or learned.
  6. Recall of related Q&A from the user's other chats about the same repo.
"""

import logging
import re
from collections.abc import Generator
from dataclasses import dataclass
from typing import ClassVar, Literal

from src.config import settings
from src.embeddings.embedding_provider import get_embeddings
from src.ingestion.repo_url import normalize_repo_url
from src.llm.groq_client import get_llm
from src.memory import llm_tasks, store
from src.rag.qa_chain import sources_of, stream_answer
from src.services.exceptions import ChatNotFoundError, RepoNotIndexedError
from src.vectorstore.faiss_store import index_exists, load_index, load_overview

logger = logging.getLogger(__name__)

# "remember that I prefer TypeScript" / "please remember: keep answers short" — but not questions.
_REMEMBER = re.compile(r"^\s*(?:please\s+)?remember(?:\s+that)?\s*[:,-]?\s+(?P<fact>[^?]+?)[.!]?\s*$", re.I | re.S)
_TITLE_MAX = 60


# ---------- Events of a streamed turn, in order. `event` is the name used on the wire (SSE). ----------


@dataclass
class Started:
    chat_id: str
    event: ClassVar[str] = "start"


@dataclass
class Status:
    stage: Literal["rewriting", "searching"]
    event: ClassVar[str] = "status"


@dataclass
class Retrieved:
    """The code search is done; the answer is about to be written from these files."""

    sources: list[str]
    standalone_question: str | None
    event: ClassVar[str] = "sources"


@dataclass
class Delta:
    text: str
    event: ClassVar[str] = "delta"


@dataclass
class ChatTurn:
    """The finished turn, always the last event."""

    chat_id: str
    answer: str
    sources: list[str]
    standalone_question: str | None  # set when a follow-up was rewritten before searching
    memory_saved: str | None  # set when the message was an explicit "remember …"
    event: ClassVar[str] = "done"


ChatEvent = Started | Status | Retrieved | Delta | ChatTurn


def _title_for(question: str) -> str:
    title = " ".join(question.split())
    return title if len(title) <= _TITLE_MAX else title[: _TITLE_MAX - 1].rstrip() + "…"


def _resolve_chat(user_id: str, repo_url: str, chat_id: str | None, question: str) -> store.Chat:
    if chat_id is None:
        return store.create_chat(user_id, repo_url, _title_for(question))
    chat = store.get_chat(user_id, chat_id)
    if chat is None or chat.repo_url != repo_url:
        raise ChatNotFoundError(f"Chat not found: {chat_id}")
    return chat


def start_chat(user_id: str, repo_url: str, question: str, chat_id: str | None = None) -> Generator[ChatEvent]:
    """Check the request, then return the turn as a stream of events ending with the ChatTurn.

    Request problems (repo not indexed, unknown chat, missing LLM key) are raised here, before
    anything streams, so callers can still report them as ordinary errors. Closing the generator
    early stops the answer and saves the text written so far."""
    repo_url = normalize_repo_url(repo_url)
    if not index_exists(repo_url):
        raise RepoNotIndexedError(f"Repository has not been indexed yet: {repo_url}")

    remember = _REMEMBER.match(question)
    if remember:
        return _just(_remember(user_id, repo_url, chat_id, question, remember.group("fact").strip()))

    get_llm()  # fail fast with a clear ConfigurationError before doing any work
    conversation = _resolve_chat(user_id, repo_url, chat_id, question)
    return _answer(user_id, repo_url, question, conversation)


def chat(user_id: str, repo_url: str, question: str, chat_id: str | None = None) -> ChatTurn:
    """The whole turn at once, for callers that don't stream."""
    *_, turn = start_chat(user_id, repo_url, question, chat_id)
    return turn


def _just(turn: ChatTurn) -> Generator[ChatEvent]:
    yield turn


def _answer(user_id: str, repo_url: str, question: str, conversation: store.Chat) -> Generator[ChatEvent]:
    yield Started(conversation.id)

    # Short-term memory: turns not yet folded into the summary. Compaction normally keeps this short;
    # the slice is a hard cap in case background summarization keeps failing.
    history = store.get_messages(conversation.id, after_id=conversation.summarized_upto)
    history = history[-(settings.summarize_after_messages + 2) :]
    standalone = question
    if history or conversation.summary:
        yield Status("rewriting")
        try:
            standalone = llm_tasks.condense_question(
                question, history[-settings.history_recent_messages * 2 :], conversation.summary
            )
        except Exception:
            logger.exception("Question rewrite failed; searching with the original question")

    # Embed once; reuse the vector for code retrieval, past-Q&A recall and storage.
    yield Status("searching")
    embeddings = get_embeddings()
    query_vector = embeddings.embed_query(standalone)
    docs = load_index(repo_url, embeddings).similarity_search_by_vector(query_vector, k=settings.retriever_top_k)
    related = store.related_qa(
        user_id,
        repo_url,
        exclude_chat_id=conversation.id,
        query_vector=query_vector,
        embedding_model=settings.embedding_model_id,
        top_k=settings.related_qa_top_k,
        min_similarity=settings.related_qa_min_similarity,
    )
    sources = sources_of(docs)
    rewritten = standalone if standalone != question else None
    yield Retrieved(sources, rewritten)

    def save(answer: str) -> None:
        store.add_message(conversation.id, "user", question)
        store.add_message(
            conversation.id,
            "assistant",
            answer,
            sources=sources,
            standalone_question=standalone,
            embedding=query_vector,
            embedding_model=settings.embedding_model_id,
        )

    pieces: list[str] = []
    try:
        for piece in stream_answer(
            question,
            docs,
            overview=load_overview(repo_url),
            memories=[m.content for m in store.list_memories(user_id)],
            related=related,
            summary=conversation.summary,
            history=history,
            history_max_chars=settings.history_message_max_chars,
        ):
            pieces.append(piece)
            yield Delta(piece)
    except GeneratorExit:
        # The client stopped the answer (or disconnected): keep what they already saw, so the saved
        # chat matches their screen and follow-ups have the context.
        if "".join(pieces).strip():
            try:
                save("".join(pieces))
            except Exception:
                logger.exception("Saving the stopped answer in chat %s failed", conversation.id)
        raise

    # Otherwise persist only after a successful answer, so failed calls don't leave half a turn behind.
    answer = "".join(pieces)
    save(answer)
    yield ChatTurn(conversation.id, answer, sources, rewritten, None)


def _remember(user_id: str, repo_url: str, chat_id: str | None, question: str, fact: str) -> ChatTurn:
    conversation = _resolve_chat(user_id, repo_url, chat_id, question)
    saved = store.add_memory(user_id, fact, "explicit", settings.max_memories_per_user)
    reply = f"Got it, I'll remember that: *{fact}*" if saved else f"I already remember that: *{fact}*"
    store.add_message(conversation.id, "user", question)
    store.add_message(conversation.id, "assistant", reply)
    return ChatTurn(conversation.id, reply, [], None, fact)


def after_turn(user_id: str, chat_id: str, user_message: str) -> None:
    """Housekeeping that shouldn't delay the response: compaction and learning user preferences.
    Runs in the background; failures are logged and never surface to the user."""
    try:
        _compact(user_id, chat_id)
    except Exception:
        logger.exception("Summarizing chat %s failed", chat_id)

    if settings.auto_memory and not _REMEMBER.match(user_message):
        try:
            _learn_preferences(user_id, user_message)
        except Exception:
            logger.exception("Memory extraction failed for user %s", user_id)


def _compact(user_id: str, chat_id: str) -> None:
    conversation = store.get_chat(user_id, chat_id)
    if conversation is None:
        return
    pending = store.get_messages(chat_id, after_id=conversation.summarized_upto)
    if len(pending) <= settings.summarize_after_messages:
        return
    to_fold = pending[: -settings.history_recent_messages]
    summary = llm_tasks.summarize_conversation(conversation.summary, to_fold)
    store.update_summary(chat_id, summary, to_fold[-1].id)


def _learn_preferences(user_id: str, user_message: str) -> None:
    if not llm_tasks.might_contain_preferences(user_message):
        return
    existing = [m.content for m in store.list_memories(user_id)]
    for fact in llm_tasks.extract_memories(user_message, existing):
        store.add_memory(user_id, fact, "auto", settings.max_memories_per_user)
