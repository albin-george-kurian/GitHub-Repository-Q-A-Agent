class RepoIndexingError(Exception):
    """Raised when cloning or indexing a repository fails."""


class RepoNotIndexedError(Exception):
    """Raised when a query targets a repo that hasn't been indexed yet."""
