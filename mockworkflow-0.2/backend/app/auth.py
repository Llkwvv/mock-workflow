"""Authentication module for backend API.

Sessions are stateful on the server side so that the cookie only carries an
opaque random token – never the raw password.

Security enhancements (Phase 2):
  - bcrypt password hashing with username support
  - IP-based login failure lockout
  - login audit logging
  - CSRF token generation for forms
"""

import json
import logging
import os
import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Tuple

import bcrypt
from fastapi import Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Audit logger
# ---------------------------------------------------------------------------
class AuditLogger:
    """Append-only audit log for authentication events."""

    def __init__(self, path: Optional[Path] = None):
        self._path = path
        if path and not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, event: str, **kwargs):
        if not self._path:
            return
        ts = _now().isoformat()
        line = json.dumps({"ts": ts, "event": event, **kwargs}) + "\n"
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            logger.exception("Failed to write audit log")

    def login_success(self, remote_addr: str, user_label: str = "unknown"):
        self._append("login_success", remote_addr=remote_addr, user=user_label)

    def login_failure(self, remote_addr: str, reason: str = "invalid_password"):
        self._append("login_failure", remote_addr=remote_addr, reason=reason)

    def logout(self, remote_addr: str, user_label: str = "unknown"):
        self._append("logout", remote_addr=remote_addr, user=user_label)

    def session_revoked(self, remote_addr: str, user_label: str = "unknown"):
        self._append("session_revoked", remote_addr=remote_addr, user=user_label)

    def task_generated(self, user_label: str, sample: str, table: str, rows: int,
                       task_id: str = "", output: str = ""):
        """Log a mock-data generation task event."""
        self._append(
            "task_generated",
            user=user_label,
            sample=sample,
            table=table,
            rows=rows,
            task_id=task_id,
            output=output,
        )


# ---------------------------------------------------------------------------
# CSRF helper
# ---------------------------------------------------------------------------
def generate_csrf_token() -> str:
    """Generate a URL-safe CSRF token for forms."""
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# User database with bcrypt password hashing
# ---------------------------------------------------------------------------
class UserDB:
    """Simple user database with bcrypt password hashing and JSON persistence."""

    def __init__(self, persist_path: Optional[Path] = None):
        # 用户数据库: {username: {"password_hash": bytes, "display_name": str}}
        self._users: Dict[str, dict] = {}
        self._persist_path = persist_path
        if persist_path:
            self._load()

    def add_user(self, username: str, password: str, display_name: str = "") -> bool:
        """添加新用户（密码自动哈希）"""
        if username in self._users:
            return False
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=10))
        self._users[username] = {
            "password_hash": password_hash,
            "display_name": display_name or username,
        }
        self._save()
        return True

    def verify_user(self, username: str, password: str) -> bool:
        """验证用户名和密码"""
        user = self._users.get(username)
        if not user:
            return False
        try:
            return bcrypt.checkpw(password.encode("utf-8"), user["password_hash"])
        except Exception:
            return False

    def get_display_name(self, username: str) -> str:
        """获取用户显示名称"""
        return self._users.get(username, {}).get("display_name", username)

    def user_exists(self, username: str) -> bool:
        """检查用户是否存在"""
        return username in self._users

    def _load(self) -> None:
        """从文件加载用户数据"""
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            for username, user_data in data.get("users", {}).items():
                # password_hash 存储为 base64 编码的字符串
                password_hash_bytes = None
                if isinstance(user_data.get("password_hash"), str):
                    import base64
                    password_hash_bytes = base64.b64decode(user_data["password_hash"])
                elif isinstance(user_data.get("password_hash"), bytes):
                    password_hash_bytes = user_data["password_hash"]

                if password_hash_bytes:
                    self._users[username] = {
                        "password_hash": password_hash_bytes,
                        "display_name": user_data.get("display_name", username),
                    }
        except Exception as e:
            logger.warning(f"Failed to load user database: {e}")

    def _save(self) -> None:
        """保存用户数据到文件"""
        if not self._persist_path:
            return
        try:
            import base64
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "users": {
                    username: {
                        "password_hash": base64.b64encode(user_data["password_hash"]).decode("utf-8"),
                        "display_name": user_data["display_name"],
                    }
                    for username, user_data in self._users.items()
                }
            }
            self._persist_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to save user database: {e}")


