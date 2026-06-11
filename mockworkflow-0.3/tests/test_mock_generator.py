"""Tests for backend/mock/generator.py reproducible seed."""
import pytest

from backend.schemas.field import FieldSpec, SqlType
from backend.mock.generator import generate_mock_rows


def _make_simple_fields():
    return [
        FieldSpec(name="id", type=SqlType.int, nullable=False),
        FieldSpec(name="name", type=SqlType.varchar, length=20, nullable=True),
    ]


def test_seed_reproducibility():
    fields = _make_simple_fields()
    rows1 = generate_mock_rows(fields, 10, seed=42)
    rows2 = generate_mock_rows(fields, 10, seed=42)
    assert rows1 == rows2


def test_different_seed_produces_different():
    fields = _make_simple_fields()
    rows1 = generate_mock_rows(fields, 10, seed=42)
    rows2 = generate_mock_rows(fields, 10, seed=99)
    assert rows1 != rows2


def test_no_seed_changes_between_calls():
    fields = _make_simple_fields()
    rows1 = generate_mock_rows(fields, 10)
    rows2 = generate_mock_rows(fields, 10)
    # Without a fixed seed, numpy/faker random state changes between calls
    # so results should differ (high probability)
    assert rows1 != rows2
