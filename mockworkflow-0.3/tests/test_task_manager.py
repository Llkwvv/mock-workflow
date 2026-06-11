"""Tests for backend/app/task_manager.py SQLite migration and CRUD."""
import asyncio
import json
import sqlite3

import pytest

from backend.app.task_manager import TaskManager, TaskStatus


@pytest.fixture
def tm(tmp_db_path):
    manager = TaskManager(storage_path=tmp_db_path, broadcast_fn=None)
    yield manager


@pytest.mark.asyncio
async def test_create_task(tm):
    task = await tm.create_task("sample.csv", "users", 100)
    assert task.status == TaskStatus.PENDING
    assert task.rows == 100
    assert task.sample_filename == "sample.csv"
    assert task.table_name == "users"


@pytest.mark.asyncio
async def test_get_task(tm):
    task = await tm.create_task("sample.csv", "users", 100)
    fetched = await tm.get_task(task.id)
    assert fetched is not None
    assert fetched.id == task.id


@pytest.mark.asyncio
async def test_list_tasks(tm):
    t1 = await tm.create_task("a.csv", "t1", 10)
    t2 = await tm.create_task("b.csv", "t2", 20)
    tasks = await tm.list_tasks(limit=10)
    assert len(tasks) == 2
    # descending by created_at
    assert tasks[0].id == t2.id


@pytest.mark.asyncio
async def test_update_task_status(tm):
    task = await tm.create_task("sample.csv", "users", 100)
    updated = await tm.update_task_status(task.id, TaskStatus.RUNNING, progress=50)
    assert updated.status == TaskStatus.RUNNING
    assert updated.progress == 50
    assert updated.started_at is not None

    completed = await tm.update_task_status(task.id, TaskStatus.COMPLETED)
    assert completed.status == TaskStatus.COMPLETED
    assert completed.progress == 100
    assert completed.completed_at is not None


@pytest.mark.asyncio
async def test_cancel_task(tm):
    task = await tm.create_task("sample.csv", "users", 100)
    cancelled = await tm.cancel_task(task.id)
    assert cancelled.status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_persistence(tmp_db_path):
    tm1 = TaskManager(storage_path=tmp_db_path, broadcast_fn=None)
    task = await tm1.create_task("sample.csv", "users", 100)
    await tm1.update_task_status(task.id, TaskStatus.COMPLETED, result_preview={"rows": 100})

    # Simulate restart by creating new instance pointing at same DB
    tm2 = TaskManager(storage_path=tmp_db_path, broadcast_fn=None)
    fetched = await tm2.get_task(task.id)
    assert fetched is not None
    assert fetched.status == TaskStatus.COMPLETED
    assert fetched.result_preview == {"rows": 100}


@pytest.mark.asyncio
async def test_json_migration(tmp_db_path):
    # Write legacy JSON file
    json_path = tmp_db_path.with_suffix(".json")
    legacy = {
        "tasks": [
            {
                "id": "legacy-1",
                "sample_filename": "old.csv",
                "table_name": "legacy",
                "rows": 50,
                "enable_db_export": False,
                "status": "completed",
                "progress": 100,
                "created_at": "2024-01-01T00:00:00",
            }
        ]
    }
    json_path.write_text(json.dumps(legacy), encoding="utf-8")

    tm = TaskManager(storage_path=tmp_db_path, broadcast_fn=None)
    tasks = await tm.list_tasks(limit=10)
    assert any(t.id == "legacy-1" for t in tasks)

    # Verify DB has data (so migration won't repeat)
    conn = sqlite3.connect(str(tmp_db_path))
    cursor = conn.execute("SELECT COUNT(*) FROM tasks")
    count = cursor.fetchone()[0]
    conn.close()
    assert count >= 1
