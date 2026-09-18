from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, sourced only from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4.1-mini"
    llm_timeout_seconds: float = Field(default=10.0, ge=1.0, le=25.0)
    llm_max_retries: int = Field(default=1, ge=0, le=2)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
