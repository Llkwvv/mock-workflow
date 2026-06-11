"""Sample file upload, listing, and reader generation endpoints."""
import json
from datetime import datetime
from pathlib import Path

import aiofiles
from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.app.deps import SAMPLES_DIR, project_root
from backend.config import get_settings
from backend.sample.codegen import ReaderCodeGenerator
from backend.sample.profiler import analyze_sample_file
from backend.sample.registry import list_supported_formats

router = APIRouter()


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


@router.get("/api/sample/readers/formats", tags=["sample"])
async def get_sample_formats():
    """List currently supported sample file formats."""
    return {"formats": list_supported_formats()}


@router.post("/api/sample/readers/generate", response_model=ReaderGenerateResponse, tags=["sample"])
async def generate_reader(request: ReaderGenerateRequest):
    """Generate and install a sample reader plugin via LLM."""
    try:
        codegen = ReaderCodeGenerator()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    import traceback as _tb

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

    # File size guard: reject files larger than 100 MB
    MAX_FILE_SIZE = 100 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum allowed is 100 MB.")

    samples_dir = SAMPLES_DIR
    save_path = samples_dir / file.filename
    try:
        async with aiofiles.open(save_path, "wb") as f:
            await f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Auto-annotate uploaded sample
    annotation = {}
    try:
        from backend.agent.tools.sample_annotation import auto_annotate
        profile = analyze_sample_file(str(save_path))
        annotation = auto_annotate(
            file_name=file.filename,
            columns=profile.columns,
            sample_rows=profile.samples,
            settings=get_settings(),
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[upload] auto-annotation failed: {e}")

    return {
        "message": "File uploaded successfully",
        "filename": file.filename,
        "filepath": str(save_path.relative_to(project_root)),
        "annotation": annotation,
    }
