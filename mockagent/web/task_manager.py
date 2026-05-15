
"""Task state management for web frontend."""
import asyncio
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
    status: TaskStatus
    progress: int = Field(default=0, ge=0, le=100)
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_preview: Optional[dict] = None
    result_full: Optional[dict] = None


class TaskManager:
    """In-memory task manager for tracking generation tasks."""

    def __init__(self):
        self.tasks: dict[str, TaskInfo] = {}
        self._lock = asyncio.Lock()

    async def create_task(
        self,
        sample_filename: str,
        table_name: str,
        rows: int,
    ) -> TaskInfo:
        """Create a new task."""
        task_id = str(uuid.uuid4())
        task = TaskInfo(
            id=task_id,
            sample_filename=sample_filename,
            table_name=table_name,
            rows=rows,
            status=TaskStatus.PENDING,
            progress=0,
            created_at=datetime.now(),
        )
        async with self._lock:
            self.tasks[task_id] = task
        return task

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        progress: Optional[int] = None,
        error_message: Optional[str] = None,
        result_preview: Optional[dict] = None,
        result_full: Optional[dict] = None,
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


# Global task manager instance
task_manager = TaskManager()

