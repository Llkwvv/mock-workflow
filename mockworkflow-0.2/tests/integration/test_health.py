"""Basic health-check integration test.

NOTE: Skipped – TestClient hangs when imported inside pytest (see test_api_errors.py)."""

import pytest

pytestmark = pytest.mark.skip(reason="TestClient hang under pytest – needs investigation")


def test_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "timestamp" in data
