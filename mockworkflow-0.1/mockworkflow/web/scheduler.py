"""Task scheduler for scheduled mock data generation."""
import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from croniter import croniter
from pydantic import BaseModel, Field


class ScheduleInfo(BaseModel):
    """Scheduled task information."""
    id: str
    sample_filename: str
    table_name: str
    rows: int
    enable_db_export: bool = False
    cron: str  # 5-field cron expression
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    created_at: datetime


class ScheduleManager:
    """Manage scheduled tasks with JSON persistence."""

    def __init__(self, storage_path: str | Path | None = None, task_manager=None, broadcast_fn=None):
        self.schedules: dict[str, ScheduleInfo] = {}
        self._lock = asyncio.Lock()
        self._task_manager = task_manager
        self._broadcast_fn = broadcast_fn
        # Default storage path: schedules.json in the web directory
        if storage_path is None:
            storage_path = Path(__file__).resolve().parent / "schedules.json"
        self._storage_path = Path(storage_path)
        self._load_schedules()

    def _load_schedules(self) -> None:
        """Load schedules from JSON file."""
        if not self._storage_path.exists():
            return
        try:
            data = json.loads(self._storage_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "schedules" in data:
                for schedule_data in data["schedules"]:
                    try:
                        schedule = ScheduleInfo.model_validate(schedule_data)
                        self.schedules[schedule.id] = schedule
                    except Exception:
                        continue
        except Exception:
            pass

    def _save_schedules(self) -> None:
        """Save schedules to JSON file."""
        try:
            schedules_list = [
                schedule.model_dump(mode="json")
                for schedule in sorted(self.schedules.values(), key=lambda s: s.created_at, reverse=True)
            ]
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            self._storage_path.write_text(
                json.dumps({"schedules": schedules_list}, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass

    async def create_schedule(
        self,
        sample_filename: str,
        table_name: str,
        rows: int,
        cron: str,
        enable_db_export: bool = False,
    ) -> ScheduleInfo:
        """Create a new schedule."""
        # Validate cron expression
        try:
            croniter(cron)
        except Exception as e:
            raise ValueError(f"Invalid cron expression: {cron} - {e}")

        schedule_id = str(uuid.uuid4())
        now = datetime.now()
        # Calculate next run time
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
            self._save_schedules()
        return schedule

    async def get_schedule(self, schedule_id: str) -> Optional[ScheduleInfo]:
        """Get schedule by ID."""
        async with self._lock:
            return self.schedules.get(schedule_id)

    async def list_schedules(self) -> list[ScheduleInfo]:
        """List all schedules."""
        async with self._lock:
            return sorted(self.schedules.values(), key=lambda s: s.created_at, reverse=True)

    async def delete_schedule(self, schedule_id: str) -> Optional[ScheduleInfo]:
        """Delete a schedule."""
        async with self._lock:
            schedule = self.schedules.pop(schedule_id, None)
            if schedule:
                self._save_schedules()
            return schedule

    async def toggle_schedule(self, schedule_id: str) -> Optional[ScheduleInfo]:
        """Enable or disable a schedule."""
        async with self._lock:
            schedule = self.schedules.get(schedule_id)
            if not schedule:
                return None
            schedule.enabled = not schedule.enabled
            if schedule.enabled:
                # Recalculate next run time
                cron_obj = croniter(schedule.cron, datetime.now())
                schedule.next_run = cron_obj.get_next(datetime)
            else:
                schedule.next_run = None
            self._save_schedules()
            return schedule

    async def update_next_run(self, schedule_id: str) -> Optional[ScheduleInfo]:
        """Update next run time after execution."""
        async with self._lock:
            schedule = self.schedules.get(schedule_id)
            if not schedule:
                return None
            schedule.last_run = datetime.now()
            cron_obj = croniter(schedule.cron, datetime.now())
            schedule.next_run = cron_obj.get_next(datetime)
            self._save_schedules()
            return schedule


class Scheduler:
    """Async scheduler that executes scheduled tasks."""

    def __init__(self, schedule_manager: ScheduleManager, task_manager):
        self._schedule_manager = schedule_manager
        self._task_manager = task_manager
        self._running = False
        self._task = None

    async def start(self):
        """Start the scheduler loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        """Stop the scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run_loop(self):
        """Main scheduler loop - checks every 30 seconds."""
        from mockworkflow.web.app import process_task

        while self._running:
            try:
                schedules = await self._schedule_manager.list_schedules()
                now = datetime.now()

                for schedule in schedules:
                    if not schedule.enabled or not schedule.next_run:
                        continue

                    # Check if it's time to run
                    if now >= schedule.next_run:
                        # Create a task
                        task = await self._task_manager.create_task(
                            sample_filename=schedule.sample_filename,
                            table_name=schedule.table_name,
                            rows=schedule.rows,
                            enable_db_export=schedule.enable_db_export,
                        )
                        # Execute task in background
                        asyncio.create_task(process_task(task.id))
                        # Update next run time
                        await self._schedule_manager.update_next_run(schedule.id)

            except Exception as e:
                print(f"Scheduler error: {e}")

            await asyncio.sleep(30)  # Check every 30 seconds