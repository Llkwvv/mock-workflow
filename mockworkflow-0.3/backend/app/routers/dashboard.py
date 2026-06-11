"""Dashboard API for aggregated metrics and data-quality insights."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter

from backend.app.deps import schedule_manager, task_manager
from backend.app.task_manager import TaskStatus

router = APIRouter()


@router.get("/api/dashboard", tags=["dashboard"])
async def get_dashboard():
    """Return aggregated metrics for the dashboard."""
    tasks = await task_manager.list_tasks(limit=5000)
    schedules = await schedule_manager.list_schedules()

    total = len(tasks)
    completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
    failed = sum(1 for t in tasks if t.status == TaskStatus.FAILED)
    pending = sum(1 for t in tasks if t.status in (TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING))

    # Last 24h
    day_ago = datetime.now() - timedelta(days=1)
    recent_tasks = [t for t in tasks if t.created_at and t.created_at > day_ago]
    recent_completed = sum(1 for t in recent_tasks if t.status == TaskStatus.COMPLETED)

    # Per-table breakdown
    table_counts: dict[str, int] = {}
    for t in tasks:
        table_counts[t.table_name] = table_counts.get(t.table_name, 0) + 1
    top_tables = sorted(table_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    success_rate = round(completed / total * 100, 1) if total else 0.0

    return {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_tasks": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "success_rate": success_rate,
            "recent_24h": {
                "total": len(recent_tasks),
                "completed": recent_completed,
            },
        },
        "schedules": {
            "total": len(schedules),
            "enabled": sum(1 for s in schedules if s.enabled),
        },
        "top_tables": [{"table": k, "count": v} for k, v in top_tables],
    }
