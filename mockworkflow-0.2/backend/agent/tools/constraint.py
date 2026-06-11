"""Agent tool: infer cross-field constraints from field names."""

from backend.schemas.field import ConstraintSpec, FieldSpec


# Common temporal / boundary field-name patterns
_TEMPORAL_PAIRS = [
    ("start", "end"),
    ("begin", "end"),
    ("create", "update"),
    ("insert", "update"),
    ("from", "to"),
    ("min", "max"),
    ("lower", "upper"),
    ("open", "close"),
]


def infer_field_constraints(fields: list[FieldSpec]) -> list[ConstraintSpec]:
    """Infer likely cross-field constraints purely from field names.

    Heuristic rules cover common naming conventions such as:
    ``start_time < end_time``, ``min_age < max_age``,
    ``create_time <= update_time``, etc.
    """
    constraints: list[ConstraintSpec] = []
    names = [f.name for f in fields]
    name_map = {n: i for i, n in enumerate(names)}

    def _snake_parts(name: str) -> list[str]:
        return name.lower().replace("_", " ").replace("-", " ").split()

    # 1. Detect prefix pairs: e.g. start_time + end_time
    for prefix, suffix in _TEMPORAL_PAIRS:
        for field in fields:
            parts = _snake_parts(field.name)
            if len(parts) < 2:
                continue
            if parts[0] == prefix:
                counterpart_name = "_".join([suffix] + parts[1:])
                if counterpart_name in name_map:
                    expression = f"{field.name} <= {counterpart_name}"
                    if prefix in ("min", "lower", "from"):
                        expression = f"{field.name} < {counterpart_name}"
                    constraints.append(
                        ConstraintSpec(
                            expression=expression,
                            fields=[field.name, counterpart_name],
                            confidence=0.7,
                        )
                    )

    # 2. Detect suffix pairs: e.g. time_start + time_end
    for field in fields:
        parts = _snake_parts(field.name)
        if len(parts) < 2:
            continue
        for prefix, suffix in _TEMPORAL_PAIRS:
            if parts[-1] == prefix:
                counterpart_parts = parts[:-1] + [suffix]
                counterpart_name = "_".join(counterpart_parts)
                if counterpart_name in name_map:
                    expression = f"{field.name} <= {counterpart_name}"
                    if prefix in ("min", "lower", "from"):
                        expression = f"{field.name} < {counterpart_name}"
                    constraints.append(
                        ConstraintSpec(
                            expression=expression,
                            fields=[field.name, counterpart_name],
                            confidence=0.7,
                        )
                    )

    return constraints
