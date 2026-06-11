"""Schedule management endpoints."""
from datetime import datetime

from croniter import croniter
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from backend.app.deps import schedule_manager
from backend.app.scheduler import ScheduleInfo

router = APIRouter()


class ScheduleCreateRequest(BaseModel):
    sample_filename: str = Field(min_length=1)
    table_name: str = Field(default="auto_table", min_length=1)
    rows: int = Field(default=100, gt=0, le=100000)
    enable_db_export: bool = Field(default=False)
    cron: str = Field(min_length=9)

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, v: str) -> str:
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


class NlpScheduleRequest(BaseModel):
    description: str = Field(min_length=1, description="Natural language schedule description")


class NlpScheduleResponse(BaseModel):
    cron: str
    description: str
    confidence: str


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


@router.post("/api/schedules/nlp", response_model=NlpScheduleResponse, tags=["schedules"])
async def parse_schedule_nlp(request: NlpScheduleRequest):
    """Parse a natural language schedule description into a cron expression."""
    from backend.agent.tools.nlp_schedule import parse_schedule_nlp as _parse_nlp
    from backend.config import get_settings
    settings = get_settings()
    result = _parse_nlp(request.description, settings)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return {
        "cron": result.get("cron", ""),
        "description": result.get("description", ""),
        "confidence": result.get("confidence", "low"),
    }
