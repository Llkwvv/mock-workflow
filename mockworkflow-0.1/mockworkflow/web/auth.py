"""Authentication module for web interface."""
import hashlib
import hmac
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware


def verify_password(password: str, provided: str) -> bool:
    """Verify password using HMAC comparison to prevent timing attacks."""
    return hmac.compare_digest(password, provided)


def generate_session_token() -> str:
    """Generate a secure session token."""
    return secrets.token_urlsafe(32)


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to check authentication for web interface."""

    EXEMPT_PATHS = ("/login", "/health", "/static", "/output")

    def __init__(self, app, password: str):
        super().__init__(app)
        self.password = password

    async def dispatch(self, request: Request, call_next):
        # Skip authentication for exempt paths
        for exempt in self.EXEMPT_PATHS:
            if request.url.path.startswith(exempt):
                return await call_next(request)

        # Check session cookie
        session = request.cookies.get("mockworkflow_session")
        if session and verify_password(self.password, session):
            return await call_next(request)

        # Check API header (X-Password or Authorization: Bearer)
        provided = request.headers.get("X-Password") or ""
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            provided = auth_header[7:]
        if provided and verify_password(self.password, provided):
            return await call_next(request)

        # Not authenticated: API returns 401, page redirects to login
        if request.url.path.startswith("/api/") or request.url.path.startswith("/ws/"):
            raise HTTPException(status_code=401, detail="Unauthorized")

        # HTML page: redirect to login
        response = Response(status_code=307, headers={"Location": "/login"})
        print(f"Redirecting to login: {response.status_code} {response.headers['Location']}")
        return response


def get_optional_password(request: Request) -> Optional[str]:
    """Extract password from request headers (for API calls)."""
    provided = request.headers.get("X-Password") or ""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        provided = auth_header[7:]
    return provided if provided else None