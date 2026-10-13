"""MCP server tests through FastMCP's in-memory client. GitHub is faked with httpx.MockTransport,
the LLM/embeddings/clone with the fixtures in conftest.py, so nothing touches the network."""

import httpx
import pytest
from fastmcp import Client

from src.github.client import GitHubClient, set_github
from src.mcp_server.server import mcp
from src.rag import qa_chain
from src.services.exceptions import ConfigurationError

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _issue(number, **extra):
    return {
        "number": number,
        "title": f"Issue {number}",
        "state": "open",
        "user": {"login": "alice"},
        "labels": [{"name": "bug"}],
        "comments": 2,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
        "html_url": f"https://github.com/acme/widgets/issues/{number}",
        "body": "x" * 500,
        **extra,
    }


def _pr(number, merged_at=None, state="closed"):
    return {
        "number": number,
        "title": f"PR {number}",
        "state": state,
        "merged_at": merged_at,
        "draft": False,
        "user": {"login": "bob"},
        "head": {"ref": "feature"},
        "base": {"ref": "main"},
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-03T00:00:00Z",
        "html_url": f"https://github.com/acme/widgets/pull/{number}",
    }


ROUTES = {
    "/repos/acme/widgets": {
        "full_name": "acme/widgets",
        "description": "Signing toolkit",
        "html_url": "https://github.com/acme/widgets",
        "homepage": "",
        "default_branch": "main",
        "language": "Python",
        "topics": ["crypto"],
        "license": {"spdx_id": "MIT"},
        "stargazers_count": 42,
        "forks_count": 7,
        "subscribers_count": 3,
        "open_issues_count": 5,
        "size": 120,
        "created_at": "2020-01-01T00:00:00Z",
        "pushed_at": "2026-10-01T00:00:00Z",
    },
    "/search/issues": {"total_count": 1, "items": [_issue(7)]},
    "/repos/acme/widgets/issues/7": _issue(7),
    "/repos/acme/widgets/issues/7/comments": [
        {"user": {"login": "carol"}, "created_at": "2026-01-02T00:00:00Z", "body": "Same here"},
        {"user": {"login": "dave"}, "created_at": "2026-01-03T00:00:00Z", "body": "Fixed in #9"},
    ],
    "/repos/acme/widgets/issues/9": _issue(9, comments=0, pull_request={"url": "..."}),
    "/repos/acme/widgets/pulls": [_pr(9, merged_at="2026-01-04T00:00:00Z"), _pr(8), _pr(10, state="open")],
    "/repos/acme/widgets/pulls/9": {**_pr(9), "merged": True, "body": "Fixes #7", "commits": 2, "additions": 10, "deletions": 3, "changed_files": 1},
    "/repos/acme/widgets/pulls/9/files": [
        {"filename": "src/signer.py", "status": "modified", "additions": 10, "deletions": 3, "patch": "@@ -1 +1 @@\n" + "+line\n" * 600}
    ],
    "/repos/acme/widgets/commits": [],
    "/repos/acme/widgets/releases": [
        {"tag_name": "v2.0.0", "name": "", "published_at": "2026-05-01T00:00:00Z", "prerelease": False, "draft": False, "html_url": "u", "body": "Big release"},
        {"tag_name": "v2.1.0-draft", "name": "draft", "published_at": None, "prerelease": False, "draft": True, "html_url": "u", "body": ""},
    ],
}