# ---------------------------------------------------------------------------
# Session store with lockout
# ---------------------------------------------------------------------------
class SessionStore:
    """In-memory session store with optional JSON persistence.

    Each session token maps to a lightweight record with an expiry time.
    Supports bcrypt-hashed passwords and IP-based login lockout.
    """

    TOKEN_TTL_SECONDS: int = 86400 * 7  # 7 days
    MAX_LOGIN_FAILURES: int = 5          # lockout after N consecutive failures
    LOCKOUT_DURATION_SECONDS: int = 900  # 15 minutes

    def __init__(self, user_db: UserDB, persist_path: Optional[Path] = None,
                 audit_path: Optional[Path] = None):
        self._user_db = user_db
        self._sessions: dict[str, Tuple[str, datetime]] = {}  # token -> (username, created_at)
        self._persist_path = persist_path
        self._audit = AuditLogger(audit_path)

        # IP -> {"count": int, "locked_until": datetime | None}
        self._failure_tracker: dict[str, dict] = defaultdict(
            lambda: {"count": 0, "locked_until": None}
        )

        if persist_path:
            self._load()

    # -- lockout logic --

    def is_locked_out(self, remote_addr: str) -> bool:
        entry = self._failure_tracker[remote_addr]
        locked_until = entry["locked_until"]
        if locked_until and _now() < locked_until:
            return True
        # Reset counter if lockout expired
        if locked_until and _now() >= locked_until:
            entry["count"] = 0
            entry["locked_until"] = None
        return False

    def _record_failure(self, remote_addr: str):
        entry = self._failure_tracker[remote_addr]
        entry["count"] += 1
        if entry["count"] >= self.MAX_LOGIN_FAILURES:
            entry["locked_until"] = _now() + timedelta(
                seconds=self.LOCKOUT_DURATION_SECONDS
            )
            logger.warning(
                "IP %s locked out after %d failed login attempts",
                remote_addr, entry["count"],
            )

    def _record_success(self, remote_addr: str):
        """Reset failure counter on successful login."""
        entry = self._failure_tracker[remote_addr]
        entry["count"] = 0
        entry["locked_until"] = None

    # -- public API --

    def create_session(self, username: str) -> str:
        """Create a new random session token and persist it."""
        token = secrets.token_urlsafe(32)
        self._sessions[token] = (username, _now())
        self._save()
        return token

    def validate_session(self, token: str | None) -> Tuple[bool, Optional[str]]:
        """Check whether a token is valid and not expired.
        Returns: (is_valid, username)
        """
        if not token:
            return False, None
        entry = self._sessions.get(token)
        if not entry:
            # Token not in memory – maybe another instance created it.
            # Try reloading from disk before giving up.
            self._load()
            entry = self._sessions.get(token)
            if not entry:
                return False, None
        username, created = entry
        if (_now() - created).total_seconds() > self.TOKEN_TTL_SECONDS:
            self._sessions.pop(token, None)
            self._save()
            return False, None
        return True, username

    def revoke_session(self, token: str) -> None:
        self._sessions.pop(token, None)
        self._save()

    def verify_user_credentials(self, username: str, password: str) -> bool:
        """Verify username and password."""
        return self._user_db.verify_user(username, password)

    def get_display_name(self, username: str) -> str:
        """Get user display name."""
        return self._user_db.get_display_name(username)

    # -- persistence --

    def _load(self) -> None:
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            for token, (username, created_iso) in data.get("sessions", {}).items():
                try:
                    self._sessions[token] = (username, datetime.fromisoformat(created_iso))
                except Exception:
                    continue
        except Exception:
            pass

    def _save(self) -> None:
        if not self._persist_path:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "sessions": {
                    token: [username, created.isoformat()]
                    for token, (username, created) in self._sessions.items()
                }
            }
            self._persist_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to check authentication for API and frontend."""

    EXEMPT_PATHS = (
        "/login", "/login.html", "/api/health", "/api/ws", "/output",
        "/api/auth/login", "/api/auth/logout", "/api/auth/me", "/api/auth/csrf", "/api/auth/register",
        "/", "/index.html", "/static",
    )

    def __init__(self, app, user_db: UserDB = None, password: str = None,
                 persist_path: Optional[Path] = None,
                 audit_path: Optional[Path] = None):
        super().__init__(app)
        from backend.app.state import get_session_store, get_user_db
        # 支持旧的 password 参数（向后兼容）
        if user_db is None:
            user_db = get_user_db()
            # 如果提供了密码且用户数据库为空，添加默认用户
            if password and not user_db._users:
                user_db.add_user("admin", password, "Administrator")
        self.store = get_session_store(user_db, persist_path, audit_path)

    async def dispatch(self, request: Request, call_next):
        # Skip authentication for exempt paths
        path = request.url.path
        for exempt in self.EXEMPT_PATHS:
            if path == exempt:
                return await call_next(request)
            if exempt != "/" and path.startswith(exempt + "/"):
                return await call_next(request)

        remote_addr = request.client.host if request.client else "unknown"

        # 1. Check opaque session cookie
        session_token = request.cookies.get("mockworkflow_session")
        if session_token:
            valid, username = self.store.validate_session(session_token)
            if valid:
                return await call_next(request)

        # 2. Check API header (X-Password or Authorization: Bearer)
        provided = _extract_password(request)
        if provided:
            # Check lockout before attempting verification
            if self.store.is_locked_out(remote_addr):
                self.store._audit.login_failure(remote_addr, reason="ip_locked_out")
                if path.startswith("/api/"):
                    return JSONResponse(
                        status_code=403,
                        content={
                            "code": "account_locked",
                            "message": "Too many failed attempts. Try again later.",
                            "retry_after": self.store.LOCKOUT_DURATION_SECONDS,
                        },
                    )
                return RedirectResponse(url="/login.html", status_code=307)

            # Extract username from header if provided
            username = request.headers.get("X-Username", "")
            # For backward compat, try password-only auth (legacy single-user mode)
            # This is a fallback - new code should use username+password
            if username:
                # Username + password authentication
                if self.store.verify_user_credentials(username, provided):
                    self.store._record_success(remote_addr)
                    self.store._audit.login_success(remote_addr, username)
                    new_token = self.store.create_session(username)
                    response = await call_next(request)
                    response.set_cookie(
                        key="mockworkflow_session",
                        value=new_token,
                        httponly=True,
                        secure=_should_secure_cookie(),
                        samesite="lax",
                        max_age=self.store.TOKEN_TTL_SECONDS,
                    )
                    return response
                else:
                    self.store._record_failure(remote_addr)
                    self.store._audit.login_failure(remote_addr, reason="invalid_password")
            else:
                # Legacy: password-only authentication (check against any user)
                # Try to verify against all users (inefficient but backward compatible)
                authenticated = False
                for uname in self.store._user_db._users:
                    if self.store.verify_user_credentials(uname, provided):
                        authenticated = True
                        username = uname
                        break
                if authenticated:
                    self.store._record_success(remote_addr)
                    self.store._audit.login_success(remote_addr, username)
                    new_token = self.store.create_session(username)
                    response = await call_next(request)
                    response.set_cookie(
                        key="mockworkflow_session",
                        value=new_token,
                        httponly=True,
                        secure=_should_secure_cookie(),
                        samesite="lax",
                        max_age=self.store.TOKEN_TTL_SECONDS,
                    )
                    return response
                else:
                    self.store._record_failure(remote_addr)
                    self.store._audit.login_failure(remote_addr, reason="invalid_password")

        # 3. Not authenticated
        if path.startswith("/api/"):
            return JSONResponse(
                status_code=401,
                content={"code": "unauthorized", "message": "Authentication required.", "detail": {}},
            )

        # HTML page: redirect to login
        return RedirectResponse(url="/login.html", status_code=307)


def _should_secure_cookie() -> bool:
    """Return True if we should set the Secure flag on cookies."""
    return os.environ.get("MOCKWORKFLOW_SECURE_COOKIES", "0") == "1"


def _extract_password(request: Request) -> Optional[str]:
    """Extract raw password from request headers (for API calls)."""
    provided = request.headers.get("X-Password") or ""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        provided = auth_header[7:]
    return provided if provided else None


def get_optional_password(request: Request) -> Optional[str]:
    """Extract password from request headers (for API calls)."""
    return _extract_password(request)

def get_optional_password(request: Request) -> Optional[str]:
    """Extract password from request headers (for API calls)."""
    return _extract_password(request)


def get_current_username(request: Request) -> str:
    """Extract the current authenticated username from session cookie.

    Returns "anonymous" if no valid session is present.
    """
    token = request.cookies.get("mockworkflow_session")
    if not token:
        return "anonymous"
    from backend.app.state import get_session_store
    store = get_session_store()
    if not store:
        return "anonymous"
    valid, username = store.validate_session(token)
    return username if (valid and username) else "anonymous"


def get_audit_logger() -> "AuditLogger":
    """Return the singleton AuditLogger from the session store."""
    from backend.app.state import get_session_store
    store = get_session_store()
    return store._audit if store else AuditLogger()
