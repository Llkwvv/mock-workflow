"""Health check endpoints."""
import sqlite3
from datetime import datetime

from fastapi import APIRouter

from backend.app.deps import schedule_manager, task_manager
from backend.config import get_settings

router = APIRouter()


@router.get("/api/health", tags=["health"])
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@router.get("/api/health/detailed", tags=["health"])
async def health_check_detailed():
    """Detailed health check including DB, task queue, schedule status, and LLM connectivity."""
    settings = get_settings()
    checks: dict[str, dict] = {}
    overall = "ok"

    # SQLite check
    try:
        from backend.app.deps import DB_PATH
        conn = sqlite3.connect(str(DB_PATH), timeout=2)
        conn.execute("SELECT 1")
        conn.close()
        checks["sqlite"] = {"status": "ok"}
    except Exception as e:
        checks["sqlite"] = {"status": "error", "detail": str(e)}
        overall = "degraded"

    # Task manager check
    try:
        tasks = await task_manager.list_tasks(limit=1000)
        pending = sum(1 for t in tasks if t.status in ("PENDING", "QUEUED", "RUNNING"))
        failed = sum(1 for t in tasks if t.status == "FAILED")
        checks["tasks"] = {
            "status": "ok",
            "total": len(tasks),
            "pending": pending,
            "failed": failed,
        }
        if failed > 5:
            overall = "degraded"
    except Exception as e:
        checks["tasks"] = {"status": "error", "detail": str(e)}
        overall = "degraded"

    # Schedule check
    try:
        schedules = await schedule_manager.list_schedules()
        enabled = sum(1 for s in schedules if s.enabled)
        checks["schedules"] = {"status": "ok", "total": len(schedules), "enabled": enabled}
    except Exception as e:
        checks["schedules"] = {"status": "error", "detail": str(e)}
        overall = "degraded"

    # LLM check (lightweight, no blocking call)
    checks["llm"] = {"status": "enabled" if settings.llm_enabled else "disabled"}

    return {
        "status": overall,
        "timestamp": datetime.now().isoformat(),
        "checks": checks,
    }
