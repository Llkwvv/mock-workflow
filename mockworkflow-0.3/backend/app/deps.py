"""Shared dependencies and global instances for the FastAPI app."""
from pathlib import Path

from fastapi import WebSocket

from backend.app.scheduler import ScheduleManager, Scheduler
from backend.app.task_manager import TaskManager

# Project root is two levels above this file (backend/app -> backend -> project_root)
project_root = Path(__file__).resolve().parent.parent.parent

# Paths
OUTPUT_DIR = project_root / "output"
SAMPLES_DIR = project_root / "samples"
FRONTEND_DIR = project_root / "frontend"
DB_PATH = project_root / "backend" / "app" / "mockworkflow.db"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict):
        disconnected = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)


# Global instances
ws_manager = ConnectionManager()
task_manager = TaskManager(broadcast_fn=ws_manager.broadcast)
schedule_manager = ScheduleManager(
    task_manager=task_manager,
    broadcast_fn=ws_manager.broadcast
)
scheduler = Scheduler(schedule_manager, task_manager)
