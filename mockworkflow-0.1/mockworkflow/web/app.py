
"""FastAPI web application for Mockworkflow."""
import asyncio
import json
import shutil
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional

from mockworkflow.config import get_settings
from mockworkflow.services.generation import build_generation_preview, generate_to_output
from mockworkflow.schemas.field import FieldSpec
from mockworkflow.web.task_manager import TaskInfo, TaskManager, TaskStatus
from mockworkflow.web.auth import AuthMiddleware, verify_password
from mockworkflow.web.scheduler import ScheduleInfo, ScheduleManager, Scheduler
from mockworkflow.output.db_writer import TableSchemaMismatchError

# Setup
BASE_DIR = Path(__file__).resolve().parent
project_root = BASE_DIR.parent.parent
templates_dir = BASE_DIR / "templates"
static_dir = BASE_DIR / "static"

templates_dir.mkdir(parents=True, exist_ok=True)
static_dir.mkdir(parents=True, exist_ok=True)


app = FastAPI(
    title="Mockworkflow Web",
    description="Web interface for Mockworkflow - sample-driven mock data generation",
    version="0.1.0",
)

# Mount authentication middleware if password is set
settings = get_settings()
if settings.web_password:
    app.add_middleware(AuthMiddleware, password=settings.web_password)

# Mount static files
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Mount output directory for CSV downloads
output_dir = project_root / "output"
output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/output", StaticFiles(directory=str(output_dir)), name="output")

# Templates
templates = Jinja2Templates(directory=str(templates_dir))
templates.env.bytecode_cache = None


# === WebSocket Connection Manager ===

class ConnectionManager:
    """Manage WebSocket connections for real-time task updates."""

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        disconnected = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)


ws_manager = ConnectionManager()


# === Task Manager with WebSocket Broadcast ===

task_manager = TaskManager(broadcast_fn=ws_manager.broadcast)


# === Schedule Manager ===

schedule_manager = ScheduleManager(
    task_manager=task_manager,
    broadcast_fn=ws_manager.broadcast
)

# Create scheduler instance (needs to be started in startup event)
scheduler = Scheduler(schedule_manager, task_manager)


# === API Models ===

class TaskCreateRequest(BaseModel):
    sample_filename: str = Field(min_length=1, description="Path to the sample data file")
    table_name: str = Field(default="auto_table", min_length=1, description="Target table name")
    rows: int = Field(default=100, gt=0, le=100000, description="Number of mock rows to generate")
    enable_db_export: bool = Field(default=False, description="Export generated rows to the database (requires the MOCKWORKFLOW_DB_EXPORT_ENABLED master toggle)")

    @field_validator("sample_filename")
    @classmethod
    def validate_sample_file(cls, v: str) -> str:
        """Validate that sample file exists."""
        path = Path(v)
        if not path.is_file():
            # Also check in samples directory
            samples_path = Path(__file__).resolve().parent.parent.parent / "samples" / v
            if not samples_path.is_file():
                raise ValueError(f"Sample file not found: {v}")
        return v

    @model_validator(mode="after")
    def auto_generate_table_name(self) -> "TaskCreateRequest":
        """Auto-generate table name from filename if not specified."""
        if self.table_name in ("auto_table", "", None):
            # Extract filename from sample_filename
            filename = Path(self.sample_filename).stem
            # 去除文件名中所有非中文，再取剩余中文的拼音首字母
            from mockworkflow.utils.pinyin import filename_to_table_name
            self.table_name = filename_to_table_name(filename) or "auto_table"
        return self


class TaskCreateResponse(BaseModel):
    task_id: str
    message: str


class TaskResponse(BaseModel):
    task: TaskInfo


class TaskListResponse(BaseModel):
    tasks: list[TaskInfo]
    total: int


class PreviewResponse(BaseModel):
    task_id: str
    preview: dict
    fields: list[dict]
    create_table_sql: str
    preview_rows: list[dict]


class GenerateRequest(BaseModel):
    sample_file: Optional[str] = None
    rows: int = Field(default=100, gt=0, le=100000)
    table_name: str = Field(default="auto_table")
    enable_db_export: bool = Field(default=False)


