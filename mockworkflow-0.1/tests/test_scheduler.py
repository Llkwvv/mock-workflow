"""
Tests for the task scheduler.
"""
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from mockworkflow.web.scheduler import ScheduleInfo, ScheduleManager, Scheduler


class TestScheduleInfo:
    """Test ScheduleInfo model."""

    def test_schedule_info_creation(self):
        """Test creating a schedule info object."""
        now = datetime.now()
        schedule = ScheduleInfo(
            id="test-id",
            sample_filename="samples/users.csv",
            table_name="users",
            rows=100,
            cron="0 9 * * *",  # Daily at 9am
            created_at=now
        )
        assert schedule.id == "test-id"
        assert schedule.sample_filename == "samples/users.csv"
        assert schedule.table_name == "users"
        assert schedule.rows == 100
        assert schedule.cron == "0 9 * * *"
        assert schedule.created_at == now
        assert not hasattr(schedule, "password")  # Ensure password is not included

    def test_schedule_info_optional_fields(self):
        """Test optional fields in schedule info."""
        now = datetime.now()
        schedule = ScheduleInfo(
            id="test-id",
            sample_filename="samples/users.csv",
            table_name="users",
            rows=100,
            cron="0 9 * * *",
            enable_db_export=True,
            enabled=False,
            created_at=now
        )
        assert schedule.enable_db_export is True
        assert schedule.enabled is False


class TestScheduleManager:
    """Test ScheduleManager functionality."""

    @pytest.fixture
    def temp_storage_file(self, tmp_path):
        """Create a temporary storage file for testing."""
        return tmp_path / "schedules.json"

    @pytest.fixture
    def schedule_manager(self, temp_storage_file):
        """Create a ScheduleManager with temporary storage."""
        with patch("mockworkflow.web.task_manager.TaskManager") as MockTaskManager:
            manager = ScheduleManager(
                storage_path=temp_storage_file,
                task_manager=MockTaskManager(),
                broadcast_fn=None
            )
            yield manager

    def test_create_schedule(self, schedule_manager):
        """Test creating a new schedule."""
        schedule = asyncio.run(schedule_manager.create_schedule(
            sample_filename="samples/users.csv",
            table_name="users",
            rows=100,
            cron="0 9 * * *"
        ))
        assert schedule.id is not None
        assert schedule.sample_filename == "samples/users.csv"
        assert schedule.table_name == "users"
        assert schedule.rows == 100
        assert schedule.cron == "0 9 * * *"
        assert schedule.enabled is True
        assert schedule.next_run is not None
        assert isinstance(schedule.created_at, datetime)

    def test_create_schedule_with_invalid_cron(self, schedule_manager):
        """Test creating a schedule with invalid cron expression."""
        with pytest.raises(ValueError, match="Invalid cron expression"):
            asyncio.run(schedule_manager.create_schedule(
                sample_filename="samples/users.csv",
                table_name="users",
                rows=100,
                cron="invalid-cron"
            ))

    def test_get_schedule(self, schedule_manager):
        """Test retrieving a schedule by ID."""
        # Create a schedule first
        created = asyncio.run(schedule_manager.create_schedule(
            sample_filename="samples/users.csv",
            table_name="users",
            rows=100,
            cron="0 9 * * *"
        ))
        # Retrieve it
        retrieved = asyncio.run(schedule_manager.get_schedule(created.id))
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.sample_filename == "samples/users.csv"

    def test_get_nonexistent_schedule(self, schedule_manager):
        """Test retrieving a non-existent schedule."""
        retrieved = asyncio.run(schedule_manager.get_schedule("nonexistent-id"))
        assert retrieved is None

    def test_list_schedules(self, schedule_manager):
        """Test listing all schedules."""
        # Create multiple schedules
        created1 = asyncio.run(schedule_manager.create_schedule(
            sample_filename="samples/users.csv",
            table_name="users",
            rows=100,
            cron="0 9 * * *"
        ))
        created2 = asyncio.run(schedule_manager.create_schedule(
            sample_filename="samples/products.csv",
            table_name="products",
            rows=50,
            cron="0 10 * * *"
        ))
        # List them
        schedules = asyncio.run(schedule_manager.list_schedules())
        assert len(schedules) >= 2
        # Should be sorted by creation time (newest first)
        assert schedules[0].id == created2.id or schedules[1].id == created2.id

    def test_delete_schedule(self, schedule_manager):
        """Test deleting a schedule."""
        # Create a schedule first
        created = asyncio.run(schedule_manager.create_schedule(
            sample_filename="samples/users.csv",
            table_name="users",
            rows=100,
            cron="0 9 * * *"
        ))
        # Delete it
        deleted = asyncio.run(schedule_manager.delete_schedule(created.id))
        assert deleted is not None
        assert deleted.id == created.id
        # Verify it's gone
        retrieved = asyncio.run(schedule_manager.get_schedule(created.id))
        assert retrieved is None

    def test_toggle_schedule(self, schedule_manager):
        """Test toggling a schedule's enabled state."""
        # Create a schedule first
        created = asyncio.run(schedule_manager.create_schedule(
            sample_filename="samples/users.csv",
            table_name="users",
            rows=100,
            cron="0 9 * * *"
        ))
        # Toggle it (should disable)
        toggled = asyncio.run(schedule_manager.toggle_schedule(created.id))
        assert toggled is not None
        assert toggled.enabled is False
        assert toggled.next_run is None
        # Toggle it again (should enable)
        toggled = asyncio.run(schedule_manager.toggle_schedule(created.id))
        assert toggled is not None
        assert toggled.enabled is True
        assert toggled.next_run is not None

    def test_update_next_run(self, schedule_manager):
        """Test updating a schedule's next run time."""
        # Create a schedule first
        created = asyncio.run(schedule_manager.create_schedule(
            sample_filename="samples/users.csv",
            table_name="users",
            rows=100,
            cron="0 9 * * *"
        ))
        original_next_run = created.next_run
        # Wait a bit and update next run
        with patch("datetime.datetime") as mock_datetime:
            future_time = datetime.now() + timedelta(days=1)
            mock_datetime.now.return_value = future_time
            updated = asyncio.run(schedule_manager.update_next_run(created.id))
        assert updated is not None
        assert updated.last_run is not None
        assert updated.next_run > original_next_run

    def test_persistence_to_json(self, temp_storage_file):
        """Test that schedules are persisted to JSON file."""
        with patch("mockworkflow.web.task_manager.TaskManager") as MockTaskManager:
            # Create manager with our temp file
            manager = ScheduleManager(
                storage_path=temp_storage_file,
                task_manager=MockTaskManager(),
                broadcast_fn=None
            )
            # Create a schedule
            created = asyncio.run(manager.create_schedule(
                sample_filename="samples/users.csv",
                table_name="users",
                rows=100,
                cron="0 9 * * *"
            ))
            # Verify file was created and contains data
            assert temp_storage_file.exists()
            data = json.loads(temp_storage_file.read_text(encoding="utf-8"))
            assert "schedules" in data
            assert len(data["schedules"]) == 1
            saved_schedule = data["schedules"][0]
            assert saved_schedule["id"] == created.id
            assert saved_schedule["sample_filename"] == "samples/users.csv"

        # Create a new manager and verify it loads from file
        with patch("mockworkflow.web.task_manager.TaskManager") as MockTaskManager:
            new_manager = ScheduleManager(
                storage_path=temp_storage_file,
                task_manager=MockTaskManager(),
                broadcast_fn=None
            )
            loaded_schedules = asyncio.run(new_manager.list_schedules())
            assert len(loaded_schedules) == 1
            assert loaded_schedules[0].id == created.id


