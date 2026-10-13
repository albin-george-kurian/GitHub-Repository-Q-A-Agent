from functools import lru_cache

from langchain_core.embeddings import Embeddings

from src.config import settings


@lru_cache(maxsize=1)
def get_embeddings() -> Embeddings:
    """Return OpenAI embeddings when an API key is configured, otherwise a local
    HuggingFace model so the pipeline runs with zero cost/key out of the box.

    Cached: loading the local model takes seconds and shouldn't happen per request."""
    if settings.use_openai_embeddings:
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=settings.openai_embedding_model, api_key=settings.openai_api_key)

    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(model_name=settings.hf_embedding_model)
