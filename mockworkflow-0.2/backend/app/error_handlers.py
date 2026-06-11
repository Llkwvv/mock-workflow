"""Global exception handlers for FastAPI.

Registers structured JSON responses for all custom business exceptions
as well as common framework errors (RequestValidationError, HTTPException).
"""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.exceptions import MockWorkflowException


def register_error_handlers(app: FastAPI) -> None:
    """Attach exception handlers to the FastAPI app."""

    @app.exception_handler(MockWorkflowException)
    async def _mockworkflow_exception_handler(
        request: Request, exc: MockWorkflowException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = []
        for error in exc.errors():
            loc = " -> ".join(str(x) for x in error.get("loc", []))
            errors.append({"field": loc, "msg": error.get("msg", ""), "type": error.get("type", "")})
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "code": "validation_error",
                "message": "Request validation failed.",
                "detail": {"errors": errors},
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        # Preserve 307/308 redirects (e.g. auth middleware redirect to login)
        if exc.status_code in (307, 308):
            return JSONResponse(
                status_code=exc.status_code,
                headers=dict(exc.headers or {}),
                content={},
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": f"http_{exc.status_code}",
                "message": exc.detail or "HTTP error",
                "detail": {},
            },
        )

    @app.exception_handler(Exception)
    async def _catchall_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "internal_error",
                "message": "An unexpected error occurred.",
                "detail": {"error_type": type(exc).__name__, "error": str(exc)},
            },
        )
