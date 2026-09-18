from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, sourced only from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: SecretStr | None = None
    # Pin the evaluated snapshot so model behavior cannot drift during judging.
    openai_model: str = "gpt-5.4-mini-2026-03-17"
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh"] = "low"
    llm_timeout_seconds: float = Field(default=10.0, ge=1.0, le=25.0)
    llm_max_retries: int = Field(default=1, ge=0, le=2)
    llm_semantic_retries: int = Field(default=1, ge=0, le=2)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