class BatchTaskCreateItem(BaseModel):
    sample_filename: str = Field(min_length=1, description="Path to the sample data file")
    table_name: str = Field(default="auto_table", min_length=1, description="Target table name")
    rows: int = Field(default=100, gt=0, le=100000, description="Number of mock rows to generate")
    enable_db_export: bool = Field(default=False, description="Export generated rows to the database")

    @field_validator("sample_filename")
    @classmethod
    def validate_sample_file(cls, v: str) -> str:
        """Validate that sample file exists."""
        path = Path(v)
        if not path.is_file():
            # Also check in samples directory
            samples_path = Path(__file__).resolve().parent.parent.parent / "samples" / v
            if not samples_path.is_file():
                raise ValueError(f"Sample file not found: {v}")
        return v


class BatchTaskCreateRequest(BaseModel):
    tasks: List[BatchTaskCreateItem] = Field(min_items=1, max_items=100, description="List of tasks to create")
    auto_table_name: bool = Field(default=True, description="Auto-generate table name from filename")


class BatchTaskCreateResponse(BaseModel):
    task_ids: List[str]
    message: str
    created_count: int


class ScheduleCreateRequest(BaseModel):
    sample_filename: str = Field(min_length=1, description="Path to the sample data file")
    table_name: str = Field(default="auto_table", min_length=1, description="Target table name")
    rows: int = Field(default=100, gt=0, le=100000, description="Number of mock rows to generate")
    enable_db_export: bool = Field(default=False, description="Export generated rows to the database")
    cron: str = Field(min_length=9, description="5-field cron expression (e.g., '0 9 * * *' for daily at 9am)")

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        """Validate cron expression."""
        from croniter import croniter
        try:
            croniter(v)
            return v
        except Exception as e:
            raise ValueError(f"Invalid cron expression: {v} - {e}")


class ScheduleResponse(BaseModel):
    schedule: ScheduleInfo


class ScheduleListResponse(BaseModel):
    schedules: list[ScheduleInfo]
    total: int


# === API Routes ===

router = APIRouter()


@router.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@router.websocket("/ws/tasks")
async def tasks_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time task updates."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, client doesn't need to send messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@router.post(
    "/api/tasks",
    response_model=TaskCreateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["tasks"],
)
async def create_task(
    background_tasks: BackgroundTasks,
    request: TaskCreateRequest,
):
    """Create a new generation task."""
    task = await task_manager.create_task(
        sample_filename=request.sample_filename,
        table_name=request.table_name,
        rows=request.rows,
        enable_db_export=request.enable_db_export,
    )
    # Start task processing in background
    background_tasks.add_task(process_task, task.id)
    return {"task_id": task.id, "message": "Task created and queued for processing"}


@router.get(
    "/api/tasks/{task_id}",
    response_model=TaskResponse,
    tags=["tasks"],
)
async def get_task(task_id: str):
    """Get task status and result."""
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": task}


@router.get(
    "/api/tasks",
    response_model=TaskListResponse,
    tags=["tasks"],
)
async def list_tasks(limit: int = 50):
    """List all tasks."""
    tasks = await task_manager.list_tasks(limit=limit)
    return {"tasks": tasks, "total": len(tasks)}


@router.delete(
    "/api/tasks/{task_id}",
    tags=["tasks"],
)
async def cancel_task(task_id: str):
    """Cancel a task."""
    task = await task_manager.cancel_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task cancelled"}


# === Schedule API Routes ===

@router.post(
    "/api/schedules",
    response_model=ScheduleResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["schedules"],
)
async def create_schedule(request: ScheduleCreateRequest):
    """Create a new scheduled task."""
    try:
        schedule = await schedule_manager.create_schedule(
            sample_filename=request.sample_filename,
            table_name=request.table_name,
            rows=request.rows,
            cron=request.cron,
            enable_db_export=request.enable_db_export,
        )
        return {"schedule": schedule}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/api/schedules",
    response_model=ScheduleListResponse,
    tags=["schedules"],
)
async def list_schedules():
    """List all scheduled tasks."""
    schedules = await schedule_manager.list_schedules()
    return {"schedules": schedules, "total": len(schedules)}


@router.get(
    "/api/schedules/{schedule_id}",
    response_model=ScheduleResponse,
    tags=["schedules"],
)
async def get_schedule(schedule_id: str):
    """Get a scheduled task."""
    schedule = await schedule_manager.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"schedule": schedule}


@router.delete(
    "/api/schedules/{schedule_id}",
    tags=["schedules"],
)
async def delete_schedule(schedule_id: str):
    """Delete a scheduled task."""
    schedule = await schedule_manager.delete_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"message": "Schedule deleted"}


