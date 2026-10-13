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


_SHORTHAND = re.compile(r"^(?P<owner>[\w.-]+)/(?P<name>[\w.-]+?)(?:\.git)?$")


def resolve_repo_ref(ref: str) -> str:
    """Like normalize_repo_url, but also accepts the "owner/name" shorthand AI clients tend to use."""
    match = _SHORTHAND.match(ref.strip())
    if match and "://" not in ref:
        ref = f"https://github.com/{match['owner']}/{match['name']}"
    return normalize_repo_url(ref)


def owner_and_name(repo_url: str) -> tuple[str, str]:
    """("owner", "name") for a normalized GitHub repo URL."""
    owner, name = repo_url.rstrip("/").split("/")[-2:]
    return owner, name
