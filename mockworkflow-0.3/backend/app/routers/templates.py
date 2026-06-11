"""Template management endpoints backed by SQLite."""
import sqlite3
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.deps import DB_PATH

router = APIRouter()


def _init_templates_table() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS templates (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            sample_filename TEXT NOT NULL,
            rows INTEGER NOT NULL,
            output TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


_init_templates_table()


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


@router.post("/api/templates", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED, tags=["templates"])
async def create_template(request: TemplateCreateRequest):
    template_id = f"tmpl_{uuid.uuid4().hex}"
    created_at = datetime.now().isoformat()
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO templates (id, name, sample_filename, rows, output, description, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (template_id, request.name, request.sample_filename, request.rows, request.output, request.description, created_at),
    )
    conn.commit()
    conn.close()
    return {
        "id": template_id,
        "name": request.name,
        "sample_filename": request.sample_filename,
        "rows": request.rows,
        "output": request.output,
        "description": request.description,
        "created_at": created_at,
    }


@router.get("/api/templates", response_model=TemplateListResponse, tags=["templates"])
async def list_templates():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.execute("SELECT * FROM templates ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    templates = [
        {
            "id": row[0],
            "name": row[1],
            "sample_filename": row[2],
            "rows": row[3],
            "output": row[4],
            "description": row[5],
            "created_at": row[6],
        }
        for row in rows
    ]
    return {"templates": templates}


@router.get("/api/templates/{template_id}", response_model=TemplateResponse, tags=["templates"])
async def get_template(template_id: str):
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.execute("SELECT * FROM templates WHERE id = ?", (template_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    return {
        "id": row[0],
        "name": row[1],
        "sample_filename": row[2],
        "rows": row[3],
        "output": row[4],
        "description": row[5],
        "created_at": row[6],
    }


@router.delete("/api/templates/{template_id}", tags=["templates"])
async def delete_template(template_id: str):
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.execute("DELETE FROM templates WHERE id = ?", (template_id,))
    conn.commit()
    deleted = cursor.rowcount
    conn.close()
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"message": "Template deleted"}
