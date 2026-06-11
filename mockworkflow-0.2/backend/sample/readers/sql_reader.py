"""SQL INSERT sample reader (auto-registered)."""

import ast
import re
from pathlib import Path

import pandas as pd

from backend.sample.registry import register_reader


@register_reader("sql")
def read_sql(path: Path) -> pd.DataFrame:
    """Parse an SQL file containing INSERT INTO ... VALUES (...) statements.

    The first VALUES row is used as column headers if it looks like
    short identifier strings (e.g. pinyin abbreviations).  Otherwise
    numeric column names are generated.
    """
    text = path.read_text(encoding="utf-8")

    rows: list[list[str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if not line.lower().startswith("insert into"):
            continue
        match = re.search(r"VALUES\s*\((.*)\)", line, re.IGNORECASE)
        if not match:
            continue
        try:
            # SQL NULL is not valid Python; convert it to None first.
            payload = re.sub(r"\bNULL\b", "None", match.group(1))
            values = ast.literal_eval(f"({payload})")
            # Single-value rows: (123) evaluates to int, not tuple.
            if not isinstance(values, tuple):
                values = (values,)
            rows.append([str(v) if v is not None else "" for v in values])
        except (ValueError, SyntaxError):
            continue

    if not rows:
        raise ValueError(f"No INSERT VALUES found in {path}")

    def _looks_like_data_value(v: str) -> bool:
        """Return True if v looks like a data value rather than a column name."""
        v = v.strip()
        if re.match(r"^\d+$", v):             # pure integer like "1", "2500"
            return True
        if re.match(r"^\d+\.\d+$", v):          # float like "2.0"
            return True
        if re.match(r"^\(\d{4}\)", v):         # year prefix like "(2025)"
            return True
        if re.match(r"^\d{4}-\d{2}-\d{2}$", v):  # date like "2025-03-26"
            return True
        if re.match(r"^\d+\.\d+[eE][+-]?\d+$", v):  # scientific notation like "9.13212E+17"
            return True
        return False

    # Find the row that looks like column headers among all INSERT rows.
    # Strategy:
    #   1. First row is all short strings, no value looks like data,
    #      and at least one value is alphabetic/Chinese.
    #   2. Fallback: scan for a row with the highest ratio of identifier-like
    #      values (a-zA-Z_ prefixes), preferring rows with no data-like values.
    #   3. Final fallback: scan for a row of Chinese column names.
    header_idx = None

    # --- Strategy 1: first row looks like a header ---
    first = rows[0]
    if (
        all(isinstance(v, str) and len(v) <= 30 for v in first)
        and any(re.search(r"[a-zA-Z\u4e00-\u9fff]", v) for v in first)
        and not all(v.strip().isdigit() for v in first)
        and not any(_looks_like_data_value(v) for v in first)
    ):
        # Extra confidence: at least one subsequent row contains a pure number.
        if len(rows) > 1 and any(
            any(v.strip().isdigit() for v in row) for row in rows[1:]
        ):
            header_idx = 0

    # --- Strategy 2: score-based scan for the best header candidate ---
    if header_idx is None:
        best_idx = None
        best_score = -1.0
        for idx, row in enumerate(rows):
            if not all(isinstance(v, str) for v in row):
                continue
            if any(_looks_like_data_value(v) for v in row):
                continue
            # A real header almost never contains multiple pure numbers.
            digit_count = sum(1 for v in row if v.strip().isdigit())
            if digit_count >= 2:
                continue
            # identifier-like values (English abbreviations like xh, rddw)
            id_count = sum(
                1 for v in row
                if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", v) and len(v) <= 20
            )
            # Chinese column name values
            cn_count = sum(
                1 for v in row
                if re.search(r"[\u4e00-\u9fff]", v) and len(v) <= 20
            )
            # Penalise very long values (likely data, not headers)
            long_count = sum(1 for v in row if len(v) > 30)
            if long_count > 0:
                continue
            score = (id_count * 2.0 + cn_count * 1.5) / max(len(row), 1)
            # Prefer rows where most values look like headers
            if score > best_score and (id_count > 0 or cn_count > 0):
                best_score = score
                best_idx = idx
        if best_idx is not None and best_score >= 0.5:
            header_idx = best_idx

    if header_idx is not None:
        headers = rows[header_idx]
        data = [row for i, row in enumerate(rows) if i != header_idx]
        return pd.DataFrame(data, columns=headers)

    return pd.DataFrame(rows)
