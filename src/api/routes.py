import logging
from collections.abc import Generator
from contextlib import closing
from dataclasses import asdict, dataclass

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response

from src.api.deps import get_user_id
from src.api.schemas import (
    ChatDetail,
    ChatSummary,
    IndexJobOut,
    IndexRequest,
    MemoryCreate,
    MemoryOut,
    MessageOut,
    QueryRequest,
    QueryResponse,
)
from src.api.streaming import EventStream, sse_event
from src.config import settings
from src.ingestion.repo_url import normalize_repo_url
from src.memory import store
from src.services import chat_service, index_jobs
from src.services.exceptions import (
    ChatNotFoundError,
    ConfigurationError,
    IndexBusyError,
    InvalidRepoUrlError,
    RepoNotIndexedError,
    rejected_key_message,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _error(status: int, exc: Exception, code: str | None = None) -> HTTPException:
    # X-Error-Code lets clients tell apart errors that share a status (e.g. the two 404s).
    return HTTPException(status_code=status, detail=str(exc), headers={"X-Error-Code": code} if code else None)


@router.post("/index", response_model=IndexJobOut, status_code=202)
def index_repo(request: IndexRequest) -> IndexJobOut:
    """Start indexing in the background (or join the run already in progress for this repo).
    Poll GET /index/jobs/{id} for live progress."""
    try:
        job = index_jobs.start(str(request.repo_url), request.force_reindex)
    except InvalidRepoUrlError as exc:
        raise _error(400, exc) from exc
    except IndexBusyError as exc:
        raise _error(429, exc, "index_busy") from exc
    return IndexJobOut(**index_jobs.snapshot(job))


@router.get("/index/jobs/{job_id}", response_model=IndexJobOut)
def get_index_job(job_id: str) -> IndexJobOut:
    job = index_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Indexing job not found", headers={"X-Error-Code": "job_not_found"})
    return IndexJobOut(**index_jobs.snapshot(job))


@router.post("/index/jobs/{job_id}/cancel", response_model=IndexJobOut, status_code=202)
def cancel_index_job(job_id: str) -> IndexJobOut:
    job = index_jobs.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Indexing job not found", headers={"X-Error-Code": "job_not_found"})
    return IndexJobOut(**index_jobs.snapshot(job))


def _query_error(exc: Exception, repo_url: str) -> tuple[int, str, str | None]:
    """Status, message and error code for a failed question."""
    if isinstance(exc, InvalidRepoUrlError):
        return 400, str(exc), None
    if isinstance(exc, RepoNotIndexedError):
        return 404, str(exc), "repo_not_indexed"
    if isinstance(exc, ChatNotFoundError):
        return 404, str(exc), "chat_not_found"
    if isinstance(exc, ConfigurationError):
        return 503, str(exc), "not_configured"
    if message := rejected_key_message(exc):
        return 503, message, "not_configured"
    logger.exception("Query failed for %s", repo_url)
    return 502, f"LLM or embedding provider error: {exc}", None


def _query_http_error(exc: Exception, repo_url: str) -> HTTPException:
    status, detail, code = _query_error(exc, repo_url)
    return HTTPException(status_code=status, detail=detail, headers={"X-Error-Code": code} if code else None)


@router.post("/query", response_model=QueryResponse)
def query_repo(
    request: QueryRequest, background: BackgroundTasks, user_id: str = Depends(get_user_id)
) -> QueryResponse:
    try:
        turn = chat_service.chat(user_id, str(request.repo_url), request.question, request.chat_id)
    except Exception as exc:
        raise _query_http_error(exc, str(request.repo_url)) from exc

    if turn.memory_saved is None:
        background.add_task(chat_service.after_turn, user_id, turn.chat_id, request.question)

    return QueryResponse(**asdict(turn))


@dataclass
class _StreamedTurn:
    user_id: str
    request: QueryRequest
    events: Generator[chat_service.ChatEvent]


def _start_streamed_turn(request: QueryRequest, user_id: str = Depends(get_user_id)) -> _StreamedTurn:
    # Runs before the stream opens, so request errors still get their HTTP status and X-Error-Code.
    try:
        events = chat_service.start_chat(user_id, str(request.repo_url), request.question, request.chat_id)
    except Exception as exc:
        raise _query_http_error(exc, str(request.repo_url)) from exc
    return _StreamedTurn(user_id, request, events)


@router.post("/query/stream", response_class=EventStream)
def query_repo_stream(background: BackgroundTasks, turn: _StreamedTurn = Depends(_start_streamed_turn)) -> EventStream:
    """Like POST /query, but streams the answer as Server-Sent Events:

    `start` {chat_id} → `status` {stage}… → `sources` {sources, standalone_question} → `delta` {text}… →
    `done` (same fields as /query). A failure after the stream has started arrives as `error`
    {status, detail, code}. Closing the connection stops the answer; the text so far is kept in the chat."""

    def events() -> Generator[bytes]:
        try:
            # When the response ends early (client gone), closing the turn saves the text written so far.
            with closing(turn.events) as turn_events:
                for event in turn_events:
                    yield sse_event(event.event, asdict(event))
                    if isinstance(event, chat_service.ChatTurn) and event.memory_saved is None:
                        background.add_task(chat_service.after_turn, turn.user_id, event.chat_id, turn.request.question)
        except Exception as exc:
            status, detail, code = _query_error(exc, str(turn.request.repo_url))
            yield sse_event("error", {"status": status, "detail": detail, "code": code})

    return EventStream(events(), background)


# ---------- Chats ----------


@router.get("/chats", response_model=list[ChatSummary])
def list_chats(repo_url: str | None = None, user_id: str = Depends(get_user_id)) -> list[ChatSummary]:
    try:
        repo = normalize_repo_url(repo_url) if repo_url else None
    except InvalidRepoUrlError as exc:
        raise _error(400, exc) from exc
    return [
        ChatSummary(id=c.id, repo_url=c.repo_url, title=c.title, updated_at=c.updated_at)
        for c in store.list_chats(user_id, repo)
    ]


@router.get("/chats/{chat_id}", response_model=ChatDetail)
def get_chat(chat_id: str, user_id: str = Depends(get_user_id)) -> ChatDetail:
    chat = store.get_chat(user_id, chat_id)
    if chat is None:
        raise _error(404, ChatNotFoundError(f"Chat not found: {chat_id}"), "chat_not_found")
    messages = [
        MessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            sources=m.sources,
            standalone_question=m.standalone_question,
            created_at=m.created_at,
        )
        for m in store.get_messages(chat.id)
    ]
    return ChatDetail(id=chat.id, repo_url=chat.repo_url, title=chat.title, updated_at=chat.updated_at, messages=messages)


