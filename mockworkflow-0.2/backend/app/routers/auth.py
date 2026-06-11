"""Authentication routes for login/logout and session status."""
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from backend.app.auth import SessionStore, generate_csrf_token, _now, _should_secure_cookie
from backend.config import get_settings

router = APIRouter()


def _get_store():
    from backend.app.state import get_session_store
    return get_session_store()


# ---------- Models ----------

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, description="Username")
    password: str = Field(min_length=1, description="Password")
    # CSRF token included (frontend sends via header or body)
    csrf_token: str | None = Field(None, description="CSRF token for form submission")


class LoginResponse(BaseModel):
    success: bool
    message: str
    username: str | None = None


class MeResponse(BaseModel):
    authenticated: bool
    username: str | None = None


class CsrfResponse(BaseModel):
    token: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, description="用户名（3-50字符）")
    password: str = Field(min_length=6, max_length=100, description="密码（至少6字符）")
    display_name: str | None = Field(None, description="显示名称（可选）")
    csrf_token: str | None = Field(None, description="CSRF token for form submission")


class RegisterResponse(BaseModel):
    success: bool
    message: str
    username: str | None = None


# ---------- Routes ----------

@router.post("/api/auth/login", response_model=LoginResponse, tags=["auth"])
async def login(payload: LoginRequest, request: Request):
    """Authenticate with username and password, issue a session cookie."""
    store = _get_store()
    remote_addr = request.client.host if request.client else "unknown"

    # Check lockout BEFORE password verification
    if store.is_locked_out(remote_addr):
        store._audit.login_failure(remote_addr, reason="ip_locked_out")
        return Response(
            status_code=403,
            content='{"success":false,"message":"Too many failed attempts. Try again later.","code":"account_locked","retry_after":900, "username":null}',
            media_type="application/json",
        )

    if not store.verify_user_credentials(payload.username, payload.password):
        store._record_failure(remote_addr)
        store._audit.login_failure(remote_addr, reason="invalid_password")
        return Response(
            status_code=401,
            content='{"success":false,"message":"Invalid username or password.","username":null}',
            media_type="application/json",
        )

    store._record_success(remote_addr)
    store._audit.login_success(remote_addr, payload.username)
    token = store.create_session(payload.username)
    resp = Response(
        content=f'{{"success":true,"message":"Login successful.","username":"{payload.username}"}}',
        media_type="application/json",
    )
    resp.set_cookie(
        key="mockworkflow_session",
        value=token,
        httponly=True,
        secure=_should_secure_cookie(),
        samesite="lax",
        max_age=store.TOKEN_TTL_SECONDS,
    )
    return resp


@router.post("/api/auth/logout", response_model=LoginResponse, tags=["auth"])
async def logout(request: Request):
    """Clear the current session cookie."""
    store = _get_store()
    remote_addr = request.client.host if request.client else "unknown"
    token = request.cookies.get("mockworkflow_session")
    username = None
    if token:
        valid, username = store.validate_session(token)
        if valid and username:
            store.revoke_session(token)
    store._audit.logout(remote_addr, username or "unknown")
    resp = Response(
        content='{"success":true,"message":"Logout successful.","username":null}',
        media_type="application/json",
    )
    resp.delete_cookie(key="mockworkflow_session")
    return resp


@router.get("/api/auth/me", response_model=MeResponse, tags=["auth"])
async def me(request: Request):
    """Check current authentication status and username."""
    store = _get_store()
    token = request.cookies.get("mockworkflow_session")
    valid, username = store.validate_session(token)
    return {"authenticated": valid, "username": username}


@router.get("/api/auth/csrf", response_model=CsrfResponse, tags=["auth"])
async def get_csrf_token():
    """Get a CSRF token for login/registration forms."""
    return {"token": generate_csrf_token()}


@router.post("/api/auth/register", response_model=RegisterResponse, tags=["auth"])
async def register(payload: RegisterRequest, request: Request):
    """Register a new user."""
    store = _get_store()
    remote_addr = request.client.host if request.client else "unknown"

    # 简单的验证
    if not payload.username or not payload.password:
        return Response(
            status_code=400,
            content='{"success":false,"message":"用户名和密码不能为空"}',
            media_type="application/json",
        )

    # 检查用户名是否已存在
    if store._user_db.user_exists(payload.username):
        return Response(
            status_code=409,
            content='{"success":false,"message":"用户名已存在"}',
            media_type="application/json",
        )

    # 添加用户
    display_name = payload.display_name or payload.username
    success = store._user_db.add_user(payload.username, payload.password, display_name)

    if success:
        return Response(
            status_code=201,
            content=f'{{"success":true,"message":"注册成功","username":"{payload.username}"}}',
            media_type="application/json",
        )
    else:
        return Response(
            status_code=500,
            content='{"success":false,"message":"注册失败，请稍后重试"}',
            media_type="application/json",
        )