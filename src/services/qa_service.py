from dataclasses import dataclass

from git import GitCommandError

from src.config import settings
from src.embeddings.embedding_provider import get_embeddings
from src.ingestion.document_loader import load_repo_documents
from src.ingestion.repo_loader import clone_repo, cleanup_repo
from src.processing.splitter import split_documents
from src.rag.qa_chain import answer_question, build_qa_chain
from src.services.exceptions import RepoIndexingError, RepoNotIndexedError
from src.vectorstore.faiss_store import build_and_save_index, index_exists, load_index


@dataclass
class IndexResult:
    repo_url: str
    reused_existing: bool
    num_chunks: int | None  # None when an existing index was reused (chunk count not recomputed)


@dataclass
class AnswerResult:
    answer: str
    sources: list[str]


def index_repository(repo_url: str, force_reindex: bool = False) -> IndexResult:
    """Clone, chunk, embed, and persist a FAISS index for a repo, or reuse an existing one."""
    if index_exists(repo_url) and not force_reindex:
        return IndexResult(repo_url=repo_url, reused_existing=True, num_chunks=None)

    try:
        local_path = clone_repo(repo_url)
    except GitCommandError as exc:
        raise RepoIndexingError(f"Failed to clone repository: {repo_url}") from exc

    try:
        documents = load_repo_documents(local_path, settings.max_file_size_bytes)
        if not documents:
            raise RepoIndexingError(f"No indexable source/doc files found in repository: {repo_url}")

        chunks = split_documents(documents, settings.chunk_size, settings.chunk_overlap)
        embeddings = get_embeddings()
        build_and_save_index(repo_url, chunks, embeddings)
        return IndexResult(repo_url=repo_url, reused_existing=False, num_chunks=len(chunks))
    finally:
        cleanup_repo(local_path)


def ask_question(repo_url: str, question: str) -> AnswerResult:
    """Answer a question about a previously indexed repo."""
    if not index_exists(repo_url):
        raise RepoNotIndexedError(f"Repository has not been indexed yet: {repo_url}")

    embeddings = get_embeddings()
    vector_store = load_index(repo_url, embeddings)
    chain = build_qa_chain(vector_store, settings.retriever_top_k)
    result = answer_question(chain, question)
    return AnswerResult(answer=result["answer"], sources=result["sources"])
