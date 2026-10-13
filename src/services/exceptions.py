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


class IndexCancelled(Exception):
    """Raised inside an indexing run when the user cancelled it."""


class IndexBusyError(RuntimeError):
    """Raised when too many repositories are being indexed at once."""


def rejected_key_message(exc: BaseException | None) -> str | None:
    """Readable message when OpenAI or Groq rejects the configured API key (HTTP 401)."""
    while exc is not None:
        if type(exc).__name__ == "AuthenticationError":
            provider = type(exc).__module__.split(".")[0]
            if provider == "openai":
                return (
                    "OpenAI rejected OPENAI_API_KEY (invalid or revoked). Replace it, or leave "
                    "OPENAI_API_KEY empty in .env to use the free local embedding model, then restart the API."
                )
            if provider == "groq":
                return "Groq rejected GROQ_API_KEY (invalid or revoked). Update it in .env and restart the API."
        exc = exc.__cause__ or exc.__context__
    return None
