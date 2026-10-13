from functools import lru_cache

from langchain_groq import ChatGroq

from src.config import settings
from src.services.exceptions import ConfigurationError


def _require_key() -> str:
    if not settings.groq_api_key:
        raise ConfigurationError("GROQ_API_KEY is not set. Add it to .env (https://console.groq.com/keys).")
    return settings.groq_api_key


@lru_cache(maxsize=1)
def get_llm() -> ChatGroq:
    """Main model, used to write answers and repo overviews."""
    return ChatGroq(model=settings.groq_model, api_key=_require_key(), temperature=0)


@lru_cache(maxsize=1)
def get_fast_llm() -> ChatGroq:
    """Small model for cheap housekeeping: rewriting follow-ups, summaries, memory extraction."""
    return ChatGroq(model=settings.groq_fast_model, api_key=_require_key(), temperature=0)
