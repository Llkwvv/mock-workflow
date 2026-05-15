"""Model pool management for automatic model selection."""

import json
from pathlib import Path
from typing import Any

from openai import OpenAI

from mockagent.config import get_settings


class ModelInfo:
    """Information about a model in the pool."""

    def __init__(
        self,
        name: str,
        enabled: bool = True,
        priority: int = 0,
        description: str | None = None,
    ):
        self.name = name
        self.enabled = enabled
        self.priority = priority
        self.description = description

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelInfo":
        return cls(
            name=data.get("name", ""),
            enabled=data.get("enabled", True),
            priority=data.get("priority", 0),
            description=data.get("description"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "priority": self.priority,
            "description": self.description,
        }


class ModelPool:
    """Model pool for managing and probing available LLM models."""

    def __init__(self, pool_file: str | Path | None = None):
        settings = get_settings()
        self.pool_file = pool_file or settings.llm_models_pool_file
        self._models: list[ModelInfo] = []
        self._loaded = False
        self._working_model: str | None = None

    def load(self) -> list[ModelInfo]:
        """Load models from the pool file."""
        if self._loaded:
            return self._models

        if not self.pool_file:
            return []

        path = Path(self.pool_file)
        if not path.exists():
            return []

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            models_data = data.get("models", [])
            self._models = [ModelInfo.from_dict(m) for m in models_data]
            self._loaded = True
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to load models pool: {e}")
            self._models = []

        return self._models

    def get_enabled_models(self) -> list[ModelInfo]:
        """Get enabled models sorted by priority."""
        self.load()
        return sorted(
            [m for m in self._models if m.enabled],
            key=lambda m: m.priority
        )

    def probe_model(
        self,
        model_name: str,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 10,
    ) -> bool:
        """Test if a model is accessible.

        Args:
            model_name: Name of the model to test
            api_key: API key for authentication
            base_url: Base URL for the API
            timeout: Timeout in seconds for the probe request

        Returns:
            True if the model is accessible, False otherwise
        """
        effective_key = api_key or "not-needed"

        try:
            client = OpenAI(
                api_key=effective_key,
                base_url=base_url,
                timeout=timeout,
            )
            # Use a minimal request to test connectivity
            client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            return True
        except Exception:
            return False

    def find_working_model(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 10,
    ) -> str | None:
        """Find the first working model from the pool.

        Args:
            api_key: API key for authentication
            base_url: Base URL for the API
            timeout: Timeout in seconds for each probe

        Returns:
            Name of the first working model, or None if no model works
        """
        # Return cached working model if available
        if self._working_model:
            return self._working_model

        models = self.get_enabled_models()
        for model in models:
            if self.probe_model(model.name, api_key, base_url, timeout):
                self._working_model = model.name
                return model.name

        return None

    def reset_cached_model(self) -> None:
        """Reset the cached working model to force re-probing."""
        self._working_model = None


def get_model_pool(pool_file: str | Path | None = None) -> ModelPool:
    """Get a ModelPool instance."""
    return ModelPool(pool_file)
