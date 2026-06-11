"""Shared utilities for the backend."""


def default_table_name(table_name: str | None) -> str:
    return table_name or "auto_table"


def require_non_empty(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value
