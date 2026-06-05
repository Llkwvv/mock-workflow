"""FastAPI backend for Mockworkflow (frontend/backend split)."""
import asyncio
import json
import shutil
import tempfile
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

import aiofiles
from collections import Counter
from fastapi import (
    APIRouter, BackgroundTasks, FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, status
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

# Use local backend core modules
import sys
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from backend.config import get_settings
from backend.services.generation import build_generation_preview, generate_to_output
from backend.schemas.field import FieldSpec
from backend.output.db_writer import TableSchemaMismatchError

from backend.app.task_manager import TaskInfo, TaskManager, TaskStatus
from backend.app.scheduler import ScheduleInfo, ScheduleManager, Scheduler
from backend.app.auth import AuthMiddleware, verify_password
from backend.app import processor

# Paths
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent.parent / "frontend"
OUTPUT_DIR = project_root / "output"
SAMPLES_DIR = project_root / "samples"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Mockworkflow API",
    description="Backend API for Mockworkflow - sample-driven mock data generation",
    version="0.2.0",
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


# === WebSocket Connection Manager ===
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


ws_manager = ConnectionManager()
task_manager = TaskManager(broadcast_fn=ws_manager.broadcast)
schedule_manager = ScheduleManager(
    task_manager=task_manager,
    broadcast_fn=ws_manager.broadcast
)
scheduler = Scheduler(schedule_manager, task_manager)


# === API Models ===
class TaskCreateRequest(BaseModel):
    sample_filename: str = Field(min_length=1)
    table_name: str = Field(default="auto_table", min_length=1)
    rows: int = Field(default=100, gt=0, le=100000)
    enable_db_export: bool = Field(default=False)

    @field_validator("sample_filename")
    @classmethod
    def validate_sample_file(cls, v: str) -> str:
        path = Path(v)
        if not path.is_file():
            samples_path = SAMPLES_DIR / v
            if not samples_path.is_file():
                raise ValueError(f"Sample file not found: {v}")
        return v

    @model_validator(mode="after")
    def auto_generate_table_name(self) -> "TaskCreateRequest":
        if self.table_name in ("auto_table", "", None):
            filename = Path(self.sample_filename).stem
            from backend.utils.pinyin import filename_to_table_name
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
    sample_filename: str = Field(min_length=1)
    table_name: str = Field(default="auto_table", min_length=1)
    rows: int = Field(default=100, gt=0, le=100000)
    enable_db_export: bool = Field(default=False)

    @field_validator("sample_filename")
    @classmethod
    def validate_sample_file(cls, v: str) -> str:
        path = Path(v)
        if not path.is_file():
            samples_path = SAMPLES_DIR / v
            if not samples_path.is_file():
                raise ValueError(f"Sample file not found: {v}")
        return v


class BatchTaskCreateRequest(BaseModel):
    tasks: List[BatchTaskCreateItem] = Field(min_items=1, max_items=100)
    auto_table_name: bool = Field(default=True)


class BatchTaskCreateResponse(BaseModel):
    task_ids: List[str]
    message: str
    created_count: int


class ScheduleCreateRequest(BaseModel):
    sample_filename: str = Field(min_length=1)
    table_name: str = Field(default="auto_table", min_length=1)
    rows: int = Field(default=100, gt=0, le=100000)
    enable_db_export: bool = Field(default=False)
    cron: str = Field(min_length=9)

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, v: str) -> str:
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


class SchemaConnectRequest(BaseModel):
    host: str = Field(min_length=1)
    database: str = Field(min_length=1)
    user: str = Field(min_length=1)
    password: str


class TableInfo(BaseModel):
    name: str
    columns: int
    rows: int


class SchemaTablesResponse(BaseModel):
    tables: list[TableInfo]


class SchemaGenerateRequest(BaseModel):
    host: str = Field(min_length=1)
    database: str = Field(min_length=1)
    user: str = Field(min_length=1)
    password: str
    table_name: str = Field(min_length=1)
    rows: int = Field(default=100, gt=0, le=100000)
    output: str = Field(default="preview")  # preview, csv, mysql


class SchemaGenerateResponse(BaseModel):
    task_id: str
    message: str


class TemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    sample_filename: str = Field(min_length=1)
    rows: int = Field(default=100, gt=0, le=100000)
    output: str = Field(default="preview")
    description: str = Field(default="")


class TemplateResponse(BaseModel):
    id: str
    name: str
    sample_filename: str
    rows: int
    output: str
    description: str
    created_at: str


class TemplateListResponse(BaseModel):
    templates: list[TemplateResponse]


# === API Routes ===
router = APIRouter()


@router.get("/api/health", tags=["health"])
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@router.websocket("/api/ws/tasks")
async def tasks_websocket(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@router.post("/api/tasks", response_model=TaskCreateResponse, status_code=status.HTTP_201_CREATED, tags=["tasks"])
async def create_task(background_tasks: BackgroundTasks, request: TaskCreateRequest):
    task = await task_manager.create_task(
        sample_filename=request.sample_filename,
        table_name=request.table_name,
        rows=request.rows,
        enable_db_export=request.enable_db_export,
    )
    background_tasks.add_task(processor.process_task, task.id)
    return {"task_id": task.id, "message": "Task created and queued for processing"}


@router.get("/api/tasks/{task_id}", response_model=TaskResponse, tags=["tasks"])
async def get_task(task_id: str):
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": task}


@router.get("/api/tasks", response_model=TaskListResponse, tags=["tasks"])
async def list_tasks(limit: int = 50):
    tasks = await task_manager.list_tasks(limit=limit)
    return {"tasks": tasks, "total": len(tasks)}


@router.delete("/api/tasks/{task_id}", tags=["tasks"])
async def cancel_task(task_id: str):
    task = await task_manager.cancel_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task cancelled"}


# === Schedule API Routes ===
@router.post("/api/schedules", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED, tags=["schedules"])
async def create_schedule(request: ScheduleCreateRequest):
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


@router.get("/api/schedules", response_model=ScheduleListResponse, tags=["schedules"])
async def list_schedules():
    schedules = await schedule_manager.list_schedules()
    return {"schedules": schedules, "total": len(schedules)}


@router.get("/api/schedules/{schedule_id}", response_model=ScheduleResponse, tags=["schedules"])
async def get_schedule(schedule_id: str):
    schedule = await schedule_manager.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"schedule": schedule}


@router.delete("/api/schedules/{schedule_id}", tags=["schedules"])
async def delete_schedule(schedule_id: str):
    schedule = await schedule_manager.delete_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"message": "Schedule deleted"}


@router.patch("/api/schedules/{schedule_id}/toggle", response_model=ScheduleResponse, tags=["schedules"])
async def toggle_schedule(schedule_id: str):
    schedule = await schedule_manager.toggle_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"schedule": schedule}


@router.post("/api/generate/preview", response_model=PreviewResponse, tags=["generation"])
async def generate_preview(request: GenerateRequest):
    try:
        settings = get_settings()
        sample_file = request.sample_file or str(SAMPLES_DIR / "users.csv")
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


