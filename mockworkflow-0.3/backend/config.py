from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Preset providers – 用户只需填 provider + api_key 即可自动推断 base_url & model
_PROVIDER_PRESETS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-v4-pro",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "llama3",
    },
}


class Settings(BaseSettings):
    app_name: str = "Mockworkflow"
    environment: str = Field(default="development")
    rules_file: str = Field(
        default_factory=lambda: str(Path(__file__).resolve().parent / "rules" / "default_rules.json")
    )
    rules_autosave: bool = Field(default=True)
    rules_min_confidence: float = Field(default=0.85, ge=0, le=1)

    # LLM 配置
    llm_enabled: bool = Field(default=False)
    llm_provider: str | None = Field(
        default=None,
        description="Preset provider: deepseek | openai | ollama. When set, base_url and model are auto-filled unless explicitly overridden."
    )
    llm_api_key: str | None = None
    llm_base_url: str | None = Field(default=None, description="OpenAI compatible API base URL, e.g., http://localhost:11434/v1 for Ollama")
    llm_model: str | None = Field(default=None, description="LLM model name (must be set via env or CLI when llm_enabled)")
    llm_timeout: int = Field(default=90, ge=1, le=300, description="LLM request timeout in seconds")
    llm_max_tokens: int = Field(default=2000, ge=100, le=8000, description="Max tokens for LLM response")
    llm_temperature: float = Field(default=0.1, ge=0, le=2, description="LLM temperature")

    @model_validator(mode="after")
    def apply_provider_preset(self) -> "Settings":
        """If llm_provider is set, force-apply its preset for base_url and model.
        Manual override should be done by leaving provider unset and filling base_url + model directly."""
        if self.llm_provider:
            preset = _PROVIDER_PRESETS.get(self.llm_provider.lower())
            if preset:
                self.llm_base_url = preset["base_url"]
                self.llm_model = preset["model"]
        return self

    # Value pool 配置 (LLM 一次生成、持久化复用)
    llm_value_pool_enabled: bool = Field(default=False, description="Generate per-field value pools via LLM and persist them")
    llm_value_pool_size: int = Field(default=50, ge=1, le=500, description="Target number of values per generated pool")

    # Model pool 配置 (自动探测可用模型)
    llm_models_pool_file: str | None = Field(
        default_factory=lambda: str(Path(__file__).resolve().parent / "rules" / "models-pool.json"),
        description="Path to models pool JSON file"
    )

    # Database export 配置 (自动建表 + 单向导出, 默认开启)
    db_export_enabled: bool = Field(
        default=True,
        description="Master switch for auto table creation and data export to the database (MySQL only)",
    )
    mysql_url: str | None = Field(
        default=None,
        description="MySQL/MariaDB connection string, e.g., mysql+pymysql://user:pass@host:3306/db",
    )

    # PII anonymization
    pii_enabled: bool = Field(default=False, description="Enable PII anonymization for generated data")

    # Web interface authentication
    web_password: str | None = Field(
        default=None,
        description="Password for web interface. None = no auth required.",
    )

    model_config = SettingsConfigDict(env_file=".env", env_prefix="MOCKWORKFLOW_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
