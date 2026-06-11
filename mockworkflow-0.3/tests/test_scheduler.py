"""Tests for backend/app/scheduler.py ScheduleManager and Scheduler."""
import asyncio
import json
import sqlite3

import pytest

from backend.app.scheduler import ScheduleManager, Scheduler
from backend.app.task_manager import TaskManager


@pytest.fixture
def sm(tmp_db_path):
    tm = TaskManager(storage_path=tmp_db_path, broadcast_fn=None)
    manager = ScheduleManager(storage_path=tmp_db_path, task_manager=tm, broadcast_fn=None)
    yield manager


@pytest.mark.asyncio
async def test_create_schedule(sm):
    s = await sm.create_schedule("sample.csv", "users", 100, "0 3 * * *")
    assert s.sample_filename == "sample.csv"
    assert s.table_name == "users"
    assert s.rows == 100
    assert s.cron == "0 3 * * *"
    assert s.enabled is True
    assert s.next_run is not None


@pytest.mark.asyncio
async def test_create_invalid_cron(sm):
    with pytest.raises(ValueError):
        await sm.create_schedule("sample.csv", "users", 100, "invalid")


@pytest.mark.asyncio
async def test_toggle_schedule(sm):
    s = await sm.create_schedule("sample.csv", "users", 100, "0 3 * * *")
    toggled = await sm.toggle_schedule(s.id)
    assert toggled.enabled is False
    assert toggled.next_run is None

    toggled_back = await sm.toggle_schedule(s.id)
    assert toggled_back.enabled is True
    assert toggled_back.next_run is not None


@pytest.mark.asyncio
async def test_delete_schedule(sm):
    s = await sm.create_schedule("sample.csv", "users", 100, "0 3 * * *")
    deleted = await sm.delete_schedule(s.id)
    assert deleted is not None
    assert await sm.get_schedule(s.id) is None


@pytest.mark.asyncio
async def test_update_next_run(sm):
    s = await sm.create_schedule("sample.csv", "users", 100, "0 3 * * *")
    original_next = s.next_run
    updated = await sm.update_next_run(s.id)
    assert updated.last_run is not None
    # next_run should be >= original (same or later)
    assert updated.next_run >= original_next


@pytest.mark.asyncio
async def test_schedule_persistence(tmp_db_path):
    tm = TaskManager(storage_path=tmp_db_path, broadcast_fn=None)
    sm1 = ScheduleManager(storage_path=tmp_db_path, task_manager=tm, broadcast_fn=None)
    s = await sm1.create_schedule("sample.csv", "users", 100, "0 3 * * *")

    sm2 = ScheduleManager(storage_path=tmp_db_path, task_manager=tm, broadcast_fn=None)
    fetched = await sm2.get_schedule(s.id)
    assert fetched is not None
    assert fetched.cron == "0 3 * * *"


@pytest.mark.asyncio
async def test_json_migration(tmp_db_path):
    json_path = tmp_db_path.with_suffix(".json")
    legacy = {
        "schedules": [
            {
                "id": "sch-1",
                "sample_filename": "old.csv",
                "table_name": "legacy",
                "rows": 50,
                "cron": "0 0 * * *",
                "enabled": True,
                "created_at": "2024-01-01T00:00:00",
            }
        ]
    }
    json_path.write_text(json.dumps(legacy), encoding="utf-8")

    tm = TaskManager(storage_path=tmp_db_path, broadcast_fn=None)
    sm = ScheduleManager(storage_path=tmp_db_path, task_manager=tm, broadcast_fn=None)
    schedules = await sm.list_schedules()
    assert any(s.id == "sch-1" for s in schedules)

    conn = sqlite3.connect(str(tmp_db_path))
    cursor = conn.execute("SELECT COUNT(*) FROM schedules")
    count = cursor.fetchone()[0]
    conn.close()
    assert count >= 1


@pytest.mark.asyncio
async def test_scheduler_start_stop(tmp_db_path):
    tm = TaskManager(storage_path=tmp_db_path, broadcast_fn=None)
    sm = ScheduleManager(storage_path=tmp_db_path, task_manager=tm, broadcast_fn=None)
    scheduler = Scheduler(sm, tm)

    await scheduler.start()
    assert scheduler._running is True
    assert scheduler._task is not None

    await scheduler.stop()
    assert scheduler._running is False
    assert scheduler._task is None
