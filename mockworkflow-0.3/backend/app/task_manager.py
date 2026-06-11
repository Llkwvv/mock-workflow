"""Task state management for backend with SQLite persistence."""
import asyncio
import json
import sqlite3
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskInfo(BaseModel):
    id: str
    sample_filename: str
    table_name: str
    rows: int
    enable_db_export: bool = False
    status: TaskStatus
    progress: int = Field(default=0, ge=0, le=100)
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_preview: Optional[dict] = None
    result_full: Optional[dict] = None
    schema_mismatch: bool = False
    retryable: bool = False


class TaskManager:
    """In-memory task manager backed by SQLite."""

    _TASKS_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            sample_filename TEXT NOT NULL,
            table_name TEXT NOT NULL,
            rows INTEGER NOT NULL,
            enable_db_export INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            result_preview TEXT,
            result_full TEXT,
            schema_mismatch INTEGER NOT NULL DEFAULT 0,
            retryable INTEGER NOT NULL DEFAULT 0
        )
    """

    def __init__(self, storage_path: str | Path | None = None, broadcast_fn=None):
        self.tasks: dict[str, TaskInfo] = {}
        self._lock = asyncio.Lock()
        self._broadcast_fn = broadcast_fn
        if storage_path is None:
            storage_path = Path(__file__).resolve().parent / "mockworkflow.db"
        self._db_path = Path(storage_path)
        self._init_db()
        self._migrate_from_json()
        self._load_tasks()

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.execute(self._TASKS_TABLE_SQL)
        conn.commit()
        conn.close()

    def _migrate_from_json(self) -> None:
        """One-time migration from legacy tasks.json to SQLite."""
        json_path = self._db_path.with_suffix(".json")
        if not json_path.exists():
            return
        # Skip if DB already contains data
        if self._db_path.exists():
            try:
                conn = sqlite3.connect(str(self._db_path))
                cursor = conn.execute("SELECT COUNT(*) FROM tasks")
                count = cursor.fetchone()[0]
                conn.close()
                if count > 0:
                    return
            except Exception:
                pass
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "tasks" in data:
                for task_data in data["tasks"]:
                    try:
                        task = TaskInfo.model_validate(task_data)
                        self._save_task(task)
                    except Exception:
                        continue
        except Exception:
            pass

    def _load_tasks(self) -> None:
        if not self._db_path.exists():
            return
        try:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC")
            for row in cursor.fetchall():
                try:
                    task = self._row_to_task(row)
                    self.tasks[task.id] = task
                except Exception:
                    continue
            conn.close()
        except Exception:
            pass

    def _save_task(self, task: TaskInfo) -> None:
        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute(
                """
                INSERT OR REPLACE INTO tasks (
                    id, sample_filename, table_name, rows, enable_db_export,
                    status, progress, error_message, created_at, started_at,
                    completed_at, result_preview, result_full, schema_mismatch, retryable
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.sample_filename,
                    task.table_name,
                    task.rows,
                    int(task.enable_db_export),
                    task.status.value,
                    task.progress,
                    task.error_message,
                    task.created_at.isoformat(),
                    task.started_at.isoformat() if task.started_at else None,
                    task.completed_at.isoformat() if task.completed_at else None,
                    json.dumps(task.result_preview, ensure_ascii=False, default=str) if task.result_preview else None,
                    json.dumps(task.result_full, ensure_ascii=False, default=str) if task.result_full else None,
                    int(task.schema_mismatch),
                    int(task.retryable),
                ),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    @staticmethod
    def _row_to_task(row: tuple) -> TaskInfo:
        return TaskInfo(
            id=row[0],
            sample_filename=row[1],
            table_name=row[2],
            rows=row[3],
            enable_db_export=bool(row[4]),
            status=TaskStatus(row[5]),
            progress=row[6],
            error_message=row[7],
            created_at=datetime.fromisoformat(row[8]),
            started_at=datetime.fromisoformat(row[9]) if row[9] else None,
            completed_at=datetime.fromisoformat(row[10]) if row[10] else None,
            result_preview=json.loads(row[11]) if row[11] else None,
            result_full=json.loads(row[12]) if row[12] else None,
            schema_mismatch=bool(row[13]),
            retryable=bool(row[14]),
        )

    async def create_task(
        self, sample_filename: str, table_name: str, rows: int, enable_db_export: bool = False,
    ) -> TaskInfo:
        task_id = str(uuid.uuid4())
        task = TaskInfo(
            id=task_id,
            sample_filename=sample_filename,
            table_name=table_name,
            rows=rows,
            enable_db_export=enable_db_export,
            status=TaskStatus.PENDING,
            progress=0,
            created_at=datetime.now(),
        )
        async with self._lock:
            self.tasks[task_id] = task
            self._save_task(task)
        if self._broadcast_fn:
            await self._broadcast_fn({"event": "task_created", "task": task.model_dump(mode="json")})
        return task

    async def update_task_status(
        self, task_id: str, status: TaskStatus, progress: Optional[int] = None,
        error_message: Optional[str] = None, result_preview: Optional[dict] = None,
        result_full: Optional[dict] = None, schema_mismatch: Optional[bool] = None,
        retryable: Optional[bool] = None,
    ) -> Optional[TaskInfo]:
        async with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return None
            task.status = status
            if progress is not None:
                task.progress = progress
            if error_message is not None:
                task.error_message = error_message
            if status == TaskStatus.RUNNING and task.started_at is None:
                task.started_at = datetime.now()
            if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                task.completed_at = datetime.now()
                task.progress = 100
            if result_preview is not None:
                task.result_preview = result_preview
            if result_full is not None:
                task.result_full = result_full
            if schema_mismatch is not None:
                task.schema_mismatch = schema_mismatch
            if retryable is not None:
                task.retryable = retryable
            self._save_task(task)
        if self._broadcast_fn:
            await self._broadcast_fn({"event": "task_updated", "task": task.model_dump(mode="json")})
        return task

    async def get_task(self, task_id: str) -> Optional[TaskInfo]:
        async with self._lock:
            return self.tasks.get(task_id)

    async def list_tasks(self, limit: int = 50) -> list[TaskInfo]:
        async with self._lock:
            tasks = sorted(self.tasks.values(), key=lambda t: t.created_at, reverse=True)
            return tasks[:limit]

    async def cancel_task(self, task_id: str) -> Optional[TaskInfo]:
        return await self.update_task_status(task_id, TaskStatus.CANCELLED)
