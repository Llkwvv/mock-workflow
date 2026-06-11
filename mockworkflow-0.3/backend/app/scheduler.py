"""Task scheduler for scheduled mock data generation."""
import asyncio
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from croniter import croniter
from pydantic import BaseModel, Field


class ScheduleInfo(BaseModel):
    id: str
    sample_filename: str
    table_name: str
    rows: int
    enable_db_export: bool = False
    cron: str
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    created_at: datetime


class ScheduleManager:
    """Manage scheduled tasks with SQLite persistence."""

    _SCHEDULES_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS schedules (
            id TEXT PRIMARY KEY,
            sample_filename TEXT NOT NULL,
            table_name TEXT NOT NULL,
            rows INTEGER NOT NULL,
            enable_db_export INTEGER NOT NULL DEFAULT 0,
            cron TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            last_run TEXT,
            next_run TEXT,
            created_at TEXT NOT NULL
        )
    """

    def __init__(self, storage_path: str | Path | None = None, task_manager=None, broadcast_fn=None):
        self.schedules: dict[str, ScheduleInfo] = {}
        self._lock = asyncio.Lock()
        self._task_manager = task_manager
        self._broadcast_fn = broadcast_fn
        if storage_path is None:
            storage_path = Path(__file__).resolve().parent / "mockworkflow.db"
        self._db_path = Path(storage_path)
        self._init_db()
        self._migrate_from_json()
        self._load_schedules()

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.execute(self._SCHEDULES_TABLE_SQL)
        conn.commit()
        conn.close()

    def _migrate_from_json(self) -> None:
        json_path = self._db_path.with_suffix(".json")
        if not json_path.exists():
            return
        if self._db_path.exists():
            try:
                conn = sqlite3.connect(str(self._db_path))
                cursor = conn.execute("SELECT COUNT(*) FROM schedules")
                count = cursor.fetchone()[0]
                conn.close()
                if count > 0:
                    return
            except Exception:
                pass
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "schedules" in data:
                for schedule_data in data["schedules"]:
                    try:
                        schedule = ScheduleInfo.model_validate(schedule_data)
                        self._save_schedule(schedule)
                    except Exception:
                        continue
        except Exception:
            pass

    def _load_schedules(self) -> None:
        if not self._db_path.exists():
            return
        try:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.execute("SELECT * FROM schedules ORDER BY created_at DESC")
            for row in cursor.fetchall():
                try:
                    schedule = self._row_to_schedule(row)
                    self.schedules[schedule.id] = schedule
                except Exception:
                    continue
            conn.close()
        except Exception:
            pass

    def _save_schedule(self, schedule: ScheduleInfo) -> None:
        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute(
                """
                INSERT OR REPLACE INTO schedules (
                    id, sample_filename, table_name, rows, enable_db_export,
                    cron, enabled, last_run, next_run, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    schedule.id,
                    schedule.sample_filename,
                    schedule.table_name,
                    schedule.rows,
                    int(schedule.enable_db_export),
                    schedule.cron,
                    int(schedule.enabled),
                    schedule.last_run.isoformat() if schedule.last_run else None,
                    schedule.next_run.isoformat() if schedule.next_run else None,
                    schedule.created_at.isoformat(),
                ),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    @staticmethod
    def _row_to_schedule(row: tuple) -> ScheduleInfo:
        return ScheduleInfo(
            id=row[0],
            sample_filename=row[1],
            table_name=row[2],
            rows=row[3],
            enable_db_export=bool(row[4]),
            cron=row[5],
            enabled=bool(row[6]),
            last_run=datetime.fromisoformat(row[7]) if row[7] else None,
            next_run=datetime.fromisoformat(row[8]) if row[8] else None,
            created_at=datetime.fromisoformat(row[9]),
        )

    async def create_schedule(
        self, sample_filename: str, table_name: str, rows: int, cron: str, enable_db_export: bool = False,
    ) -> ScheduleInfo:
        try:
            croniter(cron)
        except Exception as e:
            raise ValueError(f"Invalid cron expression: {cron} - {e}")

        schedule_id = str(uuid.uuid4())
        now = datetime.now()
        cron_obj = croniter(cron, now)
        next_run = cron_obj.get_next(datetime)

        schedule = ScheduleInfo(
            id=schedule_id,
            sample_filename=sample_filename,
            table_name=table_name,
            rows=rows,
            enable_db_export=enable_db_export,
            cron=cron,
            enabled=True,
            next_run=next_run,
            created_at=now,
        )
        async with self._lock:
            self.schedules[schedule_id] = schedule
            self._save_schedule(schedule)
        return schedule

    async def get_schedule(self, schedule_id: str) -> Optional[ScheduleInfo]:
        async with self._lock:
            return self.schedules.get(schedule_id)

    async def list_schedules(self) -> list[ScheduleInfo]:
        async with self._lock:
            return sorted(self.schedules.values(), key=lambda s: s.created_at, reverse=True)

    async def delete_schedule(self, schedule_id: str) -> Optional[ScheduleInfo]:
        async with self._lock:
            schedule = self.schedules.pop(schedule_id, None)
            if schedule:
                try:
                    conn = sqlite3.connect(str(self._db_path))
                    conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
                    conn.commit()
                    conn.close()
                except Exception:
                    pass
            return schedule

    async def toggle_schedule(self, schedule_id: str) -> Optional[ScheduleInfo]:
        async with self._lock:
            schedule = self.schedules.get(schedule_id)
            if not schedule:
                return None
            schedule.enabled = not schedule.enabled
            if schedule.enabled:
                cron_obj = croniter(schedule.cron, datetime.now())
                schedule.next_run = cron_obj.get_next(datetime)
            else:
                schedule.next_run = None
            self._save_schedule(schedule)
            return schedule

    async def update_next_run(self, schedule_id: str) -> Optional[ScheduleInfo]:
        async with self._lock:
            schedule = self.schedules.get(schedule_id)
            if not schedule:
                return None
            schedule.last_run = datetime.now()
            cron_obj = croniter(schedule.cron, datetime.now())
            schedule.next_run = cron_obj.get_next(datetime)
            self._save_schedule(schedule)
            return schedule


