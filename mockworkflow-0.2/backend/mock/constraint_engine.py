"""Cross-field constraint engine: infer, compile, and apply constraints."""

from __future__ import annotations

import operator
import re
from typing import Any, Callable

from backend.schemas.field import ConstraintSpec, FieldSemantic, FieldSpec, SqlType


# Supported binary operators in constraint expressions
_OPS: dict[str, Callable[[Any, Any], bool]] = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}

# Regex to parse simple binary expressions like "start_time < end_time"
_EXPR_RE = re.compile(
    r"^\s*(?P<left>[\w_]+)\s*(?P<op><=|>=|<|>|==|!=)\s*(?P<right>[\w_]+)\s*$"
)


def apply_constraints(rows: list[dict[str, object]], fields: list[FieldSpec]) -> list[dict[str, object]]:
    """Apply compiled constraints to generated rows, swapping values when violated."""
    # Collect all constraints from fields
    all_constraints: list[ConstraintSpec] = []
    for field in fields:
        all_constraints.extend(field.constraints)

    if not all_constraints:
        return rows

    # Compile constraints into callable checks
    compiled = []
    for c in all_constraints:
        check = _compile_constraint(c.expression)
        if check:
            compiled.append((check, c.fields))

    if not compiled:
        return rows

    # Apply: iterate rows and fix violations
    for row in rows:
        for check, involved_fields in compiled:
            if not check(row):
                _fix_violation(row, involved_fields, fields)
    return rows


def _compile_constraint(expression: str) -> Callable[[dict[str, object]], bool] | None:
    """Compile a simple DSL expression into a row-checking function."""
    m = _EXPR_RE.match(expression)
    if not m:
        return None

    left = m.group("left")
    op_str = m.group("op")
    right = m.group("right")
    op_func = _OPS.get(op_str)
    if not op_func:
        return None

    def check(row: dict[str, object]) -> bool:
        l_val = row.get(left)
        r_val = row.get(right)
        if l_val is None or r_val is None:
            return True  # nullable fields skip check
        try:
            return op_func(l_val, r_val)
        except Exception:
            return True

    return check


def _fix_violation(row: dict[str, object], fields_involved: list[str], fields: list[FieldSpec]) -> None:
    """Attempt to fix a constraint violation by swapping or adjusting values."""
    if len(fields_involved) != 2:
        return
    a, b = fields_involved[0], fields_involved[1]
    val_a = row.get(a)
    val_b = row.get(b)
    if val_a is None or val_b is None:
        return
    try:
        if val_a > val_b:
            row[a], row[b] = val_b, val_a
    except Exception:
        pass


def infer_constraints(fields: list[FieldSpec]) -> list[ConstraintSpec]:
    """Infer cross-field constraints by analyzing field names and semantics."""
    constraints: list[ConstraintSpec] = []
    field_by_name = {f.name: f for f in fields}

    # 1. Temporal ordering: start_time / end_time pairs
    start_fields = [f for f in fields if f.name.lower() in ("start_time", "starttime", "begin_time", "begintime", "kaishisj")]
    end_fields = [f for f in fields if f.name.lower() in ("end_time", "endtime", "finish_time", "finishtime", "jieshusj")]
    if start_fields and end_fields:
        constraints.append(
            ConstraintSpec(
                expression=f"{start_fields[0].name} < {end_fields[0].name}",
                fields=[start_fields[0].name, end_fields[0].name],
                confidence=0.9,
            )
        )

    # 2. Numeric ordering: subtotal / total pairs
    subtotal_fields = [f for f in fields if f.name.lower() in ("subtotal", "xiaoji", "sub_total")]
    total_fields = [f for f in fields if f.name.lower() in ("total", "zongji", "total_amount", "zonge")]
    if subtotal_fields and total_fields:
        constraints.append(
            ConstraintSpec(
                expression=f"{subtotal_fields[0].name} <= {total_fields[0].name}",
                fields=[subtotal_fields[0].name, total_fields[0].name],
                confidence=0.85,
            )
        )

    # 3. Geographic hierarchy: province -> city -> district
    geo_keywords = [("province", "sheng"), ("city", "shi"), ("district", "qu", "xian")]
    geo_fields: list[FieldSpec] = []
    for kw_tuple in geo_keywords:
        for f in fields:
            if any(kw in f.name.lower() for kw in kw_tuple):
                geo_fields.append(f)
                break
    if len(geo_fields) >= 2:
        for i in range(len(geo_fields) - 1):
            constraints.append(
                ConstraintSpec(
                    expression=f"{geo_fields[i].name} != {geo_fields[i + 1].name}",
                    fields=[geo_fields[i].name, geo_fields[i + 1].name],
                    confidence=0.7,
                )
            )

    return constraints
