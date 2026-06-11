"""Agent tool: diagnose task failures and suggest remediation."""

from __future__ import annotations

import traceback
from typing import Any


KNOWN_PATTERNS: list[tuple[str, str, str]] = [
    ("TableSchemaMismatchError", "schema_mismatch", "DROP TABLE and rebuild schema"),
    ("APITimeoutError", "llm_timeout", "LLM API timeout; disable LLM and fallback to rules"),
    ("APIConnectionError", "llm_unavailable", "LLM API unreachable; disable LLM and fallback to rules"),
    ("APIError", "llm_error", "LLM API error; retry with model pool fallback"),
    ("TimeoutError", "timeout", "Operation timed out; increase timeout or reduce rows"),
    ("ConnectionError", "connection", "Network failure; check connectivity and retry"),
    ("FileNotFoundError", "missing_file", "Sample file missing; verify upload path"),
    ("OperationalError", "db_error", "Database error; verify MySQL URL and permissions"),
]


def diagnose(error: Exception) -> dict[str, Any]:
    """Parse exception and match against known error patterns."""
    error_class = type(error).__name__
    message = str(error)
    stack = traceback.format_exc()

    matched_category = "unknown"
    suggestion = "Review logs and retry."
    for cls_pattern, category, sugg in KNOWN_PATTERNS:
        if cls_pattern in error_class or cls_pattern in message:
            matched_category = category
            suggestion = sugg
            break

    # Heuristic: if stack contains LLM-related module names but not matched yet
    if matched_category == "unknown" and ("openai" in stack.lower() or "llm" in stack.lower()):
        matched_category = "llm_error"
        suggestion = "LLM invocation failed; fallback to rule engine without LLM."

    return {
        "category": matched_category,
        "error_type": error_class,
        "message": message,
        "suggestion": suggestion,
        "retryable": matched_category in ("schema_mismatch", "llm_timeout", "llm_unavailable", "timeout", "connection"),
    }
