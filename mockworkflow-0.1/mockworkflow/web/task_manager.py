
"""Task state management for web frontend with persistent storage."""
import asyncio
import json
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
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
    """In-memory task manager with JSON file persistence for tracking generation tasks."""

    def __init__(self, storage_path: str | Path | None = None, broadcast_fn=None):
        self.tasks: dict[str, TaskInfo] = {}
        self._lock = asyncio.Lock()
        self._broadcast_fn = broadcast_fn
        # Default storage path: tasks.json in the web directory
        if storage_path is None:
            storage_path = Path(__file__).resolve().parent / "tasks.json"
        self._storage_path = Path(storage_path)
        # Load existing tasks from file
        self._load_tasks()

    def _load_tasks(self) -> None:
        """Load tasks from JSON file."""
        if not self._storage_path.exists():
            return
        try:
            data = json.loads(self._storage_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "tasks" in data:
                for task_data in data["tasks"]:
                    try:
                        task = TaskInfo.model_validate(task_data)
                        self.tasks[task.id] = task
                    except Exception:
                        continue
        except Exception:
            pass

    def _save_tasks(self) -> None:
        """Save tasks to JSON file."""
        try:
            tasks_list = [
                task.model_dump(mode="json")
                for task in sorted(self.tasks.values(), key=lambda t: t.created_at, reverse=True)
            ]
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._storage_path.write_text(
                json.dumps({"tasks": tasks_list}, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass

    async def create_task(
        self,
        sample_filename: str,
        table_name: str,
        rows: int,
        enable_db_export: bool = False,
    ) -> TaskInfo:
        """Create a new task."""
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
            self._save_tasks()
        # Broadcast task_created event
        if self._broadcast_fn:
            await self._broadcast_fn({"event": "task_created", "task": task.model_dump(mode="json")})
        return task

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        progress: Optional[int] = None,
        error_message: Optional[str] = None,
        result_preview: Optional[dict] = None,
        result_full: Optional[dict] = None,
        schema_mismatch: Optional[bool] = None,
        retryable: Optional[bool] = None,
    ) -> Optional[TaskInfo]:
        """Update task status."""
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
            self._save_tasks()
        # Broadcast task_updated event
        if self._broadcast_fn:
            await self._broadcast_fn({"event": "task_updated", "task": task.model_dump(mode="json")})
        return task

    async def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """Get task by ID."""
        async with self._lock:
            return self.tasks.get(task_id)

    async def list_tasks(self, limit: int = 50) -> list[TaskInfo]:
        """List all tasks, most recent first."""
        async with self._lock:
            tasks = sorted(self.tasks.values(), key=lambda t: t.created_at, reverse=True)
            return tasks[:limit]

    async def cancel_task(self, task_id: str) -> Optional[TaskInfo]:
        """Cancel a pending or running task."""
        return await self.update_task_status(task_id, TaskStatus.CANCELLED)


# Global task manager instance with persistent storage
task_manager = TaskManager()

