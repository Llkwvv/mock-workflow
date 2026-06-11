"""Tests for backend/config.py caching behavior."""
from backend.config import get_settings


def test_get_settings_returns_same_instance():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