@router.delete("/chats/{chat_id}", status_code=204)
def delete_chat(chat_id: str, user_id: str = Depends(get_user_id)) -> Response:
    if not store.delete_chat(user_id, chat_id):
        raise _error(404, ChatNotFoundError(f"Chat not found: {chat_id}"), "chat_not_found")
    return Response(status_code=204)


# ---------- Long-term memories ----------


def _memory_out(m: store.Memory) -> MemoryOut:
    return MemoryOut(id=m.id, content=m.content, source=m.source, created_at=m.created_at)


@router.get("/memories", response_model=list[MemoryOut])
def list_memories(user_id: str = Depends(get_user_id)) -> list[MemoryOut]:
    return [_memory_out(m) for m in store.list_memories(user_id)]


@router.post("/memories", response_model=MemoryOut, status_code=201)
def add_memory(body: MemoryCreate, user_id: str = Depends(get_user_id)) -> MemoryOut:
    memory = store.add_memory(user_id, body.content, "explicit", settings.max_memories_per_user)
    if memory is None:
        raise HTTPException(status_code=409, detail="That's already remembered")
    return _memory_out(memory)


@router.delete("/memories/{memory_id}", status_code=204)
def delete_memory(memory_id: str, user_id: str = Depends(get_user_id)) -> Response:
    if not store.delete_memory(user_id, memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    return Response(status_code=204)


@router.delete("/memories", status_code=204)
def clear_memories(user_id: str = Depends(get_user_id)) -> Response:
    store.clear_memories(user_id)
    return Response(status_code=204)
