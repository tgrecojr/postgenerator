"""Application settings, loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MODEL = "claude-opus-5"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_prefix="POSTGEN_", extra="ignore"
    )

    # Paths
    data_dir: Path = Field(default=Path("data"))

    # Anthropic credentials (read from .env; SDK resolution chain is the fallback)
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    # Models (per-step override)
    model: str = DEFAULT_MODEL
    model_topics: str | None = None
    model_research: str | None = None
    model_writer: str | None = None
    model_evaluator: str | None = None
    model_voice: str | None = None
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    enable_fallbacks: bool = True

    # Research
    research_provider: Literal["anthropic", "tavily"] = "anthropic"
    research_max_searches: int = 8
    tavily_api_key: str | None = Field(default=None, alias="TAVILY_API_KEY")

    # Pipeline behaviour
    max_revisions: int = 2
    pass_threshold: float = 7.5
    topic_cooldown_days: int = 60
    exemplar_count: int = 4
    recent_feedback_count: int = 8

    # Web UI. allowed_hosts is a comma-separated Host-header allowlist ("*" disables it);
    # add your Tailscale / reverse-proxy hostname when exposing the UI beyond localhost.
    host: str = "127.0.0.1"
    port: int = 8790
    allowed_hosts: str = "localhost,127.0.0.1"

    @property
    def allowed_host_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    def model_for(self, step: str) -> str:
        override: str | None = getattr(self, f"model_{step}", None)
        return override or self.model

    @property
    def profile_path(self) -> Path:
        return self.data_dir / "profile.yaml"

    @property
    def topics_path(self) -> Path:
        return self.data_dir / "topics.yaml"

    @property
    def corpus_dir(self) -> Path:
        return self.data_dir / "corpus"

    @property
    def voice_profile_path(self) -> Path:
        return self.data_dir / "voice_profile.md"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "postgen.db"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
