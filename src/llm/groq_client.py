from functools import lru_cache

from langchain_groq import ChatGroq

from src.config import settings
from src.services.exceptions import ConfigurationError


@lru_cache(maxsize=1)
def get_llm() -> ChatGroq:
    if not settings.groq_api_key:
        raise ConfigurationError("GROQ_API_KEY is not set. Add it to .env (https://console.groq.com/keys).")
    return ChatGroq(model=settings.groq_model, api_key=settings.groq_api_key, temperature=0)
