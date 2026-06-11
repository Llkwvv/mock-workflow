"""Agent tool: validate generated data against sample profile and constraints."""

from __future__ import annotations

import re
from typing import Any

from backend.schemas.field import FieldSpec, SampleProfile, SqlType


def validate_generated_data(
    rows: list[dict[str, Any]],
    fields: list[FieldSpec],
    profile: SampleProfile,
    null_threshold: float = 0.05,
    unique_threshold: float = 0.05,
) -> dict[str, Any]:
    """Run multi-dimensional validation on generated data.

    Returns a dict with status (passed/warning/failed) and detailed checks.
    """
    checks: list[dict[str, Any]] = []
    total_rows = len(rows)
    if total_rows == 0:
        return {"status": "failed", "checks": [], "message": "No rows generated"}

    overall_passed = True

    for field in fields:
        col_name = field.name
        col_profile = profile.column_profiles.get(col_name)
        if not col_profile:
            continue

        values = [row.get(col_name) for row in rows if col_name in row]
        non_null = [v for v in values if v is not None and str(v) != ""]
        null_ratio = (len(values) - len(non_null)) / len(values) if values else 0.0
        unique_ratio = (len(set(str(v) for v in non_null)) / len(non_null)) if non_null else 0.0

        # Null ratio check
        sample_null = col_profile.null_ratio
        null_ok = abs(null_ratio - sample_null) <= null_threshold
        checks.append({
            "field": col_name,
            "check": "null_ratio",
            "expected": sample_null,
            "actual": round(null_ratio, 3),
            "passed": null_ok,
        })
        if not null_ok:
            overall_passed = False

        # Unique ratio check
        sample_unique = col_profile.unique_ratio
        unique_ok = abs(unique_ratio - sample_unique) <= unique_threshold
        checks.append({
            "field": col_name,
            "check": "unique_ratio",
            "expected": sample_unique,
            "actual": round(unique_ratio, 3),
            "passed": unique_ok,
        })
        if not unique_ok:
            overall_passed = False

        # Format regex checks for known semantics
        if field.semantic.value == "phone_number" or any(k in col_name.lower() for k in ("phone", "mobile", "手机", "电话")):
            phone_pattern = re.compile(r"^1[3-9]\d{9}$")
            bad_phones = [v for v in non_null if not phone_pattern.match(str(v))]
            phone_ok = len(bad_phones) == 0
            checks.append({
                "field": col_name,
                "check": "phone_format",
                "passed": phone_ok,
                "bad_count": len(bad_phones),
            })
            if not phone_ok:
                overall_passed = False

        # Constraint satisfaction
        if field.constraints:
            from backend.mock.constraint_engine import _compile_constraint
            for c in field.constraints:
                check_fn = _compile_constraint(c.expression)
                if check_fn:
                    violations = sum(1 for row in rows if not check_fn(row))
                    constraint_ok = violations == 0
                    checks.append({
                        "field": col_name,
                        "check": "constraint",
                        "expression": c.expression,
                        "passed": constraint_ok,
                        "violations": violations,
                    })
                    if not constraint_ok:
                        overall_passed = False

    failed_checks = [c for c in checks if not c["passed"]]
    status = "passed" if overall_passed else "warning" if len(failed_checks) <= 2 else "failed"

    return {
        "status": status,
        "total_rows": total_rows,
        "checks": checks,
        "failed_count": len(failed_checks),
    }
