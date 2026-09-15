from fastapi import APIRouter, HTTPException

from src.api.schemas import IndexRequest, IndexResponse, QueryRequest, QueryResponse
from src.services.exceptions import RepoIndexingError, RepoNotIndexedError
from src.services.qa_service import ask_question, index_repository

router = APIRouter()


@router.post("/index", response_model=IndexResponse)
def index_repo(request: IndexRequest) -> IndexResponse:
    try:
        result = index_repository(str(request.repo_url), request.force_reindex)
    except RepoIndexingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Embedding provider error: {exc}") from exc

    return IndexResponse(
        repo_url=result.repo_url, reused_existing=result.reused_existing, num_chunks=result.num_chunks
    )


@router.post("/query", response_model=QueryResponse)
def query_repo(request: QueryRequest) -> QueryResponse:
    try:
        result = ask_question(str(request.repo_url), request.question)
    except RepoNotIndexedError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM or embedding provider error: {exc}") from exc

    return QueryResponse(answer=result.answer, sources=result.sources)
