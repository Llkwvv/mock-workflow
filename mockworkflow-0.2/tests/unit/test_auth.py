"""Tests for auth security model (session tokens, username+password, bcrypt hashing)."""

from pathlib import Path

import pytest

from backend.app.auth import SessionStore, AuthMiddleware, UserDB


@pytest.fixture
def user_db():
    """创建一个测试用的用户数据库。"""
    db = UserDB()
    db.add_user("testuser", "secret123", "Test User")
    db.add_user("admin", "adminpass", "Administrator")
    return db


@pytest.fixture
def store(tmp_path, user_db):
    """创建一个带有用户数据库的SessionStore。"""
    return SessionStore(user_db=user_db, persist_path=tmp_path / "sessions.json")


class DummyClient:
    def __init__(self, host="testclient"):
        self.host = host


class DummyRequest:
    def __init__(self, cookies=None, headers=None, client_host="testclient"):
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.url = type("URL", (), {"path": "/api/tasks"})()
        self.client = DummyClient(host=client_host)


# ---------- UserDB 测试 ----------

def test_user_db_add_and_verify():
    """测试用户数据库的添加和验证。"""
    db = UserDB()
    db.add_user("alice", "password123", "Alice")
    assert db.user_exists("alice") is True
    assert db.user_exists("bob") is False
    assert db.verify_user("alice", "password123") is True
    assert db.verify_user("alice", "wrong") is False
    assert db.get_display_name("alice") == "Alice"


def test_user_db_duplicate():
    """测试重复用户不能添加。"""
    db = UserDB()
    assert db.add_user("alice", "pass", "Alice") is True
    assert db.add_user("alice", "pass2", "Alice2") is False


# ---------- SessionStore 测试 ----------

def test_create_and_validate_session(store):
    """测试会话创建和验证。"""
    token = store.create_session("testuser")
    assert token
    valid, username = store.validate_session(token)
    assert valid is True
    assert username == "testuser"
    assert store.validate_session("bad-token") == (False, None)
    assert store.validate_session(None) == (False, None)


def test_session_expiry(store, monkeypatch):
    """测试会话过期。"""
    token = store.create_session("testuser")
    # Mock time to be 8 days later
    import datetime
    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=8)
    monkeypatch.setattr("backend.app.auth._now", lambda: future)
    valid, username = store.validate_session(token)
    assert valid is False


def test_persistence(tmp_path, user_db):
    """测试会话持久化。"""
    store1 = SessionStore(user_db=user_db, persist_path=tmp_path / "sessions.json")
    token = store1.create_session("testuser")
    # Re-create store pointing at same file
    store2 = SessionStore(user_db=user_db, persist_path=tmp_path / "sessions.json")
    valid, username = store2.validate_session(token)
    assert valid is True
    assert username == "testuser"


def test_verify_user_credentials(store):
    """测试用户凭证验证。"""
    assert store.verify_user_credentials("testuser", "secret123") is True
    assert store.verify_user_credentials("testuser", "wrong") is False
    assert store.verify_user_credentials("nonexistent", "pass") is False


# ---------- 暴力破解防护测试 ----------

def test_login_lockout(store):
    """测试多次失败登录后的IP锁定。"""
    # 模拟多次失败
    for i in range(5):
        store._record_failure("192.168.1.100")
    # 5次失败后应被锁定（MAX_LOGIN_FAILURES=5）
    assert store.is_locked_out("192.168.1.100") is True
    # 不同IP不受影响
    assert store.is_locked_out("10.0.0.1") is False


def test_lockout_reset_after_success(store):
    """测试成功登录后重置失败计数器。"""
    store._record_failure("192.168.1.50")
    store._record_failure("192.168.1.50")
    assert store._failure_tracker["192.168.1.50"]["count"] == 2
    store._record_success("192.168.1.50")
    assert store._failure_tracker["192.168.1.50"]["count"] == 0
    assert store._failure_tracker["192.168.1.50"]["locked_until"] is None


# ---------- 中间件测试 ----------

@pytest.mark.asyncio
async def test_middleware_allows_exempt_path():
    """测试中间件允许豁免路径。"""
    calls = []
    async def call_next(req):
        calls.append(1)
        return "ok"
    mw = AuthMiddleware(lambda app: app, password="secret123")
    req = DummyRequest(headers={})
    req.url = type("URL", (), {"path": "/api/health"})()
    resp = await mw.dispatch(req, call_next)
    assert calls == [1]


@pytest.mark.asyncio
async def test_middleware_redirects_unauthorized_html():
    """测试中间件重定向未认证的HTML请求到登录页。"""
    async def call_next(req):
        return "ok"
    mw = AuthMiddleware(lambda app: app, password="secret123")
    req = DummyRequest(headers={})
    req.url = type("URL", (), {"path": "/dashboard"})()
    resp = await mw.dispatch(req, call_next)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/login.html"


@pytest.mark.asyncio
async def test_middleware_api_unauthorized_raises():
    """测试中间件对未认证的API请求返回401。"""
    async def call_next(req):
        return "ok"
    mw = AuthMiddleware(lambda app: app, password="secret123")
    mw.store._sessions.clear()  # 确保干净的session状态
    req = DummyRequest(headers={})
    req.url = type("URL", (), {"path": "/api/tasks"})()
    resp = await mw.dispatch(req, call_next)
    # 现在返回JSONResponse 401，而不是抛出UnauthorizedError
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_middleware_header_auth_sets_cookie():
    """测试通过Header认证成功后会话创建。"""
    calls = []
    async def call_next(req):
        calls.append(1)
        return type("Resp", (), {"status_code": 200, "headers": {}, "set_cookie": lambda *a, **k: None})()
    # 创建独立SessionStore避免与其他测试共享状态
    user_db = UserDB()
    user_db.add_user("testuser", "secret123")
    store = SessionStore(user_db=user_db, persist_path=Path("/tmp/test_sessions.json"))
    store._sessions.clear()
    mw = AuthMiddleware(lambda app: app, user_db=user_db)
    mw.store = store  # 替换为干净的store
    req = DummyRequest(headers={"X-Password": "secret123", "X-Username": "testuser"})
    resp = await mw.dispatch(req, call_next)
    assert resp.status_code == 200
    # The response object should carry a Set-Cookie for the new session token
    assert len(mw.store._sessions) == 1