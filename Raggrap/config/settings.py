"""Application configuration settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # AI API Keys
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    # Optional OpenAI-compatible gateway base URL (e.g. a local/proxy /v1).
    openai_base_url: str | None = None

    # LLM Configuration
    llm_provider: str = "auto"
    main_llm_model: str = "gpt-4o"
    critic_llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 2000

    # Neo4j Configuration
    neo4j_uri: str | None = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str | None = None

    # Redis Configuration
    redis_host: str | None = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None

    # Cache Settings
    cache_ttl: int = 3600
    enable_cache: bool = True

    # ChromaDB Configuration
    enable_vector_search: bool = True
    chroma_persist_dir: str = "./data/chroma"
    chroma_collection_name: str = "raggrap_embeddings"

    # Application Settings
    app_name: str = "RagGrap"
    app_version: str = "1.0.0"
    log_level: str = "INFO"
    environment: str = "development"

    # API Settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 1

    # SpaCy Configuration
    spacy_model: str = "en_core_web_sm"

    # Performance Tuning
    max_related_mistakes: int = 5
    max_retries: int = 3
    retry_delay: int = 1


settings = Settings()
