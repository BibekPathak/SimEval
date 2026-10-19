"""Application settings.

Settings are loaded from environment variables (prefixed ``SIMEVAL_``) with
sensible local defaults so the app runs with zero configuration. Nothing here
requires cloud credentials.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SIMEVAL_", env_file=".env", extra="ignore")

    app_name: str = "SimEval"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False

    # Database. SQLite by default; set a PostgreSQL URL for production.
    database_url: str = "sqlite:///./simeval.db"

    # Artifact storage root (relative to the process working directory).
    artifact_root: str = "artifacts"

    # Worker.
    max_concurrent_episodes: int = 1
    max_concurrent_experiments: int = 1
    episode_timeout_s: float = 120.0

    # Pagination defaults.
    default_page_size: int = 50
    max_page_size: int = 500

    @property
    def artifact_path(self) -> Path:
        return Path(self.artifact_root)


@lru_cache
def get_settings() -> Settings:
    return Settings()
