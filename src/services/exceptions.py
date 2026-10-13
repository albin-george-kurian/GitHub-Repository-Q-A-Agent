class RepoIndexingError(Exception):
    """Raised when cloning or indexing a repository fails."""


class RepoNotIndexedError(Exception):
    """Raised when a query targets a repo that hasn't been indexed yet."""


class InvalidRepoUrlError(ValueError):
    """Raised when a URL isn't a valid public GitHub repository URL."""


class ConfigurationError(RuntimeError):
    """Raised when required configuration (e.g. an API key) is missing."""


class ChatNotFoundError(LookupError):
    """Raised when a chat doesn't exist or belongs to another user."""
