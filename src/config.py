from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized, environment-driven configuration for the pipeline."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM (Groq)
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"

    # Embeddings
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    hf_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Splitting
    chunk_size: int = 1000
    chunk_overlap: int = 200

    # Retrieval
    retriever_top_k: int = 6

    # Storage
    index_store_dir: str = "data/indexes"

    # Ingestion
    max_file_size_bytes: int = 1_000_000

    @property
    def use_openai_embeddings(self) -> bool:
        return bool(self.openai_api_key)


settings = Settings()
