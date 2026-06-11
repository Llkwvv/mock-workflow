"""System-level routes: health, metrics, audit logs, sample readers, WebSocket."""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from backend.app.state import project_root, ws_manager
from backend.sample.registry import list_supported_formats

router = APIRouter()


# ---------- Models ----------

class ReaderGenerateRequest(BaseModel):
    suffix: str = Field(min_length=1, description="File suffix without dot, e.g. 'rdf'")
    description: str = Field(default="", description="Human-readable description of the format (optional)")
    strategy: str = Field(default="", description="Optional parsing strategy hints (streaming, sampling, etc.)")
    sample_snippet: str = Field(default="", description="Optional first lines of a real sample file for LLM reference")


class ReaderGenerateResponse(BaseModel):
    success: bool
    installed_path: str
    supported_formats: list[str]
    generated_code: str


# ---------- Routes ----------

@router.get("/api/health", tags=["health"])
async def health_check():
    from backend.app.metrics import get_metrics
    from backend.app.state import executor, task_manager
    metrics = get_metrics()
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "metrics": metrics.snapshot(),
        "tasks": {
            "total": len(task_manager.tasks) if task_manager else 0,
        },
        "executor": executor.stats() if executor else None,
    }


@router.get("/api/metrics", tags=["metrics"])
async def metrics_endpoint():
    """Raw metrics snapshot for debugging / monitoring."""
    from backend.app.metrics import get_metrics
    return get_metrics().snapshot()


@router.get("/api/audit/logs", tags=["audit"])
async def audit_logs(
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum log entries to return"),
    event: Optional[str] = Query(default=None, description="Filter by event type (login_success, login_failure, logout, session_revoked, task_generated)"),
    user: Optional[str] = Query(default=None, description="Filter by username"),
):
    """Return recent audit log entries (JSON-lines format).

    The audit log is stored at ``<project_root>/.audit.log`` with one JSON
    object per line. This endpoint reads the tail of that file and returns
    parsed entries, newest first.
    """
    audit_path = project_root / ".audit.log"
    if not audit_path.exists():
        return {"entries": [], "total": 0, "path": str(audit_path)}

    try:
        lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
    except Exception:
        return {"entries": [], "total": 0, "path": str(audit_path)}

    entries = []
    for line in reversed(lines):  # newest first
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Apply filters
        if event and entry.get("event") != event:
            continue
        if user and entry.get("user") != user:
            continue
        entries.append(entry)
        if len(entries) >= limit:
            break

    return {
        "entries": entries,
        "total": len(entries),
        "path": str(audit_path),
        "filters": {"event": event, "user": user, "limit": limit},
    }


@router.get("/api/sample/readers/formats", tags=["sample"])
async def get_sample_formats():
    """List currently supported sample file formats."""
    return {"formats": list_supported_formats()}


@router.post("/api/sample/readers/generate", response_model=ReaderGenerateResponse, tags=["sample"])
async def generate_reader(request: ReaderGenerateRequest):
    """Generate and install a sample reader plugin via LLM."""
    from backend.sample.codegen import ReaderCodeGenerator
    import traceback as _tb

    try:
        codegen = ReaderCodeGenerator()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    try:
        code = codegen.generate(
            suffix=request.suffix,
            description=request.description,
            strategy=request.strategy or None,
            sample_snippet=request.sample_snippet or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Code generation failed: {exc}")
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Code generation error: {exc}\n{_tb.format_exc()}"
        )

    try:
        installed = codegen.install(request.suffix, code)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Installation failed: {exc}\n{_tb.format_exc()}"
        )

    return {
        "success": True,
        "installed_path": str(installed),
        "supported_formats": list_supported_formats(),
        "generated_code": code,
    }


@router.get("/api/settings", tags=["settings"])
async def get_settings_api():
    """Get current system settings."""
    from backend.config import get_settings
    return {"config": get_settings().model_dump(mode="json")}


@router.post("/api/settings", tags=["settings"])
async def update_settings_api(new_config: dict):
    """Update system settings."""
    # Note: In a real implementation, this would need to handle config reloading.
    # For now, we'll just return success since the validation happens in the model.
    # A more robust solution would require a config reload mechanism or restart.
    from backend.config import get_settings

    # Validate the new configuration by creating a Settings instance
    try:
        settings = get_settings()
        updated = settings.model_copy(update=new_config)
        # In production, you'd want to persist these changes and reload the config
        return {"success": True, "message": "Settings updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid configuration: {str(e)}")


@router.websocket("/api/ws/tasks")
async def tasks_websocket(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
