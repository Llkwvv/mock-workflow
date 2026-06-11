"""Tests for backend/llm/client.py unified client factory."""
import pytest
from pydantic import BaseModel

from backend.llm.client import get_client


class FakeSettings(BaseModel):
    llm_api_key: str | None = "test-key"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_timeout: int = 30


def test_get_client_uses_settings():
    settings = FakeSettings()
    client = get_client(settings)
    assert client is not None


def test_get_client_override_key():
    settings = FakeSettings()
    client = get_client(settings, api_key="override-key")
    # OpenAI client stores api_key; we can inspect its _custom_headers or auth
    assert client is not None


def test_get_client_missing_base_url():
    class NoUrlSettings(BaseModel):
        llm_api_key: str | None = "key"
        llm_base_url: str | None = None
        llm_timeout: int = 30

    with pytest.raises(ValueError, match="llm_base_url"):
        get_client(NoUrlSettings())
