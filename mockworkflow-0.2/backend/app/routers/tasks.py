"""Task routes: CRUD, batch, retry, stats."""
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Request, UploadFile, status
from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.exceptions import TaskNotFoundError, ValidationError
from backend.app.state import executor, project_root, SAMPLES_DIR, task_manager
from backend.app.task_manager import TaskInfo, TaskStatus
from backend.app import processor

router = APIRouter()


# ---------- Models ----------

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


# ---------- Routes ----------

@router.post("/api/tasks", response_model=TaskCreateResponse, status_code=status.HTTP_201_CREATED, tags=["tasks"])
async def create_task(request: TaskCreateRequest, req: Request):
    task = await task_manager.create_task(
        sample_filename=request.sample_filename,
        table_name=request.table_name,
        rows=request.rows,
        enable_db_export=request.enable_db_export,
    )
    await executor.submit(task.id, processor.process_task(task.id))
    # Audit log: record who created this generation task
    from backend.app.auth import get_current_username, get_audit_logger
    from backend.app.metrics import get_metrics
    username = get_current_username(req)
    audit = get_audit_logger()
    audit.task_generated(
        user_label=username,
        sample=request.sample_filename,
        table=request.table_name,
        rows=request.rows,
        task_id=task.id,
    )
    get_metrics().inc("tasks_created")
    return {"task_id": task.id, "message": "Task created and queued for processing"}


@router.get("/api/tasks/{task_id}", response_model=TaskResponse, tags=["tasks"])
async def get_task(task_id: str):
    task = await task_manager.get_task(task_id)
    if not task:
        raise TaskNotFoundError()
    return {"task": task}


@router.get("/api/tasks", response_model=TaskListResponse, tags=["tasks"])
async def list_tasks(limit: int = 50):
    tasks = await task_manager.list_tasks(limit=limit)
    return {"tasks": tasks, "total": len(tasks)}


@router.delete("/api/tasks/{task_id}", tags=["tasks"])
async def cancel_task(task_id: str):
    task = await task_manager.cancel_task(task_id)
    if not task:
        raise TaskNotFoundError()
    await executor.cancel(task_id)
    return {"message": "Task cancelled"}


@router.post("/api/tasks/batch", response_model=BatchTaskCreateResponse, status_code=status.HTTP_201_CREATED, tags=["tasks"])
async def create_batch_tasks(request: BatchTaskCreateRequest, req: Request):
    from backend.utils.pinyin import filename_to_table_name
    from backend.app.auth import get_current_username, get_audit_logger
    username = get_current_username(req)
    audit = get_audit_logger()
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
        await executor.submit(task.id, processor.process_task(task.id))
        # Audit each task in the batch
        audit.task_generated(
            user_label=username,
            sample=task_item.sample_filename,
            table=table_name,
            rows=task_item.rows,
            task_id=task.id,
        )

    return {
        "task_ids": task_ids,
        "message": f"Successfully created {len(task_ids)} tasks",
        "created_count": len(task_ids),
    }


@router.post("/api/tasks/{task_id}/retry", tags=["tasks"])
async def retry_task_endpoint(task_id: str):
    task = await task_manager.get_task(task_id)
    if not task:
        raise TaskNotFoundError()
    if not task.retryable:
        raise ValidationError(message="Task is not retryable", detail={"task_id": task_id})
    await executor.submit(task_id, processor.retry_task(task_id))
    return {"message": "Task retry queued", "task_id": task_id}


@router.post("/api/tasks/batch-from-files", response_model=BatchTaskCreateResponse, status_code=status.HTTP_201_CREATED, tags=["tasks"])
async def create_batch_tasks_from_files(
    files: list[UploadFile],
    req: Request,
    rows: int = 100,
    enable_db_export: bool = False,
    table_prefix: str = "",
):
    from backend.utils.pinyin import filename_to_table_name
    from backend.app.auth import get_current_username, get_audit_logger
    username = get_current_username(req)
    audit = get_audit_logger()
    allowed_extensions = {".csv", ".xlsx", ".xls", ".sql"}
    task_ids = []

    for file in files:
        if not file.filename:
            continue
        ext = Path(file.filename).suffix.lower()
        if ext not in allowed_extensions:
            continue

        samples_dir = SAMPLES_DIR
        save_path = samples_dir / file.filename
        import aiofiles
        try:
            content = await file.read()
            async with aiofiles.open(save_path, "wb") as f:
                await f.write(content)
        except Exception as e:
            raise ValidationError(message=f"Failed to save file {file.filename}", detail={"error": str(e)})

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
        await executor.submit(task.id, processor.process_task(task.id))
        # Audit each uploaded file task
        audit.task_generated(
            user_label=username,
            sample=file.filename,
            table=table_name,
            rows=rows,
            task_id=task.id,
        )

    return {
        "task_ids": task_ids,
        "message": f"Successfully created {len(task_ids)} tasks from uploaded files",
        "created_count": len(task_ids),
    }


@router.get("/api/tasks/stats/summary", tags=["tasks"])
async def get_task_statistics():
    from collections import Counter
    from datetime import date, timedelta

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