class Scheduler:
    """Async scheduler that executes scheduled tasks."""

    def __init__(self, schedule_manager: ScheduleManager, task_manager):
        self._schedule_manager = schedule_manager
        self._task_manager = task_manager
        self._running = False
        self._task = None

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run_loop(self):
        # Lazy import to avoid circular dependency
        from backend.app.processor import process_task
        from backend.agent.tools.scheduler import decide_schedule_params
        from backend.app.task_manager import TaskStatus
        from backend.config import get_settings

        _semaphore = asyncio.Semaphore(4)

        async def _run_with_limit(task_id: str):
            async with _semaphore:
                await process_task(task_id)

        while self._running:
            try:
                all_tasks = await self._task_manager.list_tasks()
                schedules = await self._schedule_manager.list_schedules()
                now = datetime.now()
                pending = len([
                    t for t in all_tasks
                    if t.status in (TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING)
                ])
                params = decide_schedule_params(pending_tasks=pending)
                max_concurrency = params["max_concurrency"]
                running = 0

                for schedule in schedules:
                    if running >= max_concurrency:
                        break
                    if not schedule.enabled or not schedule.next_run:
                        continue
                    if now >= schedule.next_run:
                        task = await self._task_manager.create_task(
                            sample_filename=schedule.sample_filename,
                            table_name=schedule.table_name,
                            rows=schedule.rows,
                            enable_db_export=schedule.enable_db_export,
                        )
                        await self._task_manager.update_task_status(task.id, TaskStatus.QUEUED)
                        asyncio.create_task(_run_with_limit(task.id))
                        await self._schedule_manager.update_next_run(schedule.id)
                        running += 1
            except Exception as e:
                import logging
                logging.getLogger(__name__).error("Scheduler error: %s", e)
            # Phase 3 #10: dynamic sleep interval
            try:
                all_tasks = await self._task_manager.list_tasks()
                pending = len([
                    t for t in all_tasks
                    if t.status in (TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING)
                ])
                params = decide_schedule_params(pending_tasks=pending)
                await asyncio.sleep(params["sleep_seconds"])
            except Exception:
                await asyncio.sleep(30)
