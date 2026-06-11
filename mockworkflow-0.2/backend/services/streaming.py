"""Streaming generation helpers for memory-efficient large output.

Provides generator-based alternatives to in-memory batch generation
so that producing millions of rows does not require holding them all
in RAM at once.
"""
from typing import Iterator

from backend.schemas.field import FieldSpec


def generate_mock_rows_stream(fields: list[FieldSpec], rows: int) -> Iterator[dict[str, object]]:
    """Yield rows one at a time instead of building a giant list.

    Thin wrapper around the existing batch generator that chunks
    production into small batches and yields individually.
    """
    from backend.mock.generator import generate_mock_rows

    batch_size = min(rows, 1000)
    produced = 0
    while produced < rows:
        current_batch = min(batch_size, rows - produced)
        batch = generate_mock_rows(fields, current_batch)
        for row in batch:
            yield row
            produced += 1
            if produced >= rows:
                break
