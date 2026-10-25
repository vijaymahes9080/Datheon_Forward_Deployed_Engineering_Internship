"""Enterprise configuration management engine with Pydantic validation."""

from functools import lru_cache
from pathlib import Path
from typing import List, Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for AegisAI Enterprise Gateway."""

    model_config = SettingsConfigDict(
        env_prefix="AEGIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Runtime & Server
    HOST: str = Field(default="0.0.0.0", description="Server bind host")
    PORT: int = Field(default=8000, description="Server bind port")
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = Field(
        default="development", description="Runtime environment"
    )
    LOG_LEVEL: str = Field(default="INFO", description="Log level")
    ALLOWED_HOSTS: List[str] = Field(default_factory=lambda: ["*"])

    # Security & Tokens
    SECRET_KEY: str = Field(
        default="aegis-default-insecure-secret-key-change-in-production",
        description="Master secret key for HMAC and signature verification",
    )
    API_KEY_HEADER: str = Field(default="X-Aegis-API-Key", description="Header name for API keys")
    TOKEN_EXPIRATION_MINUTES: int = Field(default=60, description="Session token expiration in minutes")
    APPROVAL_TTL_SECONDS: int = Field(default=900, description="Approval token TTL in seconds (15m)")

    # Persistence & Storage
    DATABASE_URL: str = Field(
        default="sqlite:///./storage/aegis.db", description="Database connection URL"
    )
    CHROMA_PERSIST_DIR: str = Field(
        default="./storage/chroma_db", description="ChromaDB persistence directory"
    )
    STORAGE_DIR: str = Field(
        default="./storage/documents", description="Document file staging directory"
    )

    # Ingestion & ETL
    CHUNK_SIZE: int = Field(default=512, description="Structure-aware chunk token/char length")
    CHUNK_OVERLAP: int = Field(default=64, description="Chunk overlap boundary")
    MAX_CONCURRENT_INGESTIONS: int = Field(default=4, description="Maximum parallel ingestion tasks")

    # Embeddings & Retrieval
    EMBEDDING_PROVIDER: Literal["mock", "local", "ollama"] = Field(
        default="mock", description="Vector embedding provider"
    )
    EMBEDDING_MODEL: str = Field(
        default="all-MiniLM-L6-v2", description="Model identifier for embeddings"
    )
    EMBEDDING_DIMENSION: int = Field(default=384, description="Dimension of embedding vectors")
    TOP_K_RETRIEVAL: int = Field(default=5, description="Number of candidate passages to retrieve")
    CROSS_ENCODER_MODEL: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2", description="Cross-encoder model for reranking"
    )
    SIMILARITY_THRESHOLD: float = Field(
        default=0.20, description="Minimum cosine similarity score required for retrieval"
    )

    # LLM Generation
    LLM_PROVIDER: Literal["mock", "ollama"] = Field(
        default="mock", description="Language generation provider"
    )
    LLM_MODEL: str = Field(default="llama3:8b", description="Model name for generation")
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434", description="Ollama API base URL")

    def ensure_directories(self) -> None:
        """Create configured storage and database directories if absent."""
        Path(self.CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
        Path(self.STORAGE_DIR).mkdir(parents=True, exist_ok=True)
        db_path = self.DATABASE_URL.replace("sqlite:///", "")
        if db_path != ":memory:" and not db_path.startswith("sqlite+"):
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton instance of system configuration."""
    settings = Settings()
    settings.ensure_directories()
    return settings
