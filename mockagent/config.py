from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MockAgent"
    environment: str = Field(default="development")
    rules_file: str = Field(
        default_factory=lambda: str(Path(__file__).resolve().parent / "rules" / "default_rules.json")
    )
    rules_autosave: bool = Field(default=True)
    rules_min_confidence: float = Field(default=0.85, ge=0, le=1)

    # LLM 配置
    llm_enabled: bool = Field(default=False)
    llm_api_key: str | None = None
    llm_base_url: str | None = Field(default=None, description="OpenAI compatible API base URL, e.g., http://localhost:11434/v1 for Ollama")
    llm_model: str | None = Field(default=None, description="LLM model name (must be set via env or CLI when llm_enabled)")
    llm_timeout: int = Field(default=90, ge=1, le=300, description="LLM request timeout in seconds")
    llm_max_tokens: int = Field(default=2000, ge=100, le=8000, description="Max tokens for LLM response")
    llm_temperature: float = Field(default=0.1, ge=0, le=2, description="LLM temperature")

    # Value pool 配置 (LLM 一次生成、持久化复用)
    llm_value_pool_enabled: bool = Field(default=False, description="Generate per-field value pools via LLM and persist them")
    llm_value_pool_size: int = Field(default=50, ge=1, le=500, description="Target number of values per generated pool")

    model_config = SettingsConfigDict(env_file=".env", env_prefix="MOCKAGENT_", extra="ignore")


def get_settings() -> Settings:
    return Settings()
