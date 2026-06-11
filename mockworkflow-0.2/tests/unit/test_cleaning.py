"""Tests for data cleaning utilities."""

from backend.cleaning import clean_cell, clean_row, normalize_whitespace, strip_null_tokens, truncate_long_text


def test_normalize_whitespace():
    assert normalize_whitespace("  hello   world  ") == "hello world"
    assert normalize_whitespace(None) is None


def test_strip_null_tokens():
    assert strip_null_tokens("null") is None
    assert strip_null_tokens("N/A") is None
    assert strip_null_tokens("hello") == "hello"
    assert strip_null_tokens(None) is None


def test_truncate_long_text():
    assert truncate_long_text("short", max_length=10) == "short"
    assert truncate_long_text("a" * 100, max_length=10) == "a" * 10 + "..."


def test_clean_cell():
    assert clean_cell("  hello  ") == "hello"
    assert clean_cell("null") is None
    assert clean_cell(123) == 123


def test_clean_row():
    row = {"a": "  hello  ", "b": "null", "c": 42}
    cleaned = clean_row(row)
    assert cleaned["a"] == "hello"
    assert cleaned["b"] is None
    assert cleaned["c"] == 42