@router.patch(
    "/api/schedules/{schedule_id}/toggle",
    response_model=ScheduleResponse,
    tags=["schedules"],
)
async def toggle_schedule(schedule_id: str):
    """Enable or disable a scheduled task."""
    schedule = await schedule_manager.toggle_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"schedule": schedule}


@router.post(
    "/api/generate/preview",
    response_model=PreviewResponse,
    tags=["generation"],
)
async def generate_preview(request: GenerateRequest):
    """Generate a preview synchronously (for quick previews)."""
    try:
        settings = get_settings()
        sample_file = request.sample_file or str(
            Path(__file__).resolve().parent.parent.parent / "samples" / "users.csv"
        )
        preview = build_generation_preview(
            sample_file=sample_file,
            table_name=request.table_name,
            rows=min(request.rows, 5),
            settings=settings,
        )
        return {
            "task_id": "sync",
            "preview": {
                "row_count": preview.profile.row_count,
                "columns": preview.profile.columns,
            },
            "fields": [f.model_dump() for f in preview.fields],
            "create_table_sql": preview.create_table_sql,
            "preview_rows": preview.preview_rows,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/api/samples",
    tags=["samples"],
)
async def list_samples():
    """List available sample files in the samples directory."""
    samples_dir = Path(__file__).resolve().parent.parent.parent / "samples"
    if not samples_dir.exists():
        return {"samples": []}
    allowed_extensions = {".csv", ".xlsx", ".xls"}
    files = []
    for f in sorted(samples_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in allowed_extensions:
            files.append({
                "name": f.name,
                "path": str(f.relative_to(Path(__file__).resolve().parent.parent.parent)),
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
    return {"samples": files}


@router.post(
    "/api/upload",
    tags=["upload"],
)
async def upload_file(file: UploadFile):
    """Upload a sample file."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Validate file extension
    allowed_extensions = {".csv", ".xlsx", ".xls"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}",
        )

    # Save to samples directory
    samples_dir = Path(__file__).resolve().parent.parent.parent / "samples"
    save_path = samples_dir / file.filename

    try:
        content = await file.read()
        async with aiofiles.open(save_path, "wb") as f:
            await f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    return {
        "message": "File uploaded successfully",
        "filename": file.filename,
        "filepath": str(save_path.relative_to(Path(__file__).resolve().parent.parent.parent)),
    }


@router.post(
    "/api/tasks/batch",
    response_model=BatchTaskCreateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["tasks"],
)
async def create_batch_tasks(
    background_tasks: BackgroundTasks,
    request: BatchTaskCreateRequest,
):
    """Create multiple generation tasks in batch."""
    from mockworkflow.utils.pinyin import filename_to_table_name

    task_ids = []
    for task_item in request.tasks:
        table_name = task_item.table_name
        if request.auto_table_name and (table_name == "auto_table" or not table_name):
            filename = Path(task_item.sample_filename).stem
            table_name = filename_to_table_name(filename) or "auto_table"

        task = await task_manager.create_task(
            sample_filename=task_item.sample_filename,
            table_name=table_name,
            rows=task_item.rows,
            enable_db_export=task_item.enable_db_export,
        )
        task_ids.append(task.id)
        # Start task processing in background
        background_tasks.add_task(process_task, task.id)

    return {
        "task_ids": task_ids,
        "message": f"Successfully created {len(task_ids)} tasks",
        "created_count": len(task_ids),
    }


@router.post(
    "/api/tasks/{task_id}/retry",
    tags=["tasks"],
)
async def retry_task_endpoint(task_id: str, background_tasks: BackgroundTasks):
    """Retry a failed task by dropping the table and re-running it."""
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if not task.retryable:
        raise HTTPException(status_code=400, detail="Task is not retryable")

    background_tasks.add_task(retry_task, task_id)
    return {"message": "Task retry queued", "task_id": task_id}


@router.post(
    "/api/tasks/batch-from-files",
    response_model=BatchTaskCreateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["tasks"],
)
async def create_batch_tasks_from_files(
    background_tasks: BackgroundTasks,
    files: list[UploadFile],
    rows: int = 100,
    enable_db_export: bool = False,
    table_prefix: str = "",
):
    """Create multiple tasks from uploaded files."""
    from mockworkflow.utils.pinyin import filename_to_table_name

    allowed_extensions = {".csv", ".xlsx", ".xls"}
    task_ids = []

    for file in files:
        if not file.filename:
            continue

        ext = Path(file.filename).suffix.lower()
        if ext not in allowed_extensions:
            continue

        # Save to samples directory
        samples_dir = Path(__file__).resolve().parent.parent.parent / "samples"
        save_path = samples_dir / file.filename

        try:
            content = await file.read()
            async with aiofiles.open(save_path, "wb") as f:
                await f.write(content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save file {file.filename}: {str(e)}")

        # Auto-generate table name from filename with optional prefix
        filename = Path(file.filename).stem
        base_name = filename_to_table_name(filename) or "auto_table"
        table_name = table_prefix + base_name if table_prefix else base_name

        task = await task_manager.create_task(
            sample_filename=str(save_path.relative_to(samples_dir.parent)),
            table_name=table_name,
            rows=rows,
            enable_db_export=enable_db_export,
        )
        task_ids.append(task.id)
        # Start task processing in background
        background_tasks.add_task(process_task, task.id)

    return {
        "task_ids": task_ids,
        "message": f"Successfully created {len(task_ids)} tasks from uploaded files",
        "created_count": len(task_ids),
    }


@router.get(
    "/api/tasks/stats/summary",
    tags=["tasks"],
)
async def get_task_statistics():
    """Get task statistics for charts."""
    from collections import Counter
    from datetime import date, timedelta

    tasks = await task_manager.list_tasks(limit=1000)

    # Status distribution
    status_counts = Counter(t.status for t in tasks)

    # Daily task counts (last 14 days)
    today = date.today()
    daily_counts = {}
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        daily_counts[d.isoformat()] = 0

    for t in tasks:
        created_date = t.created_at.date().isoformat()
        if created_date in daily_counts:
            daily_counts[created_date] += 1

    # Success rate
    total = len(tasks)
    completed = status_counts.get("completed", 0)
    failed = status_counts.get("failed", 0)
    success_rate = round(completed / total * 100, 1) if total > 0 else 0

    # Table name distribution (top 10)
    table_counts = Counter(t.table_name for t in tasks)
    top_tables = [{"name": name, "count": count} for name, count in table_counts.most_common(10)]

    # Average rows per task
    avg_rows = round(sum(t.rows for t in tasks) / total) if total > 0 else 0

    # Average completion time (in seconds)
    completion_times = []
    for t in tasks:
        if t.completed_at and t.started_at:
            delta = (t.completed_at - t.started_at).total_seconds()
            completion_times.append(delta)
    avg_completion_time = round(sum(completion_times) / len(completion_times), 1) if completion_times else 0

    return {
        "total_tasks": total,
        "status_distribution": {
            "pending": status_counts.get("pending", 0),
            "running": status_counts.get("running", 0),
            "completed": status_counts.get("completed", 0),
            "failed": status_counts.get("failed", 0),
            "cancelled": status_counts.get("cancelled", 0),
        },
        "daily_counts": [{"date": d, "count": c} for d, c in daily_counts.items()],
        "success_rate": success_rate,
        "top_tables": top_tables,
        "avg_rows": avg_rows,
        "avg_completion_time": avg_completion_time,
        "total_rows_generated": sum(
            (t.result_full.get("generated_rows", 0) or 0)
            for t in tasks if t.result_full and t.status == "completed"
        ),
    }


async def process_task(task_id: str):
    """Process a task in the background."""
    task = await task_manager.get_task(task_id)
    if not task:
        return

    try:
        await task_manager.update_task_status(task_id, TaskStatus.RUNNING, progress=10)

        settings = get_settings()
        sample_path = Path(task.sample_filename)
        if not sample_path.is_absolute():
            # Check relative to project root
            root = Path(__file__).resolve().parent.parent.parent
            sample_path = root / "samples" / task.sample_filename
            if not sample_path.is_file():
                sample_path = root / task.sample_filename

        if not sample_path.is_file():
            raise FileNotFoundError(f"Sample file not found: {task.sample_filename}")

        sample_file = str(sample_path)

        # Step 1: Build preview
        await task_manager.update_task_status(task_id, TaskStatus.RUNNING, progress=30)
        preview = build_generation_preview(
            sample_file=sample_file,
            table_name=task.table_name,
            rows=min(task.rows, 5),
            settings=settings,
        )

        preview_result = {
            "row_count": preview.profile.row_count,
            "columns": preview.profile.columns,
            "fields": [f.model_dump() for f in preview.fields],
            "create_table_sql": preview.create_table_sql,
            "preview_rows": preview.preview_rows,
            "llm_used": preview.llm_used,
            "llm_resolved_count": preview.llm_resolved_count,
            "rules_resolved_count": preview.rules_resolved_count,
        }

        # Step 2: Generate full output (if rows > 5)
        await task_manager.update_task_status(task_id, TaskStatus.RUNNING, progress=70)

        if task.enable_db_export:
            # Database export is gated by the master toggle. When the toggle is
            # disabled this raises a readable error and performs no DB operations.
            full_result = generate_to_output(
                sample_file=sample_file,
                table_name=task.table_name,
                rows=task.rows,
                output="mysql",
                settings=settings,
                preview=preview,
            )
            result = {
                **preview_result,
                "generated_rows": full_result.generated_rows,
                "output": full_result.output,
                "output_path": full_result.output_path,
            }
        elif task.rows <= 5:
            result = preview_result
        else:
            output_dir = Path(__file__).resolve().parent.parent.parent / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            csv_filename = f"{task.table_name}_{task_id[:8]}.csv"
            csv_path = str(output_dir / csv_filename)
            full_result = generate_to_output(
                sample_file=sample_file,
                table_name=task.table_name,
                rows=task.rows,
                output="csv",
                csv_path=csv_path,
                settings=settings,
                preview=preview,
            )
            result = {
                **preview_result,
                "generated_rows": full_result.generated_rows,
                "output": full_result.output,
                "output_path": full_result.output_path,
            }

        await task_manager.update_task_status(
            task_id,
            TaskStatus.COMPLETED,
            progress=100,
            result_preview=preview_result,
            result_full=result,
        )

    except TableSchemaMismatchError as e:
        traceback.print_exc()
        await task_manager.update_task_status(
            task_id,
            TaskStatus.FAILED,
            progress=0,
            error_message=str(e),
            schema_mismatch=True,
            retryable=True,
        )
    except Exception as e:
        traceback.print_exc()
        await task_manager.update_task_status(
            task_id,
            TaskStatus.FAILED,
            progress=0,
            error_message=str(e),
        )


async def retry_task(task_id: str):
    """Retry a failed task by dropping the table and re-running it."""
    task = await task_manager.get_task(task_id)
    if not task:
        return

    try:
        await task_manager.update_task_status(task_id, TaskStatus.RUNNING, progress=10)

        settings = get_settings()
        if not settings.mysql_url:
            raise ValueError("MySQL connection not configured")

        # Drop the existing table
        from sqlalchemy import create_engine, text
        engine = create_engine(settings.mysql_url)
        with engine.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS `{task.table_name}`"))

        # Re-run the task
        await process_task(task_id)

    except Exception as e:
        traceback.print_exc()
        await task_manager.update_task_status(
            task_id,
            TaskStatus.FAILED,
            progress=0,
            error_message=str(e),
        )


# === Web Routes (HTML) ===


@app.get("/login", response_class=HTMLResponse, tags=["web"])
async def login_page(request: Request, error: str = ""):
    """Serve the login page."""
    template = templates.env.get_template("login.html")
    content = template.render(error_message=error)
    return HTMLResponse(content=content)


@app.post("/login", response_class=HTMLResponse, tags=["web"])
async def login_submit(request: Request):
    """Handle login form submission."""
    form = await request.form()
    password = form.get("password", "")
    settings = get_settings()

    if settings.web_password and verify_password(settings.web_password, password):
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie("mockworkflow_session", password, max_age=86400 * 7)  # 7 days
        return response
    else:
        template = templates.env.get_template("login.html")
        content = template.render(error_message="密码错误")
        return HTMLResponse(content=content, status_code=401)


@app.get("/", response_class=HTMLResponse, tags=["web"])
async def index(request: Request):
    """Serve the main page."""
    template = templates.env.get_template("index.html")
    content = template.render()
    return HTMLResponse(content=content)


@app.on_event("startup")
async def startup_event():
    """Start the scheduler on application startup."""
    await scheduler.start()


@app.on_event("shutdown")
async def shutdown_event():
    """Stop the scheduler on application shutdown."""
    await scheduler.stop()


# Include router
app.include_router(router)

