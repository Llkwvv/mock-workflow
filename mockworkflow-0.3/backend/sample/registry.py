"""Sample reader registry with decorator-based auto-registration."""

from typing import Callable
from pathlib import Path

import pandas as pd

SampleReader = Callable[[Path], pd.DataFrame]

_READERS: dict[str, SampleReader] = {}


def register_reader(suffix: str):
    """Decorator: register a function as the reader for a given file suffix.

    Args:
        suffix: File suffix without the leading dot (e.g. "csv", "xlsx").
    """
    clean = suffix.lower().lstrip(".")

    def decorator(func: SampleReader) -> SampleReader:
        _READERS[clean] = func
        return func

    return decorator


def get_reader(suffix: str) -> SampleReader | None:
    """Look up a registered reader by file suffix."""
    return _READERS.get(suffix.lower().lstrip("."))


def list_supported_formats() -> list[str]:
    """Return all registered file suffixes (with leading dot)."""
    return sorted(f".{k}" for k in _READERS.keys())
