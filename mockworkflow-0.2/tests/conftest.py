import sys
from pathlib import Path

import pytest

# Ensure backend is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """FastAPI TestClient with exception handlers registered.
    Lifespan is disabled to avoid startup/shutdown side-effects in unit tests."""
    from backend.app.main import app
    with TestClient(app, lifespan="off") as c:
        yield c


@pytest.fixture
def mock_settings(monkeypatch):
    """Return a patched Settings object that disables external deps."""
    from backend.config import Settings

    test_settings = Settings(
        llm_enabled=False,
        db_export_enabled=False,
        web_password=None,
        rules_autosave=False,
    )
    monkeypatch.setattr("backend.config.get_settings", lambda: test_settings)
    return test_settings


@pytest.fixture
def temp_dir(tmp_path):
    """Provide a temporary directory for file I/O tests."""
    return tmp_path


@pytest.fixture
def sample_csv(temp_dir):
    """Write a minimal CSV fixture and return its path."""
    path = temp_dir / "users.csv"
    path.write_text(
        "id,name,age\n"
        "1,Alice,30\n"
        "2,Bob,25\n"
        "3,Charlie,35\n",
        encoding="utf-8",
    )
    return str(path)