@router.get("/api/samples", tags=["samples"])
async def list_samples():
    samples_dir = SAMPLES_DIR
    if not samples_dir.exists():
        return {"samples": []}
    allowed_extensions = {".csv", ".xlsx", ".xls"}
    files = []
    for f in sorted(samples_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in allowed_extensions:
            files.append({
                "name": f.name,
                "path": str(f.relative_to(project_root)),
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
    return {"samples": files}


@router.post("/api/upload", tags=["upload"])
async def upload_file(file: UploadFile):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    allowed_extensions = {".csv", ".xlsx", ".xls"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}")

    samples_dir = SAMPLES_DIR
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
        "filepath": str(save_path.relative_to(project_root)),
    }


@router.post("/api/tasks/batch", response_model=BatchTaskCreateResponse, status_code=status.HTTP_201_CREATED, tags=["tasks"])
async def create_batch_tasks(background_tasks: BackgroundTasks, request: BatchTaskCreateRequest):
    from backend.utils.pinyin import filename_to_table_name
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
        background_tasks.add_task(process_task, task.id)

    return {
        "task_ids": task_ids,
        "message": f"Successfully created {len(task_ids)} tasks",
        "created_count": len(task_ids),
    }


@router.post("/api/tasks/{task_id}/retry", tags=["tasks"])
async def retry_task_endpoint(task_id: str, background_tasks: BackgroundTasks):
    task = await task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not task.retryable:
        raise HTTPException(status_code=400, detail="Task is not retryable")
    background_tasks.add_task(processor.retry_task, task_id)
    return {"message": "Task retry queued", "task_id": task_id}


@router.post("/api/tasks/batch-from-files", response_model=BatchTaskCreateResponse, status_code=status.HTTP_201_CREATED, tags=["tasks"])
async def create_batch_tasks_from_files(
    background_tasks: BackgroundTasks,
    files: list[UploadFile],
    rows: int = 100,
    enable_db_export: bool = False,
    table_prefix: str = "",
):
    from backend.utils.pinyin import filename_to_table_name
    allowed_extensions = {".csv", ".xlsx", ".xls"}
    task_ids = []

    for file in files:
        if not file.filename:
            continue
        ext = Path(file.filename).suffix.lower()
        if ext not in allowed_extensions:
            continue

        samples_dir = SAMPLES_DIR
        save_path = samples_dir / file.filename
        try:
            content = await file.read()
            async with aiofiles.open(save_path, "wb") as f:
                await f.write(content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save file {file.filename}: {str(e)}")

        filename = Path(file.filename).stem
        base_name = filename_to_table_name(filename) or "auto_table"
        table_name = table_prefix + base_name if table_prefix else base_name

        task = await task_manager.create_task(
            sample_filename=str(save_path.relative_to(project_root)),
            table_name=table_name,
            rows=rows,
            enable_db_export=enable_db_export,
        )
        task_ids.append(task.id)
        background_tasks.add_task(processor.process_task, task.id)

    return {
        "task_ids": task_ids,
        "message": f"Successfully created {len(task_ids)} tasks from uploaded files",
        "created_count": len(task_ids),
    }


@router.post("/api/schema/tables", response_model=SchemaTablesResponse, tags=["schema"])
async def list_schema_tables(request: SchemaConnectRequest):
    """Connect to MySQL and list all tables with column counts."""
    import pymysql
    from pymysql import Error

    # Parse host (may include port like "localhost:3306")
    if ":" in request.host:
        host, port = request.host.split(":", 1)
        port = int(port)
    else:
        host = request.host
        port = 3306

    tables = []
    try:
        connection = pymysql.connect(
            host=host,
            port=port,
            user=request.user,
            password=request.password,
            database=request.database,
            connect_timeout=5
        )
        with connection.cursor() as cursor:
            # Get all tables
            cursor.execute("SHOW TABLES")
            table_names = [row[0] for row in cursor.fetchall()]

            # Get column count and row count for each table
            for table_name in table_names:
                cursor.execute(f"DESCRIBE `{table_name}`")
                columns = cursor.rowcount
                cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
                rows = cursor.fetchone()[0]
                tables.append(TableInfo(name=table_name, columns=columns, rows=rows))

        connection.close()
        return {"tables": tables}
    except Error as e:
        raise HTTPException(status_code=400, detail=f"MySQL connection failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.post("/api/schema/generate", response_model=SchemaGenerateResponse, status_code=status.HTTP_201_CREATED, tags=["schema"])
async def generate_from_schema(background_tasks: BackgroundTasks, request: SchemaGenerateRequest):
    """Generate mock data from a MySQL table schema."""
    import pymysql
    from pymysql import Error
    import csv
    import uuid

    # Parse host (may include port like "localhost:3306")
    if ":" in request.host:
        host, port = request.host.split(":", 1)
        port = int(port)
    else:
        host = request.host
        port = 3306

    try:
        connection = pymysql.connect(
            host=host,
            port=port,
            user=request.user,
            password=request.password,
            database=request.database,
            connect_timeout=5
        )
        with connection.cursor() as cursor:
            # Get table structure
            cursor.execute(f"DESCRIBE `{request.table_name}`")
            columns_info = cursor.fetchall()
            column_names = [col[0] for col in columns_info]

            # Try to get some sample rows (up to 5) to use as sample data
            cursor.execute(f"SELECT * FROM `{request.table_name}` LIMIT 5")
            sample_rows = cursor.fetchall()

        connection.close()

        # Create a temporary sample CSV file from the schema
        samples_dir = SAMPLES_DIR
        samples_dir.mkdir(parents=True, exist_ok=True)

        # Generate a unique filename for the schema-based sample
        sample_filename = f"schema_{request.database}_{request.table_name}_{uuid.uuid4().hex[:8]}.csv"
        sample_path = samples_dir / sample_filename

        with open(sample_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(column_names)  # Write header
            # Write sample rows if available, otherwise just header
            for row in sample_rows:
                writer.writerow(row)

        # Create a task using the generated sample file
        task = await task_manager.create_task(
            sample_filename=str(sample_path.relative_to(project_root)),
            table_name=request.table_name,
            rows=request.rows,
            enable_db_export=(request.output == "mysql"),
        )
        background_tasks.add_task(processor.process_task, task.id)

        return {
            "task_id": task.id,
            "message": f"Schema-based generation task created for table {request.table_name}"
        }

    except Error as e:
        raise HTTPException(status_code=400, detail=f"MySQL connection failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


# === Template API Routes ===
TEMPLATES_FILE = project_root / "templates.json"


def _load_templates() -> list[dict]:
    """Load templates from JSON file."""
    if not TEMPLATES_FILE.exists():
        return []
    try:
        with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_templates(templates: list[dict]):
    """Save templates to JSON file."""
    with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)


@router.post("/api/templates", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED, tags=["templates"])
async def create_template(request: TemplateCreateRequest):
    """Create a new template."""
    templates = _load_templates()
    template_id = f"tmpl_{uuid.uuid4().hex}"
    template = {
        "id": template_id,
        "name": request.name,
        "sample_filename": request.sample_filename,
        "rows": request.rows,
        "output": request.output,
        "description": request.description,
        "created_at": datetime.now().isoformat(),
    }
    templates.append(template)
    _save_templates(templates)
    return template


@router.get("/api/templates", response_model=TemplateListResponse, tags=["templates"])
async def list_templates():
    """List all templates."""
    templates = _load_templates()
    return {"templates": templates}


@router.get("/api/templates/{template_id}", response_model=TemplateResponse, tags=["templates"])
async def get_template(template_id: str):
    """Get a specific template by ID."""
    templates = _load_templates()
    for template in templates:
        if template["id"] == template_id:
            return template
    raise HTTPException(status_code=404, detail="Template not found")


@router.delete("/api/templates/{template_id}", tags=["templates"])
async def delete_template(template_id: str):
    """Delete a template by ID."""
    templates = _load_templates()
    original_count = len(templates)
    templates = [t for t in templates if t["id"] != template_id]
    if len(templates) == original_count:
        raise HTTPException(status_code=404, detail="Template not found")
    _save_templates(templates)
    return {"message": "Template deleted"}


@router.get("/api/tasks/stats/summary", tags=["tasks"])
async def get_task_statistics():
    tasks = await task_manager.list_tasks(limit=1000)
    status_counts = Counter(t.status for t in tasks)
    today = date.today()
    daily_counts = {}
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        daily_counts[d.isoformat()] = 0
    for t in tasks:
        created_date = t.created_at.date().isoformat()
        if created_date in daily_counts:
            daily_counts[created_date] += 1

    total = len(tasks)
    completed = status_counts.get("completed", 0)
    failed = status_counts.get("failed", 0)
    success_rate = round(completed / total * 100, 1) if total > 0 else 0
    table_counts = Counter(t.table_name for t in tasks)
    top_tables = [{"name": name, "count": count} for name, count in table_counts.most_common(10)]
    avg_rows = round(sum(t.rows for t in tasks) / total) if total > 0 else 0
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


# === Startup / Shutdown ===
@app.on_event("startup")
async def startup_event():
    processor.set_globals(task_manager, project_root)
    await scheduler.start()


@app.on_event("shutdown")
async def shutdown_event():
    await scheduler.stop()


# Include router (API routes must be registered before static file mount)
app.include_router(router)

# Mount frontend static files last so API routes take precedence
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
