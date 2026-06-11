"""Data generation preview endpoints."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.config import get_settings
from backend.services.generation import build_generation_preview
from backend.app.deps import SAMPLES_DIR

router = APIRouter()


class GenerateRequest(BaseModel):
    sample_file: str | None = None
    rows: int = Field(default=100, gt=0, le=100000)
    table_name: str = Field(default="auto_table")
    enable_db_export: bool = Field(default=False)


class PreviewResponse(BaseModel):
    task_id: str
    preview: dict
    fields: list[dict]
    create_table_sql: str
    preview_rows: list[dict]


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
