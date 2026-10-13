import re

from src.services.exceptions import InvalidRepoUrlError

_GITHUB_REPO = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[\w.-]+)/(?P<name>[\w.-]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


def normalize_repo_url(repo_url: str) -> str:
    """Canonical form of a GitHub repo URL, so `.../Repo`, `.../repo/` and `.../repo.git`
    all map to the same index. GitHub owner/repo names are case-insensitive."""
    match = _GITHUB_REPO.match(repo_url.strip())
    if not match:
        raise InvalidRepoUrlError(
            f"Not a GitHub repository URL: {repo_url!r}. Expected https://github.com/<owner>/<repo>"
        )
    return f"https://github.com/{match['owner'].lower()}/{match['name'].lower()}"
