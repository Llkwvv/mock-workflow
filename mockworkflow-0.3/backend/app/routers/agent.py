"""Agent-powered conversational and tool endpoints."""
from fastapi import APIRouter, HTTPException, WebSocket
from pydantic import BaseModel, Field

from backend.config import get_settings

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


@router.post("/api/chat", tags=["chat"])
async def chat_endpoint(request: dict):
    """Conversational entry for mock data generation configuration."""
    from backend.agent.chat import chat_message
    settings = get_settings()
    history = request.get("history", [])
    message = request.get("message", "")
    result = chat_message(history, message, settings)
    return result


@router.websocket("/api/ws/chat")
async def chat_websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time chat with the agent."""
    from backend.agent.chat_endpoint import chat_websocket
    await chat_websocket(websocket)


@router.post("/api/explain", tags=["agent"])
async def explain_generation(request: dict):
    """Explain a generation result in natural language."""
    from backend.agent.tools.explanation import explain_result
    result = request.get("result", {})
    return {"explanation": explain_result(result)}


@router.post("/api/few-shot", tags=["agent"])
async def few_shot_recommend(request: dict):
    """Recommend similar past tasks as few-shot examples."""
    from backend.agent.tools.few_shot import recommend_few_shot
    current_file = request.get("current_file", "")
    current_columns = request.get("current_columns", [])
    history = request.get("history", [])
    recommendations = recommend_few_shot(current_file, current_columns, history)
    return {"recommendations": recommendations}


@router.post("/api/samples/cluster", tags=["agent"])
async def cluster_samples_endpoint(request: dict):
    """Cluster uploaded samples by semantic similarity."""
    from backend.agent.tools.sample_cluster import cluster_samples
    samples = request.get("samples", [])
    threshold = request.get("threshold", 0.6)
    clusters = cluster_samples(samples, threshold)
    return {"clusters": clusters}


@router.post("/api/custom-generators/generate", tags=["agent"])
async def generate_custom_generator(request: dict):
    """Auto-generate a custom field generator via LLM."""
    from backend.agent.tools.code_gen import generate_custom_field_code, install_custom_generator
    settings = get_settings()
    description = request.get("description", "")
    field_name = request.get("field_name", "custom")
    try:
        code = generate_custom_field_code(description, field_name, settings)
        path = install_custom_generator(field_name, code)
        return {"success": True, "code": code, "installed_path": str(path)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/custom-generators", tags=["agent"])
async def list_custom_generators():
    """List installed custom field generators."""
    from backend.agent.tools.code_gen import load_custom_generators
    generators = load_custom_generators()
    return {"generators": list(generators.keys())}
