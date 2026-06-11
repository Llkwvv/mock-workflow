"""Tests for structured business exceptions."""

import pytest

from backend.app.exceptions import (
    MockWorkflowException,
    TaskNotFoundError,
    ValidationError,
    UnauthorizedError,
    DatabaseConnectionError,
)


def test_base_exception_to_dict():
    exc = MockWorkflowException(message="base", detail={"a": 1})
    assert exc.to_dict() == {"code": "internal_error", "message": "base", "detail": {"a": 1}}


def test_task_not_found_error():
    exc = TaskNotFoundError()
    assert exc.status_code == 404
    assert exc.code == "task_not_found"
    assert "Task not found" in exc.message


def test_validation_error_with_detail():
    exc = ValidationError(message="bad input", detail={"field": "rows"})
    assert exc.status_code == 422
    assert exc.code == "validation_error"
    assert exc.to_dict()["detail"]["field"] == "rows"


def test_unauthorized_error():
    exc = UnauthorizedError()
    assert exc.status_code == 401
    assert exc.code == "unauthorized"


def test_database_connection_error():
    exc = DatabaseConnectionError(message="mysql down")
    assert exc.status_code == 502
    assert "mysql down" in exc.message
