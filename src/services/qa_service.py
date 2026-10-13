import posixpath
from collections import defaultdict
from dataclasses import dataclass
from threading import Lock

from git import GitCommandError

from src.config import settings
from src.embeddings.embedding_provider import get_embeddings
from src.ingestion.document_loader import load_repo_documents
from src.ingestion.file_filter import language_breakdown
from src.ingestion.repo_loader import clone_repo, cleanup_repo
from src.ingestion.repo_url import normalize_repo_url
from src.processing.splitter import split_documents
from src.rag.overview import build_overview
from src.rag.qa_chain import generate_answer, sources_of
from src.services.exceptions import RepoIndexingError, RepoNotIndexedError
from src.services.progress import IndexProgress, NullProgress
from src.vectorstore.faiss_store import build_and_save_index, embed_chunks, index_exists, load_index, load_overview

# One lock per repo so concurrent /index calls for the same repo don't clone and write twice.
_index_locks: defaultdict[str, Lock] = defaultdict(Lock)


@dataclass
class IndexResult:
    repo_url: str
    reused_existing: bool
    num_chunks: int | None  # None when an existing index was reused (chunk count not recomputed)


@dataclass
class AnswerResult:
    answer: str
    sources: list[str]


def _human_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024**2:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024**2:.1f} MB"


def index_repository(
    repo_url: str, force_reindex: bool = False, progress: IndexProgress | None = None
) -> IndexResult:
    """Clone, chunk, embed, and persist a FAISS index for a repo, or reuse an existing one.
    `progress` receives live status for the UI; it may raise IndexCancelled between steps."""
    progress = progress or NullProgress()
    repo_url = normalize_repo_url(repo_url)

    with _index_locks[repo_url]:
        if index_exists(repo_url) and not force_reindex:
            progress.log("Existing index found; reusing it")
            return IndexResult(repo_url=repo_url, reused_existing=True, num_chunks=None)

        progress.step("clone")
        progress.log(f"Cloning {repo_url} (shallow)")

        def on_clone(label: str, fraction: float | None) -> None:
            progress.detail(f"{label} {fraction:.0%}" if fraction is not None else label)
            if fraction is not None:
                progress.fraction(fraction)

        try:
            local_path = clone_repo(repo_url, on_progress=on_clone)
        except GitCommandError as exc:
            raise RepoIndexingError(
                f"Failed to clone repository: {repo_url}. Check that it exists and is public."
            ) from exc
        progress.log("Clone complete")

        try:
            progress.check_cancelled()
            progress.step("scan")
            documents = load_repo_documents(local_path, settings.max_file_size_bytes)
            if not documents:
                raise RepoIndexingError(f"No indexable source/doc files found in repository: {repo_url}")

            languages = language_breakdown(documents)
            total_bytes = sum(size for _, size in languages)
            folders = len({posixpath.dirname(doc.metadata["source"]) for doc in documents} - {""})
            progress.stats(
                files=len(documents),
                folders=folders,
                bytes=total_bytes,
                languages=[{"name": name, "bytes": size} for name, size in languages],
            )
            top = ", ".join(name for name, _ in languages[:3])
            progress.log(f"Found {len(documents)} files in {folders} folders ({_human_bytes(total_bytes)}): {top}")

            progress.check_cancelled()
            progress.step("chunk")
            chunks = split_documents(documents, settings.chunk_size, settings.chunk_overlap)
            progress.stats(chunks=len(chunks))
            progress.log(f"Split into {len(chunks)} chunks of up to {settings.chunk_size} characters")

            progress.check_cancelled()
            progress.step("embed")
            progress.detail("Loading embedding model")
            progress.log(f"Embedding with {settings.embedding_model_id}")
            embeddings = get_embeddings()

            def on_embed(done: int, total: int) -> None:
                progress.check_cancelled()
                progress.stats(embedded=done)
                progress.detail(f"{done:,} / {total:,} chunks")
                progress.fraction(done / total if total else 1.0)

            vectors = embed_chunks(chunks, embeddings, on_progress=on_embed)
            progress.log(f"Embedded {len(chunks)} chunks")

            progress.check_cancelled()
            progress.step("overview")
            progress.detail("Summarizing the repository")
            overview = build_overview(documents)
            progress.log("Overview written")

            progress.check_cancelled()
            build_and_save_index(repo_url, chunks, embeddings, overview=overview, vectors=vectors)
            progress.log("Index saved")
            return IndexResult(repo_url=repo_url, reused_existing=False, num_chunks=len(chunks))
        finally:
            cleanup_repo(local_path)


def ask_question(repo_url: str, question: str) -> AnswerResult:
    """Answer a one-off question about a previously indexed repo (no chat memory; used by the CLI)."""
    repo_url = normalize_repo_url(repo_url)
    if not index_exists(repo_url):
        raise RepoNotIndexedError(f"Repository has not been indexed yet: {repo_url}")

    vector_store = load_index(repo_url, get_embeddings())
    docs = vector_store.similarity_search(question, k=settings.retriever_top_k)
    answer = generate_answer(question, docs, overview=load_overview(repo_url))
    return AnswerResult(answer=answer, sources=sources_of(docs))
