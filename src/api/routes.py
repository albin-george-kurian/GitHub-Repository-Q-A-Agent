import logging

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


@router.post("/query", response_model=QueryResponse)
def query_repo(
    request: QueryRequest, background: BackgroundTasks, user_id: str = Depends(get_user_id)
) -> QueryResponse:
    try:
        turn = chat_service.chat(user_id, str(request.repo_url), request.question, request.chat_id)
    except InvalidRepoUrlError as exc:
        raise _error(400, exc) from exc
    except RepoNotIndexedError as exc:
        raise _error(404, exc, "repo_not_indexed") from exc
    except ChatNotFoundError as exc:
        raise _error(404, exc, "chat_not_found") from exc
    except ConfigurationError as exc:
        raise _error(503, exc, "not_configured") from exc
    except Exception as exc:
        if message := rejected_key_message(exc):
            raise HTTPException(status_code=503, detail=message, headers={"X-Error-Code": "not_configured"}) from exc
        logger.exception("Query failed for %s", request.repo_url)
        raise HTTPException(status_code=502, detail=f"LLM or embedding provider error: {exc}") from exc

    if turn.memory_saved is None:
        background.add_task(chat_service.after_turn, user_id, turn.chat_id, request.question)

    return QueryResponse(
        answer=turn.answer,
        sources=turn.sources,
        chat_id=turn.chat_id,
        standalone_question=turn.standalone_question,
        memory_saved=turn.memory_saved,
    )


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
