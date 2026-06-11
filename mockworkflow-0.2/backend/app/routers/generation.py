"""Generation routes: preview, samples list, upload."""
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import APIRouter, UploadFile
from pydantic import BaseModel, Field

from backend.app.exceptions import SampleNotFoundError, ValidationError
from backend.app.state import project_root, SAMPLES_DIR
from backend.config import get_settings
from backend.services.generation import build_generation_preview

router = APIRouter()


# ---------- Models ----------

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


# ---------- Routes ----------

@router.post("/api/generate/preview", response_model=PreviewResponse, tags=["generation"])
async def generate_preview(request: GenerateRequest):
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


@router.get("/api/samples", tags=["samples"])
async def list_samples():
    samples_dir = SAMPLES_DIR
    if not samples_dir.exists():
        return {"samples": []}
    allowed_extensions = {".csv", ".xlsx", ".xls", ".sql"}
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
        raise ValidationError(message="No filename provided")
    allowed_extensions = {".csv", ".xlsx", ".xls", ".sql"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_extensions:
        raise ValidationError(
            message="Invalid file type.",
            detail={"allowed": list(allowed_extensions), "received": ext}
        )

    samples_dir = SAMPLES_DIR
    save_path = samples_dir / file.filename
    try:
        content = await file.read()
        async with aiofiles.open(save_path, "wb") as f:
            await f.write(content)
    except Exception as e:
        raise ValidationError(message=f"Failed to save file: {file.filename}", detail={"error": str(e)})

    return {
        "message": "File uploaded successfully",
        "filename": file.filename,
        "filepath": str(save_path.relative_to(project_root)),
    }
