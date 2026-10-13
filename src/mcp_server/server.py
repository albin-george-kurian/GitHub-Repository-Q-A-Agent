"""MCP server exposing the repository Q&A agent and live GitHub data as tools (FastMCP)."""

import asyncio
from typing import Annotated, Any, Literal

import anyio
from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from src.github.client import GitHubError, get_github
from src.ingestion.repo_url import resolve_repo_ref
from src.services import index_jobs
from src.services.exceptions import (
    ConfigurationError,
    IndexBusyError,
    InvalidRepoUrlError,
    RepoNotIndexedError,
    rejected_key_message,
)
from src.services.qa_service import ask_question
from src.vectorstore.faiss_store import index_exists

_PROGRESS_POLL_SECONDS = 0.5

mcp = FastMCP(
    name="repo-qa",
    instructions=(
        "Tools for understanding public GitHub repositories. "
        "Use ask_repository for questions about how the code works: it indexes the repository on first use "
        "(this can take a minute or two) and answers from the source with file citations. "
        "Use the GitHub tools for project activity: get_repo_info for an overview, search_issues/get_issue for "
        "bugs and discussions, list_pull_requests/get_pull_request for proposed changes, get_file_history for "
        "who changed a file and when, list_releases for versions and changelogs. "
        "Repositories can be given as a URL or as owner/name."
    ),
)

RepoRef = Annotated[str, Field(description="GitHub repository, as https://github.com/owner/name or owner/name")]
Limit = Annotated[int, Field(ge=1, le=50, description="Maximum number of items to return (1-50)")]
State = Annotated[Literal["open", "closed", "all"], Field(description="Filter by state")]

_READ_ONLY = {"read_only_hint": True, "open_world_hint": True, "idempotent_hint": True}


def _repo(ref: str) -> str:
    try:
        return resolve_repo_ref(ref)
    except InvalidRepoUrlError as exc:
        raise ToolError(str(exc)) from exc


def _github(call):
    try:
        return call()
    except GitHubError as exc:
        raise ToolError(str(exc)) from exc


def _blob_url(repo_url: str, path: str) -> str:
    return f"{repo_url}/blob/HEAD/{path}"


# ---------- Repository Q&A (the app's RAG agent) ----------


async def _ensure_indexed(repo_url: str, reindex: bool, ctx: Context) -> dict[str, Any] | None:
    """Index the repo if needed, streaming real step progress to the client. Returns the final job
    snapshot, or None when an existing index was used."""
    if index_exists(repo_url) and not reindex:
        return None
    try:
        job = index_jobs.start(repo_url, force=True)
    except IndexBusyError as exc:
        raise ToolError(str(exc)) from exc

    try:
        while True:
            snap = index_jobs.snapshot(job)
            active = next((s for s in snap["steps"] if s["status"] == "active"), None)
            message = f"{active['label']}: {active['detail']}" if active and active["detail"] else (active or {}).get("label")
            await ctx.report_progress(round(snap["progress"] * 100, 1), 100, message)
            if snap["status"] != "running":
                break
            await asyncio.sleep(_PROGRESS_POLL_SECONDS)
    except asyncio.CancelledError:
        index_jobs.cancel(job.id)  # client cancelled the tool call: stop indexing too
        raise

    if snap["status"] != "done":
        raise ToolError(snap["error"] or f"Indexing {snap['status']}.")
    return snap


@mcp.tool(
    annotations={"title": "Ask about a repository's code", "read_only_hint": False, "open_world_hint": True},
)
async def ask_repository(
    repo: RepoRef,
    question: Annotated[str, Field(min_length=1, max_length=2000, description="Question about the code")],
    ctx: Context,
    reindex: Annotated[bool, Field(description="Rebuild the index first to pick up recent changes")] = False,
) -> dict[str, Any]:
    """Answer a question about a repository's source code, grounded in its files.

    Indexes the repository automatically on first use (clone, chunk, embed; usually under a few minutes,
    with progress updates). Answers cite the files they are based on. Says so when the indexed code
    doesn't contain the answer instead of guessing."""
    repo_url = _repo(repo)
    job = await _ensure_indexed(repo_url, reindex, ctx)

    try:
        result = await anyio.to_thread.run_sync(ask_question, repo_url, question)
    except (ConfigurationError, RepoNotIndexedError) as exc:
        raise ToolError(str(exc)) from exc
    except Exception as exc:
        raise ToolError(rejected_key_message(exc) or f"Answering failed: {exc}") from exc

    return {
        "repository": repo_url,
        "answer": result.answer,
        "sources": [{"path": path, "url": _blob_url(repo_url, path)} for path in result.sources],
        "indexed_now": job is not None,
        **({"chunks_indexed": job["num_chunks"]} if job else {}),
    }