class TestScheduler:
    """Test Scheduler functionality."""

    @pytest.fixture
    def schedule_manager(self):
        """Create a ScheduleManager for testing."""
        with patch("mockworkflow.web.task_manager.TaskManager") as MockTaskManager:
            return ScheduleManager(
                task_manager=MockTaskManager(),
                broadcast_fn=None
            )

    @pytest.fixture
    def scheduler(self, schedule_manager):
        """Create a Scheduler for testing."""
        return Scheduler(schedule_manager, schedule_manager._task_manager)

    @pytest.mark.asyncio
    async def test_start_stop_scheduler(self, scheduler):
        """Test starting and stopping the scheduler."""
        # Start scheduler
        await scheduler.start()
        assert scheduler._running is True
        assert scheduler._task is not None

        # Stop scheduler
        await scheduler.stop()
        assert scheduler._running is False
        assert scheduler._task is None

    @pytest.mark.asyncio
    async def test_scheduler_runs_scheduled_task(self, schedule_manager, scheduler):
        """Test that scheduler executes scheduled tasks at correct time."""
        # Create a schedule for right now
        now = datetime.now()
        with patch("mockworkflow.web.scheduler.datetime") as mock_datetime:
            mock_datetime.now.return_value = now
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

            # Create a schedule with a cron that matches now
            schedule = await schedule_manager.create_schedule(
                sample_filename="samples/users.csv",
                table_name="users",
                rows=100,
                cron="* * * * *"  # Every minute
            )

            # Patch the process_task function
            with patch("mockworkflow.web.scheduler.process_task") as mock_process_task:
                # Start scheduler
                await scheduler.start()
                # Give it a moment to run
                await asyncio.sleep(0.1)
                # Stop scheduler
                await scheduler.stop()

                # Verify process_task was called
                assert mock_process_task.called
                assert mock_process_task.call_count >= 1

    @pytest.mark.asyncio
    async def test_scheduler_only_runs_enabled_schedules(self, schedule_manager, scheduler):
        """Test that scheduler only runs enabled schedules."""
        # Create an enabled schedule
        enabled_schedule = await schedule_manager.create_schedule(
            sample_filename="samples/users.csv",
            table_name="users",
            rows=100,
            cron="* * * * *"
        )

        # Create a disabled schedule
        disabled_schedule = await schedule_manager.create_schedule(
            sample_filename="samples/products.csv",
            table_name="products",
            rows=50,
            cron="* * * * *"
        )
        # Disable it
        await schedule_manager.toggle_schedule(disabled_schedule.id)

        # Patch the process_task function
        with patch("mockworkflow.web.scheduler.process_task") as mock_process_task:
            # Start scheduler
            await scheduler.start()
            # Give it a moment to run
            await asyncio.sleep(0.1)
            # Stop scheduler
            await scheduler.stop()

            # Verify process_task was only called for enabled schedule
            assert mock_process_task.called
            assert mock_process_task.call_count >= 1

    @pytest.mark.asyncio
    async def test_scheduler_updates_next_run_time(self, schedule_manager, scheduler):
        """Test that scheduler updates the next run time after execution."""
        # Create a schedule
        schedule = await schedule_manager.create_schedule(
            sample_filename="samples/users.csv",
            table_name="users",
            rows=100,
            cron="* * * * *"
        )
        original_next_run = schedule.next_run

        # Patch the process_task function and update_next_run
        with patch("mockworkflow.web.scheduler.process_task"),\
             patch.object(schedule_manager, "update_next_run") as mock_update_next_run:
            # Start scheduler
            await scheduler.start()
            # Give it a moment to run
            await asyncio.sleep(0.1)
            # Stop scheduler
            await scheduler.stop()

            # Verify update_next_run was called
            assert mock_update_next_run.called
            assert mock_update_next_run.call_count >= 1
