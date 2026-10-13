from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized, environment-driven configuration for the pipeline."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # The project's .env wins over inherited OS variables, so `OPENAI_API_KEY=` (empty) in .env
        # really disables OpenAI even if a stale key is set machine-wide. Without a .env, OS
        # variables still apply (e.g. in deployments).
        return init_settings, dotenv_settings, env_settings, file_secret_settings

    # LLM (Groq). Optional at load time so indexing and /health work without it;
    # get_llm() raises a clear ConfigurationError when it's missing.
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    # Model for housekeeping calls (question rewriting, summaries, memory extraction). The rewrite
    # decides what gets retrieved, so the default favours quality; set a smaller model to save quota.
    groq_fast_model: str = "openai/gpt-oss-120b"

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

    # Memory (chat history, summaries, user memories, past Q&A recall)
    memory_db_path: str = "data/memory.db"
    history_recent_messages: int = 4  # unsummarized turns always kept verbatim
    summarize_after_messages: int = 10  # fold older turns into the chat summary past this many
    history_message_max_chars: int = 1200
    related_qa_top_k: int = 2
    related_qa_min_similarity: float = 0.55
    auto_memory: bool = True  # learn user preferences from what they say
    max_memories_per_user: int = 50

    # GitHub REST API (MCP GitHub tools). Optional: without a token GitHub allows 60 requests/hour,
    # with one 5,000/hour. A fine-grained token with read-only public access is enough.
    github_token: str | None = None

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
