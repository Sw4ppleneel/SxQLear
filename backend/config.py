from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings. All values can be overridden via environment variables
    or a .env file in the backend directory.

    Design intent: SxQLear is local-first. Cloud dependencies are opt-in only.
    Sensitive values (API keys) are never logged or exposed in responses.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_name: str = "SxQLear"
    debug: bool = False
    api_port: int = 8000
    api_host: str = "127.0.0.1"  # Local-only by default

    # ── Local data directory ──────────────────────────────────────────────────
    # All project data, memory, and snapshots live here.
    # Never put raw query results here; only schema metadata.
    data_dir: Path = Path.home() / ".sxqlear"

    @property
    def memory_db_path(self) -> str:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return str(self.data_dir / "memory.db")

    @property
    def projects_dir(self) -> Path:
        path = self.data_dir / "projects"
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ── Schema crawling ───────────────────────────────────────────────────────
    max_tables_per_crawl: int = 500
    max_sample_rows: int = 10       # Per column, for value sampling
    crawl_timeout_seconds: int = 30

    # ── Inference engine ──────────────────────────────────────────────────────
    min_inference_score: float = 0.20   # Relationships below this are dropped
    enable_statistical_profiling: bool = True
    enable_sample_values: bool = True   # Set False for stricter privacy posture

    # ── Optional: LLM integration ────────────────────────────────────────────
    # The inference engine works fully without these.
    # LLMs are used only for reasoning on ambiguous cases when enabled.
    enable_llm_inference: bool = False
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "gpt-4o-mini"

    # ── Optional: Embedding-based semantic inference ──────────────────────────
    enable_semantic_inference: bool = False
    embedding_model: str = "all-MiniLM-L6-v2"  # sentence-transformers


settings = Settings()
