from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized, environment-driven configuration for the pipeline."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM (Groq). Optional at load time so indexing and /health work without it;
    # get_llm() raises a clear ConfigurationError when it's missing.
    groq_api_key: str | None = None
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

    # API: comma-separated origins allowed to call the backend from a browser
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def use_openai_embeddings(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def embedding_model_id(self) -> str:
        """Identifies the active embedding model; indexes are only valid for the model that built them."""
        if self.use_openai_embeddings:
            return f"openai:{self.openai_embedding_model}"
        return f"hf:{self.hf_embedding_model}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