# ---------- Live GitHub data ----------


@mcp.tool(annotations={"title": "Repository info", **_READ_ONLY})
def get_repo_info(repo: RepoRef) -> dict[str, Any]:
    """Repository metadata: description, stars, forks, main language, topics, license, default branch,
    and when it was created and last pushed to."""
    repo_url = _repo(repo)
    return _github(lambda: get_github().repo_info(repo_url))


@mcp.tool(annotations={"title": "Search issues", **_READ_ONLY})
def search_issues(
    repo: RepoRef,
    query: Annotated[str, Field(description="Search text, e.g. 'timeout' or 'label:bug'. Empty lists recent issues.")] = "",
    state: State = "open",
    limit: Limit = 10,
) -> dict[str, Any]:
    """Search a repository's issues (not pull requests). Returns number, title, state, labels, comment
    count and a short excerpt for each; use get_issue for the full discussion."""
    repo_url = _repo(repo)
    return _github(lambda: get_github().search_issues(repo_url, query, state, limit))


@mcp.tool(annotations={"title": "Get issue", **_READ_ONLY})
def get_issue(
    repo: RepoRef,
    number: Annotated[int, Field(ge=1, description="Issue number")],
    max_comments: Annotated[int, Field(ge=0, le=50, description="How many comments to include")] = 10,
) -> dict[str, Any]:
    """Full issue: description, labels, assignees, state, and the first comments."""
    repo_url = _repo(repo)
    return _github(lambda: get_github().issue(repo_url, number, max_comments))


@mcp.tool(annotations={"title": "List pull requests", **_READ_ONLY})
def list_pull_requests(repo: RepoRef, state: State = "open", limit: Limit = 10) -> list[dict[str, Any]]:
    """Pull requests, most recently updated first, with author, branches and state (open/closed/merged)."""
    repo_url = _repo(repo)
    return _github(lambda: get_github().list_pull_requests(repo_url, state, limit))


@mcp.tool(annotations={"title": "Get pull request", **_READ_ONLY})
def get_pull_request(
    repo: RepoRef,
    number: Annotated[int, Field(ge=1, description="Pull request number")],
    max_files: Annotated[int, Field(ge=1, le=100, description="How many changed files to list")] = 30,
    include_patches: Annotated[bool, Field(description="Include each file's diff (truncated)")] = True,
) -> dict[str, Any]:
    """A pull request's description, stats and changed files, optionally with diffs."""
    repo_url = _repo(repo)
    return _github(lambda: get_github().pull_request(repo_url, number, max_files, include_patches))


@mcp.tool(annotations={"title": "File history", **_READ_ONLY})
def get_file_history(
    repo: RepoRef,
    path: Annotated[str, Field(min_length=1, description="File or folder path from the repo root, e.g. src/app.py")],
    limit: Limit = 10,
) -> dict[str, Any]:
    """Recent commits that changed a file or folder: short SHA, first line of the message, author, date."""
    repo_url = _repo(repo)
    return _github(lambda: get_github().file_history(repo_url, path, limit))


@mcp.tool(annotations={"title": "List releases", **_READ_ONLY})
def list_releases(repo: RepoRef, limit: Annotated[int, Field(ge=1, le=30)] = 5) -> list[dict[str, Any]]:
    """Published releases, newest first, with tag, date and release notes (truncated)."""
    repo_url = _repo(repo)
    return _github(lambda: get_github().releases(repo_url, limit))
