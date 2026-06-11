"""Structured business exceptions for Mockworkflow.

All custom exceptions carry a machine-readable ``code``, a human-readable
``message``, and an optional ``detail`` dict for debugging.
"""

from typing import Any


class MockWorkflowException(Exception):
    """Base exception with structured fields."""

    status_code: int = 500
    code: str = "internal_error"
    message: str = "An internal error occurred."

    def __init__(
        self,
        message: str | None = None,
        detail: dict[str, Any] | None = None,
    ):
        self.message = message or self.message
        self.detail = detail or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "detail": self.detail,
        }


# --- 4xx client errors ---

class SampleNotFoundError(MockWorkflowException):
    status_code = 404
    code = "sample_not_found"
    message = "Sample file not found."


class TaskNotFoundError(MockWorkflowException):
    status_code = 404
    code = "task_not_found"
    message = "Task not found."


class ScheduleNotFoundError(MockWorkflowException):
    status_code = 404
    code = "schedule_not_found"
    message = "Schedule not found."


class ValidationError(MockWorkflowException):
    status_code = 422
    code = "validation_error"
    message = "Request validation failed."


class SchemaMismatchError(MockWorkflowException):
    status_code = 400
    code = "schema_mismatch"
    message = "Generated schema does not match target table."


class LLMConfigurationError(MockWorkflowException):
    status_code = 503
    code = "llm_not_configured"
    message = "LLM is not configured or unavailable."


class LLMResponseError(MockWorkflowException):
    status_code = 502
    code = "llm_response_error"
    message = "LLM returned an invalid or empty response."


class DatabaseConnectionError(MockWorkflowException):
    status_code = 502
    code = "db_connection_failed"
    message = "Failed to connect to the database."


class UnauthorizedError(MockWorkflowException):
    status_code = 401
    code = "unauthorized"
    message = "Authentication required."


class ForbiddenError(MockWorkflowException):
    status_code = 403
    code = "forbidden"
    message = "Access denied."


# --- 5xx server errors ---

class GenerationError(MockWorkflowException):
    status_code = 500
    code = "generation_failed"
    message = "Mock data generation failed."


class RuleStoreError(MockWorkflowException):
    status_code = 500
    code = "rule_store_error"
    message = "Failed to read or write rule store."
