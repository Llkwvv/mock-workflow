"""Shared application state to avoid circular imports between main and routers."""
from pathlib import Path

from backend.app.executor import TaskExecutor
from backend.app.task_manager import TaskManager
from backend.app.scheduler import ScheduleManager, Scheduler

BASE_DIR = Path(__file__).resolve().parent
project_root = BASE_DIR.parent.parent  # 项目根目录: mockworkflow-0.2
FRONTEND_DIR = project_root / "frontend"
OUTPUT_DIR = project_root / "output"
SAMPLES_DIR = project_root / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)


class ConnectionManager:
    def __init__(self):
        self.active = []

    async def connect(self, ws):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict):
        disconnected = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)


ws_manager = ConnectionManager()
task_manager = TaskManager(broadcast_fn=ws_manager.broadcast)
schedule_manager = ScheduleManager(
    task_manager=task_manager,
    broadcast_fn=ws_manager.broadcast
)
executor = TaskExecutor(max_concurrent=4)
scheduler = Scheduler(schedule_manager, task_manager, executor=executor)

# Lazy-initialized user database and session store (shared between middleware and auth routes)
_user_db = None
_session_store = None


def get_user_db() -> "UserDB":
    """Return the singleton UserDB, creating it on first call."""
    global _user_db
    if _user_db is None:
        from backend.app.auth import UserDB
        _user_db = UserDB(persist_path=project_root / ".users.json")
        # 从环境变量或配置文件初始化默认用户（仅在用户不存在时）
        from backend.config import get_settings
        settings = get_settings()
        if settings.web_password and not _user_db.user_exists("admin"):
            # 向后兼容：使用密码作为默认用户"admin"的密码
            _user_db.add_user("admin", settings.web_password, "Administrator")
        # 可以在这里添加更多用户或从数据库加载
    return _user_db


def get_session_store(user_db=None, persist_path=None, audit_path=None) -> "SessionStore":
    """Return the singleton SessionStore, creating it on first call."""
    global _session_store
    if _session_store is None:
        from backend.app.auth import SessionStore
        if user_db is None:
            user_db = get_user_db()
        _session_store = SessionStore(
            user_db=user_db,
            persist_path=persist_path or (project_root / ".sessions.json"),
            audit_path=audit_path or (project_root / ".audit.log")
        )
    return _session_store


# Lazy-initialized vector store (heavy model load deferred until first use)
_vector_store = None


def get_vector_store():
    """Return the singleton ChromaVectorStore, creating it on first call."""
    global _vector_store
    if _vector_store is None:
        from backend.config import get_settings
        from backend.rag.chroma_store import ChromaVectorStore
        from backend.rag.embedding import EmbeddingService
        settings = get_settings()
        embedding = EmbeddingService(
            model_name=settings.embedding_model,
            project_root=project_root,
        )
        _vector_store = ChromaVectorStore(
            persist_dir=settings.chroma_persist_dir,
            embedding_service=embedding,
        )
    return _vector_store
