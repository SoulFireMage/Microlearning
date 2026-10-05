"""Runtime configuration, read once from the environment."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_db_path() -> Path:
    explicit = os.environ.get("DB_PATH")
    if explicit:
        return Path(explicit)
    data_dir = Path(os.environ.get("DATA_DIR", "/data"))
    if data_dir.is_dir() and os.access(data_dir, os.W_OK):
        return data_dir / "app.db"
    return Path("./app.db")


def _default_journal_mode(db_path: Path) -> str:
    explicit = os.environ.get("SQLITE_JOURNAL_MODE")
    if explicit:
        return explicit.upper()
    # On HF Spaces, /data is a mounted Storage Bucket (object storage behind a
    # filesystem layer). WAL needs a shared-memory index (-shm) that such
    # mounts often cannot provide, so use the classic rollback journal there.
    if str(db_path).startswith("/data"):
        return "DELETE"
    return "WAL"


@dataclass
class Settings:
    db_path: Path = field(default_factory=_default_db_path)
    hf_token: str | None = field(default_factory=lambda: os.environ.get("HF_TOKEN"))
    default_model: str = field(
        default_factory=lambda: os.environ.get("DEFAULT_MODEL", "Qwen/Qwen3.8-27B")
    )
    inference_provider: str = field(
        default_factory=lambda: os.environ.get("INFERENCE_PROVIDER", "auto")
    )
    llm_timeout: float = field(
        default_factory=lambda: float(os.environ.get("LLM_TIMEOUT", "90"))
    )
    # OpenRouter (OpenAI-compatible). If its key is set it takes precedence
    # over HF Inference Providers; LLM_BACKEND=hf|openrouter forces a choice.
    openrouter_api_key: str | None = field(
        default_factory=lambda: os.environ.get("OPENROUTER_API_KEY") or None
    )
    openrouter_model: str = field(
        default_factory=lambda: os.environ.get("OPENROUTER_MODEL", "qwen/qwen3.8-27b")
    )
    # Reasoning effort for long-form synthesis: off | low | medium | high.
    llm_reasoning: str = field(
        default_factory=lambda: os.environ.get("LLM_REASONING", "low").lower()
    )
    llm_backend_pref: str = field(
        default_factory=lambda: os.environ.get("LLM_BACKEND", "auto").lower()
    )
    app_password: str | None = field(
        default_factory=lambda: os.environ.get("APP_PASSWORD") or None
    )
    app_secret: str = field(
        default_factory=lambda: os.environ.get("APP_SECRET", "dev-secret-change-me")
    )
    dormancy_days: float = field(
        default_factory=lambda: float(os.environ.get("DORMANCY_DAYS", "7"))
    )
    max_active: int = field(
        default_factory=lambda: int(os.environ.get("MAX_ACTIVE_THREADS", "2"))
    )
    seed_on_start: bool = field(
        default_factory=lambda: os.environ.get("SEED_ON_START", "1") == "1"
    )

    @property
    def journal_mode(self) -> str:
        return _default_journal_mode(self.db_path)

    @property
    def llm_backend(self) -> str | None:
        pref = self.llm_backend_pref
        if pref == "openrouter":
            return "openrouter" if self.openrouter_api_key else None
        if pref == "hf":
            return "hf" if self.hf_token else None
        if self.openrouter_api_key:
            return "openrouter"
        return "hf" if self.hf_token else None

    @property
    def llm_enabled(self) -> bool:
        return self.llm_backend is not None

    @property
    def model(self) -> str:
        return self.openrouter_model if self.llm_backend == "openrouter" else self.default_model


settings = Settings()