@pytest.fixture
def github():
    """Fake GitHub API. Returns the list of requests made, for assertions on query parameters."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/repos/acme/limited":
            return httpx.Response(403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1893456000"}, json={"message": "rate limited"})
        if request.url.path == "/repos/acme/widgets/commits" and request.url.params.get("path") == "src/signer.py":
            commit = {"sha": "abcdef1234567", "html_url": "c", "author": {"login": "alice"},
                      "commit": {"message": "Fix verify\n\nLonger body", "author": {"name": "Alice", "date": "2026-02-01T00:00:00Z"}}}
            return httpx.Response(200, json=[commit])
        body = ROUTES.get(request.url.path)
        return httpx.Response(200, json=body) if body is not None else httpx.Response(404, json={"message": "Not Found"})

    set_github(GitHubClient(transport=httpx.MockTransport(handler)))
    yield seen
    set_github(None)


async def call(name: str, args: dict):
    async with Client(mcp) as client:
        return await client.call_tool(name, args, raise_on_error=False)


# ---------- server shape ----------


async def test_exposes_all_tools_with_hints():
    async with Client(mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
    assert set(tools) == {
        "ask_repository", "get_repo_info", "search_issues", "get_issue",
        "list_pull_requests", "get_pull_request", "get_file_history", "list_releases",
    }
    assert all(tools[n].annotations.read_only_hint for n in tools if n != "ask_repository")
    assert "ctx" not in tools["ask_repository"].input_schema["properties"]


# ---------- ask_repository (the RAG agent) ----------


async def test_ask_repository_uses_existing_index(llm):
    result = await call("ask_repository", {"repo": "acme/widgets", "question": "How is a signature verified?"})
    assert not result.is_error, result.content
    data = result.data
    assert data["answer"] == "ANSWER"
    assert data["indexed_now"] is False
    assert {"path": "src/signer.py", "url": "https://github.com/acme/widgets/blob/HEAD/src/signer.py"} in data["sources"]
    assert "Widgets is a signing library." in llm.calls[-1][0].content  # overview reached the prompt


async def test_ask_repository_indexes_first_and_streams_progress(fake_clone):
    updates: list[tuple[float, float | None, str | None]] = []

    async def on_progress(progress, total, message):
        updates.append((progress, total, message))

    async with Client(mcp) as client:
        result = await client.call_tool(
            "ask_repository", {"repo": "https://github.com/acme/gadgets", "question": "What is this?"},
            progress_handler=on_progress,
        )
    assert result.data["indexed_now"] is True
    assert result.data["chunks_indexed"] > 0
    assert updates[-1][:2] == (100.0, 100)
    assert [u[0] for u in updates] == sorted(u[0] for u in updates)  # progress never goes backwards


async def test_ask_repository_explains_missing_llm_key(llm, monkeypatch):
    def no_key():
        raise ConfigurationError("GROQ_API_KEY is not set.")

    monkeypatch.setattr(qa_chain, "get_llm", no_key)
    result = await call("ask_repository", {"repo": "acme/widgets", "question": "hi"})
    assert result.is_error
    assert "GROQ_API_KEY" in result.content[0].text


async def test_invalid_repository_is_rejected():
    result = await call("get_repo_info", {"repo": "https://gitlab.com/a/b"})
    assert result.is_error
    assert "Not a GitHub repository URL" in result.content[0].text


# ---------- GitHub tools ----------


async def test_get_repo_info(github):
    data = (await call("get_repo_info", {"repo": "acme/widgets"})).data
    assert data["stars"] == 42 and data["license"] == "MIT" and data["homepage"] is None


async def test_search_issues_builds_query(github):
    data = (await call("search_issues", {"repo": "acme/widgets", "query": "timeout", "state": "closed", "limit": 5})).data
    params = github[-1].url.params
    assert params["q"] == "repo:acme/widgets is:issue state:closed timeout"
    assert params["per_page"] == "5" and "sort" not in params
    assert data["issues"][0]["labels"] == ["bug"]
    assert data["issues"][0]["excerpt"].endswith("more chars]")  # long bodies are truncated

    await call("search_issues", {"repo": "acme/widgets", "state": "all"})
    params = github[-1].url.params
    assert params["q"] == "repo:acme/widgets is:issue" and params["sort"] == "updated"


async def test_get_issue_with_comments_and_pr_hint(github):
    issue = (await call("get_issue", {"repo": "acme/widgets", "number": 7, "max_comments": 2})).data
    assert [c["author"] for c in issue["comments"]] == ["carol", "dave"]
    assert "note" not in issue

    pr_as_issue = (await call("get_issue", {"repo": "acme/widgets", "number": 9})).data
    assert "get_pull_request" in pr_as_issue["note"]


async def test_pull_requests(github):
    prs = (await call("list_pull_requests", {"repo": "acme/widgets", "state": "all"})).data
    assert [(p["number"], p["state"]) for p in prs] == [(9, "merged"), (8, "closed"), (10, "open")]

    pr = (await call("get_pull_request", {"repo": "acme/widgets", "number": 9})).data
    assert pr["state"] == "merged" and pr["files"][0]["path"] == "src/signer.py"
    assert len(pr["files"][0]["patch"]) < 1600  # diff truncated

    no_patch = (await call("get_pull_request", {"repo": "acme/widgets", "number": 9, "include_patches": False})).data
    assert "patch" not in no_patch["files"][0]


async def test_file_history(github):
    hist = (await call("get_file_history", {"repo": "acme/widgets", "path": "/src/signer.py"})).data
    assert hist["commits"] == [
        {"sha": "abcdef1", "message": "Fix verify", "author": "alice", "date": "2026-02-01T00:00:00Z", "url": "c"}
    ]
    empty = (await call("get_file_history", {"repo": "acme/widgets", "path": "nope.py"})).data
    assert empty["commits"] == [] and "case-sensitive" in empty["note"]


async def test_list_releases_skips_drafts(github):
    releases = (await call("list_releases", {"repo": "acme/widgets"})).data
    assert [r["tag"] for r in releases] == ["v2.0.0"]
    assert releases[0]["name"] == "v2.0.0"


async def test_github_errors_are_readable(github):
    missing = await call("get_issue", {"repo": "acme/widgets", "number": 404})
    assert missing.is_error and "Not found on GitHub: issue #404" in missing.content[0].text

    limited = await call("get_repo_info", {"repo": "acme/limited"})
    assert limited.is_error
    text = limited.content[0].text
    assert "rate limit" in text and "GITHUB_TOKEN" in text


async def test_tool_input_is_validated(github):
    result = await call("search_issues", {"repo": "acme/widgets", "limit": 500})
    assert result.is_error
    assert github == []  # invalid input is rejected before any GitHub request
