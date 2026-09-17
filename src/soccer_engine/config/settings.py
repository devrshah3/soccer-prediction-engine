"""Validated application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings with safe local defaults."""

    model_config = SettingsConfigDict(env_prefix="SOCCER_ENGINE_", env_file=".env", extra="ignore")

    env: str = "development"
    data_dir: Path = Path("data")
    model_dir: Path = Path("models")
    log_level: str = "INFO"
    random_seed: int = 42
    request_timeout_seconds: float = Field(default=30.0, gt=0)
    max_requests_per_second: float = Field(default=2.0, gt=0)

    @property
    def database_path(self) -> Path:
        return self.data_dir / "soccer_engine.duckdb"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide validated settings object."""

    return Settings()
