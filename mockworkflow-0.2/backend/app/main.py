"""FastAPI backend for Mockworkflow (frontend/backend split)."""
import sys
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from backend.app import processor
from backend.app.state import (
    executor,
    FRONTEND_DIR,
    OUTPUT_DIR,
    project_root,
    scheduler,
    task_manager,
)
from backend.app.routers import auth, engine, generation, schedules, schema, system, tasks
from backend.config import get_settings

# ---------------------------------------------------------------------------
# Security Headers Middleware
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # HSTS: Force HTTPS in production
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # X-Content-Type-Options: Prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # X-Frame-Options: Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # X-XSS-Protection
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer-Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions-Policy (formerly Feature-Policy)
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=()"
        )

        # Content-Security-Policy (basic for frontend)
        # Allow inline scripts/styles for existing frontend, but restrict external sources
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' cdn.jsdelivr.net",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data:",
            "font-src 'self' data:",
            "connect-src 'self' ws:",
            "frame-ancestors 'none'",
            "form-action 'self'",
            "base-uri 'self'",
        ]
        if settings.environment != "production":
            # Allow localhost in dev
            csp_directives[5] = "connect-src 'self' ws: localhost:* 127.0.0.1:*"

        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        return response


# App definition
app = FastAPI(
    title="Mockworkflow API",
    description="Backend API for Mockworkflow - sample-driven mock data generation",
    version="0.2.0",
)

# Register global exception handlers
from backend.app.error_handlers import register_error_handlers
register_error_handlers(app)

# CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers
app.add_middleware(SecurityHeadersMiddleware)

# Auth middleware
settings = get_settings()
if settings.web_password:
    from backend.app.auth import AuthMiddleware, UserDB
    # 创建用户数据库并添加默认用户
    user_db = UserDB()
    user_db.add_user("admin", settings.web_password, "Administrator")
    app.add_middleware(
        AuthMiddleware,
        user_db=user_db,
        persist_path=project_root / ".sessions.json",
        audit_path=project_root / ".audit.log",
    )

# Mount output directory for downloads
app.mount("/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")

# Include routers (API routes must be registered before static file mount)
app.include_router(system.router)
app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(schedules.router)
app.include_router(generation.router)
app.include_router(schema.router)
app.include_router(engine.router)


@app.on_event("startup")
async def startup_event():
    processor.set_globals(task_manager, project_root, executor)
    await scheduler.start()


@app.on_event("shutdown")
async def shutdown_event():
    await scheduler.stop()


# Mount frontend static files last so API routes take precedence
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
