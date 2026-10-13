"""Small read-only client for the GitHub REST API, shaped for AI tools: compact JSON,
long text truncated, and errors that say what to do next."""

from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from src.config import settings
from src.ingestion.repo_url import owner_and_name

API_URL = "https://api.github.com"
_BODY_CHARS = 6000
_COMMENT_CHARS = 1500
_PATCH_CHARS = 1500
_EXCERPT_CHARS = 280


class GitHubError(Exception):
    """A GitHub API failure with a message fit to show the user/AI client."""


def _clip(text: str | None, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + f"\n… [truncated, {len(text) - limit} more chars]"


def _first_line(text: str | None) -> str:
    return text.strip().splitlines()[0] if text and text.strip() else ""


def _login(user: dict | None) -> str | None:
    return user.get("login") if user else None


class GitHubClient:
    def __init__(self, token: str | None = None, transport: httpx.BaseTransport | None = None, timeout: float = 20):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._authenticated = bool(token)
        self._http = httpx.Client(base_url=API_URL, headers=headers, timeout=timeout, transport=transport)

    # ---------- transport ----------

    def _get(self, path: str, params: dict[str, Any] | None = None, what: str = "resource") -> Any:
        try:
            res = self._http.get(path, params=params)
        except httpx.HTTPError as exc:
            raise GitHubError(f"Could not reach the GitHub API: {exc}") from exc

        if res.status_code < 400:
            return res.json()
        if res.status_code in (403, 429) and res.headers.get("x-ratelimit-remaining") == "0":
            reset = res.headers.get("x-ratelimit-reset")
            when = (
                datetime.fromtimestamp(int(reset), tz=timezone.utc).strftime("%H:%M UTC") if reset else "soon"
            )
            hint = "" if self._authenticated else " Set GITHUB_TOKEN in .env to raise the limit to 5,000/hour."
            raise GitHubError(f"GitHub API rate limit reached; it resets at {when}.{hint}")
        if res.status_code == 401:
            raise GitHubError("GitHub rejected GITHUB_TOKEN (invalid or expired). Update or remove it in .env.")
        if res.status_code == 404:
            raise GitHubError(f"Not found on GitHub: {what}. Check the repository and number; private repos aren't supported.")
        try:
            message = res.json().get("message", res.text)
        except ValueError:
            message = res.text
        raise GitHubError(f"GitHub API error {res.status_code}: {message}")

    # ---------- tools ----------

    def repo_info(self, repo_url: str) -> dict[str, Any]:
        owner, name = owner_and_name(repo_url)
        r = self._get(f"/repos/{owner}/{name}", what=f"repository {owner}/{name}")
        return {
            "full_name": r["full_name"],
            "description": r.get("description"),
            "url": r["html_url"],
            "homepage": r.get("homepage") or None,
            "default_branch": r["default_branch"],
            "language": r.get("language"),
            "topics": r.get("topics", []),
            "license": (r.get("license") or {}).get("spdx_id"),
            "stars": r["stargazers_count"],
            "forks": r["forks_count"],
            "watchers": r.get("subscribers_count"),
            "open_issues_and_prs": r["open_issues_count"],
            "size_kb": r.get("size"),
            "created_at": r["created_at"],
            "last_push": r.get("pushed_at"),
            "archived": r.get("archived", False),
            "is_fork": r.get("fork", False),
        }

    def search_issues(
        self, repo_url: str, query: str, state: Literal["open", "closed", "all"], limit: int
    ) -> dict[str, Any]:
        owner, name = owner_and_name(repo_url)
        q = f"repo:{owner}/{name} is:issue"
        if state != "all":
            q += f" state:{state}"
        if query.strip():
            q += f" {query.strip()}"
        params: dict[str, Any] = {"q": q, "per_page": limit}
        if not query.strip():
            params["sort"] = "updated"  # no search text: most recently active first
        r = self._get("/search/issues", params, what=f"issues in {owner}/{name}")
        return {
            "total_count": r["total_count"],
            "issues": [
                {
                    "number": i["number"],
                    "title": i["title"],
                    "state": i["state"],
                    "author": _login(i.get("user")),
                    "labels": [label["name"] for label in i.get("labels", [])],
                    "comments": i.get("comments", 0),
                    "created_at": i["created_at"],
                    "updated_at": i["updated_at"],
                    "url": i["html_url"],
                    "excerpt": _clip(i.get("body"), _EXCERPT_CHARS),
                }
                for i in r.get("items", [])
            ],
        }

    def issue(self, repo_url: str, number: int, max_comments: int) -> dict[str, Any]:
        owner, name = owner_and_name(repo_url)
        i = self._get(f"/repos/{owner}/{name}/issues/{number}", what=f"issue #{number} in {owner}/{name}")
        comments = []
        if max_comments > 0 and i.get("comments", 0) > 0:
            raw = self._get(
                f"/repos/{owner}/{name}/issues/{number}/comments",
                {"per_page": max_comments},
                what=f"comments on #{number}",
            )
            comments = [
                {"author": _login(c.get("user")), "created_at": c["created_at"], "body": _clip(c.get("body"), _COMMENT_CHARS)}
                for c in raw
            ]
        result = {
            "number": i["number"],
            "title": i["title"],
            "state": i["state"],
            "state_reason": i.get("state_reason"),
            "author": _login(i.get("user")),
            "labels": [label["name"] for label in i.get("labels", [])],
            "assignees": [_login(a) for a in i.get("assignees", [])],
            "created_at": i["created_at"],
            "closed_at": i.get("closed_at"),
            "url": i["html_url"],
            "body": _clip(i.get("body"), _BODY_CHARS),
            "comments_total": i.get("comments", 0),
            "comments": comments,
        }
        if "pull_request" in i:
            result["note"] = "This number is a pull request; get_pull_request shows its changes."
        return result

    def list_pull_requests(
        self, repo_url: str, state: Literal["open", "closed", "all"], limit: int
    ) -> list[dict[str, Any]]:
        owner, name = owner_and_name(repo_url)
        raw = self._get(
            f"/repos/{owner}/{name}/pulls",
            {"state": state, "sort": "updated", "direction": "desc", "per_page": limit},
            what=f"pull requests in {owner}/{name}",
        )
        return [
            {
                "number": p["number"],
                "title": p["title"],
                "state": "merged" if p.get("merged_at") else p["state"],
                "draft": p.get("draft", False),
                "author": _login(p.get("user")),
                "head": p["head"]["ref"],
                "base": p["base"]["ref"],
                "created_at": p["created_at"],
                "updated_at": p["updated_at"],
                "url": p["html_url"],
            }
            for p in raw
        ]

    def pull_request(self, repo_url: str, number: int, max_files: int, include_patches: bool) -> dict[str, Any]:
        owner, name = owner_and_name(repo_url)
        p = self._get(f"/repos/{owner}/{name}/pulls/{number}", what=f"pull request #{number} in {owner}/{name}")
        files = self._get(
            f"/repos/{owner}/{name}/pulls/{number}/files", {"per_page": max_files}, what=f"files of PR #{number}"
        )
        return {
            "number": p["number"],
            "title": p["title"],
            "state": "merged" if p.get("merged") else p["state"],
            "draft": p.get("draft", False),
            "author": _login(p.get("user")),
            "head": p["head"]["ref"],
            "base": p["base"]["ref"],
            "created_at": p["created_at"],
            "merged_at": p.get("merged_at"),
            "url": p["html_url"],
            "body": _clip(p.get("body"), _BODY_CHARS),
            "commits": p.get("commits"),
            "additions": p.get("additions"),
            "deletions": p.get("deletions"),
            "changed_files": p.get("changed_files"),
            "files_shown": len(files),
            "files": [
                {
                    "path": f["filename"],
                    "status": f["status"],
                    "additions": f["additions"],
                    "deletions": f["deletions"],
                    **({"patch": _clip(f.get("patch"), _PATCH_CHARS)} if include_patches and f.get("patch") else {}),
                }
                for f in files
            ],
        }

    def file_history(self, repo_url: str, path: str, limit: int) -> dict[str, Any]:
        owner, name = owner_and_name(repo_url)
        path = path.strip().lstrip("/")
        raw = self._get(
            f"/repos/{owner}/{name}/commits", {"path": path, "per_page": limit}, what=f"history of {path}"
        )
        result: dict[str, Any] = {
            "path": path,
            "commits": [
                {
                    "sha": c["sha"][:7],
                    "message": _first_line(c["commit"].get("message")),
                    "author": _login(c.get("author")) or (c["commit"].get("author") or {}).get("name"),
                    "date": (c["commit"].get("author") or {}).get("date"),
                    "url": c["html_url"],
                }
                for c in raw
            ],
        }
        if not raw:
            result["note"] = "No commits touch this path. Paths are case-sensitive and relative to the repo root."
        return result

    def releases(self, repo_url: str, limit: int) -> list[dict[str, Any]]:
        owner, name = owner_and_name(repo_url)
        raw = self._get(f"/repos/{owner}/{name}/releases", {"per_page": limit}, what=f"releases of {owner}/{name}")
        return [
            {
                "tag": r["tag_name"],
                "name": r.get("name") or r["tag_name"],
                "published_at": r.get("published_at"),
                "prerelease": r.get("prerelease", False),
                "url": r["html_url"],
                "notes": _clip(r.get("body"), 2000),
            }
            for r in raw
            if not r.get("draft")
        ]


_client: GitHubClient | None = None


def get_github() -> GitHubClient:
    """Shared client (connection reuse). Tests swap it with set_github()."""
    global _client
    if _client is None:
        _client = GitHubClient(token=settings.github_token)
    return _client


def set_github(client: GitHubClient | None) -> None:
    global _client
    _client = client
