
"""FastAPI web application for MockAgent."""
import asyncio
import json
import shutil
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from mockagent.config import get_settings
from mockagent.services.generation import build_generation_preview, generate_to_output
from mockagent.schemas.field import FieldSpec
from mockagent.web.task_manager import TaskInfo, TaskManager, TaskStatus, task_manager

# Setup
BASE_DIR = Path(__file__).resolve().parent
project_root = BASE_DIR.parent.parent
templates_dir = BASE_DIR / "templates"
static_dir = BASE_DIR / "static"

templates_dir.mkdir(parents=True, exist_ok=True)
static_dir.mkdir(parents=True, exist_ok=True)


app = FastAPI(
    title="MockAgent Web",
    description="Web interface for MockAgent - sample-driven mock data generation",
    version="0.1.0",
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Mount output directory for CSV downloads
output_dir = project_root / "output"
output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/output", StaticFiles(directory=str(output_dir)), name="output")

# Templates
templates = Jinja2Templates(directory=str(templates_dir))
templates.env.bytecode_cache = None


# === API Models ===

class TaskCreateRequest(BaseModel):
    sample_filename: str = Field(min_length=1, description="Path to the sample data file")
    table_name: str = Field(default="auto_table", min_length=1, description="Target table name")
    rows: int = Field(default=100, gt=0, le=100000, description="Number of mock rows to generate")

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


# === API Routes ===

router = APIRouter()


@router.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


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

        if task.rows <= 5:
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

    except Exception as e:
        traceback.print_exc()
        await task_manager.update_task_status(
            task_id,
            TaskStatus.FAILED,
            progress=0,
            error_message=str(e),
        )


# === Web Routes (HTML) ===


@app.get("/", response_class=HTMLResponse, tags=["web"])
async def index(request: Request):
    """Serve the main page."""
    template = templates.env.get_template("index.html")
    content = template.render()
    return HTMLResponse(content=content)


# Include router
app.include_router(router)

