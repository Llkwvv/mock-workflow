"""FastAPI backend for Mockworkflow (frontend/backend split)."""
import sys
from pathlib import Path

# Ensure project root is in path before any backend imports
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.auth import AuthMiddleware
from backend.app.deps import (
    FRONTEND_DIR,
    OUTPUT_DIR,
    project_root,
    schedule_manager,
    scheduler,
    task_manager,
    ws_manager,
)
from backend.config import get_settings

# Import routers
from backend.app.routers import agent, dashboard, generation, health, samples, schema, schedules, tasks, templates

# Phase 3 #12: health monitor instance
health_monitor = None

app = FastAPI(
    title="Mockworkflow API",
    description="Backend API for Mockworkflow - sample-driven mock data generation",
    version="0.3.0",
)

# CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth middleware
settings = get_settings()
if settings.web_password:
    app.add_middleware(AuthMiddleware, password=settings.web_password)

# Mount output directory for downloads
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")


# === WebSocket endpoints (kept in main.py due to global manager coupling) ===
@app.websocket("/api/ws/tasks")
async def tasks_websocket(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Phase 3 #3: heartbeat — timeout recv to keep connection alive
            data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            if data == "ping":
                await websocket.send_text("pong")
    except (WebSocketDisconnect, asyncio.TimeoutError):
        ws_manager.disconnect(websocket)


# === Register API routers ===
app.include_router(health.router)
app.include_router(samples.router)
app.include_router(tasks.router)
app.include_router(schedules.router)
app.include_router(generation.router)
app.include_router(schema.router)
app.include_router(templates.router)
app.include_router(agent.router)
app.include_router(dashboard.router)


# === Startup / Shutdown ===
@app.on_event("startup")
async def startup_event():
    global health_monitor
    from backend.app import processor
    processor.set_globals(task_manager, project_root)
    await scheduler.start()
    if health_monitor is None:
        from backend.agent.tools.health_monitor import HealthMonitor
        health_monitor = HealthMonitor(
            task_manager=task_manager,
            schedule_manager=schedule_manager,
            broadcast_fn=ws_manager.broadcast if ws_manager else None,
            interval_seconds=300,
        )
    if health_monitor:
        await health_monitor.start()


@app.on_event("shutdown")
async def shutdown_event():
    await scheduler.stop()
    if health_monitor is not None:
        await health_monitor.stop()


# Mount frontend static files last so API routes take precedence
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
