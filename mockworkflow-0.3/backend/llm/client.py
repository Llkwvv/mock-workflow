"""Unified LLM client factory for the project."""
from __future__ import annotations

from openai import OpenAI

from backend.config import Settings, get_settings


def get_client(
    settings: Settings | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout: int | None = None,
) -> OpenAI:
    """Build an OpenAI-compatible client from settings with optional overrides.

    Args:
        settings: Base settings. If None, uses ``get_settings()``.
        api_key: Override API key.
        base_url: Override base URL.
        timeout: Override timeout in seconds.
    """
    if settings is None:
        settings = get_settings()

    effective_key = api_key or settings.llm_api_key or "not-needed"
    effective_base = base_url or settings.llm_base_url
    effective_timeout = timeout or settings.llm_timeout

    if not effective_base:
        raise ValueError("llm_base_url must be provided")

    return OpenAI(
        api_key=effective_key,
        base_url=effective_base,
        timeout=effective_timeout,
    )
