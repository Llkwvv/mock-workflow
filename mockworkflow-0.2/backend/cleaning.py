"""Data cleaning and preprocessing helpers.

Lightweight utilities for normalising sample data before profiling
to improve downstream generation quality.
"""
import re
from typing import Any


def normalize_whitespace(value: str | None) -> str | None:
    """Collapse multiple whitespace characters into a single space."""
    if value is None:
        return None
    return " ".join(value.split())


def strip_null_tokens(value: str | None, null_tokens: set[str] | None = None) -> str | None:
    """Replace common null-like tokens with actual None."""
    if value is None:
        return None
    null_tokens = null_tokens or {"null", "none", "nan", "-", "", "n/a", "\\n"}
    if value.strip().lower() in null_tokens:
        return None
    return value


def truncate_long_text(value: str | None, max_length: int = 500) -> str | None:
    """Truncate overly long strings to avoid bloating profiles."""
    if value is None:
        return None
    if len(value) > max_length:
        return value[:max_length] + "..."
    return value


def clean_cell(value: Any, max_length: int = 500) -> Any:
    """Apply all cleaning steps to a single cell value."""
    if not isinstance(value, str):
        return value
    value = strip_null_tokens(value)
    if value is None:
        return None
    value = normalize_whitespace(value)
    value = truncate_long_text(value, max_length=max_length)
    return value


def clean_row(row: dict[str, Any], max_length: int = 500) -> dict[str, Any]:
    """Apply cell-level cleaning to every value in a row."""
    return {k: clean_cell(v, max_length=max_length) for k, v in row.items()}
