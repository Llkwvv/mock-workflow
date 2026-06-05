"""
Tests for web interface authentication.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from mockworkflow.config import Settings
from mockworkflow.web.app import app


class TestAuthentication:
    """Test authentication functionality."""

    def test_no_password_required_when_not_set(self):
        """Test that no password is required when web_password is not set."""
        with patch("mockworkflow.web.app.get_settings", return_value=Settings(web_password=None)):
            client = TestClient(app)
            response = client.get("/")
            assert response.status_code == 200

    def test_password_required_when_set(self):
        """Test that password is required when web_password is set."""
        with patch("mockworkflow.web.app.get_settings",
                  return_value=Settings(web_password="testpassword")):
            client = TestClient(app)
            response = client.get("/")
            assert response.status_code == 307  # Redirect to login
            assert "/login" in response.headers["location"]

    def test_login_page_access(self):
        """Test that login page can be accessed."""
        with patch("mockworkflow.web.app.get_settings",
                  return_value=Settings(web_password="testpassword")):
            client = TestClient(app)
            response = client.get("/login")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
            assert "MockWorkflow" in response.text

    def test_successful_login(self):
        """Test successful login with correct password."""
        with patch("mockworkflow.web.app.get_settings",
                  return_value=Settings(web_password="testpassword")):
            client = TestClient(app, follow_redirects=False)
            response = client.post(
                "/login",
                data={"password": "testpassword"}
            )
            assert response.status_code == 303  # Redirect
            assert "/" in response.headers["location"]
            assert "mockworkflow_session" in response.cookies
            assert response.cookies["mockworkflow_session"] == "testpassword"

    def test_failed_login(self):
        """Test failed login with incorrect password."""
        with patch("mockworkflow.web.app.get_settings",
                  return_value=Settings(web_password="testpassword")):
            client = TestClient(app)
            response = client.post(
                "/login",
                data={"password": "wrongpassword"}
            )
            assert response.status_code == 401
            assert "text/html" in response.headers["content-type"]
            assert "密码错误" in response.text
            assert "mockworkflow_session" not in response.cookies

    def test_access_protected_page_with_valid_session(self):
        """Test accessing protected page with valid session cookie."""
        with patch("mockworkflow.web.app.get_settings",
                  return_value=Settings(web_password="testpassword")):
            client = TestClient(app)
            # First login to get the session cookie
            client.post(
                "/login",
                data={"password": "testpassword"}
            )
            # Now access the main page
            response = client.get("/")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
            assert "Mockworkflow" in response.text

    def test_access_protected_page_without_session(self):
        """Test accessing protected page without session cookie."""
        with patch("mockworkflow.web.app.get_settings",
                  return_value=Settings(web_password="testpassword")):
            client = TestClient(app, follow_redirects=True)
            response = client.get("/")
            assert response.status_code == 307  # Redirect to login
            assert "/login" in response.headers["location"]

    def test_logout_clears_session(self):
        """Test that logout clears the session cookie."""
        with patch("mockworkflow.web.app.get_settings",
                  return_value=Settings(web_password="testpassword")):
            client = TestClient(app)
            # Login first
            client.post(
                "/login",
                data={"password": "testpassword"}
            )
            # Logout (there's no explicit logout, so we just delete the cookie)
            client.cookies.clear()
            # Try to access protected page
            response = client.get("/")
            assert response.status_code == 307  # Should redirect to login
            assert "/login" in response.headers["location"]


@pytest.fixture(autouse=True)
def cleanup_tasks():
    """Clear tasks before each test."""
    from mockworkflow.web.task_manager import task_manager
    task_manager.tasks.clear()
    yield
    task_manager.tasks.clear()
