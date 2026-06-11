"""Generation quality validation and feedback loop.

After mock rows are produced, this module re-profiles the *generated* data and
compares it against the original sample profile to score how faithfully the
output reproduces the real data's shape (type, null ratio, cardinality, enum
domain, value length).  The per-field scores close the agent loop: high-scoring
field specs are promoted into durable rules via the rule store, low-scoring ones
are surfaced for review.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.schemas.field import FieldSpec, SampleProfile, SqlType


class FieldQuality(BaseModel):
    name: str
    score: float = Field(ge=0, le=1)
    type_match: bool = True
    null_ratio_delta: float = 0.0
    unique_ratio_delta: float = 0.0
    enum_adherence: float = 1.0
    issues: list[str] = Field(default_factory=list)


class QualityReport(BaseModel):
    overall_score: float = Field(default=0.0, ge=0, le=1)
    field_quality: list[FieldQuality] = Field(default_factory=list)
    rows_evaluated: int = 0
    promoted_rules: int = 0


def _abs(a: float | None, b: float | None) -> float:
    if a is None or b is None:
        return 0.0
    return abs(float(a) - float(b))


def validate_generation(
    original: SampleProfile,
    generated_rows: list[dict[str, object]],
    fields: list[FieldSpec],
) -> QualityReport:
    """Re-profile generated rows and score them against the original sample."""
    if not generated_rows:
        return QualityReport()

    # Lazy import keeps pandas out of the import path for callers that don't validate.
    import pandas as pd
    from backend.sample.profiler import profile_dataframe

    df = pd.DataFrame(generated_rows)
    try:
        gen_profile = profile_dataframe(df, file_path="<generated>", sample_size=len(df))
    except ValueError:
        return QualityReport(rows_evaluated=len(generated_rows))

    field_by_name = {f.name: f for f in fields}
    qualities: list[FieldQuality] = []

    for name, orig_col in original.column_profiles.items():
        gen_col = gen_profile.column_profiles.get(name)
        field = field_by_name.get(name)
        if gen_col is None:
            qualities.append(FieldQuality(name=name, score=0.0, issues=["missing in output"]))
            continue

        issues: list[str] = []
        score = 1.0

        # 1. Type fidelity (0.35 weight)
        type_match = orig_col.inferred_type == gen_col.inferred_type
        if not type_match:
            score -= 0.35
            issues.append(f"type {gen_col.inferred_type} != {orig_col.inferred_type}")

        # 2. Null ratio fidelity (0.15)
        null_delta = _abs(orig_col.null_ratio, gen_col.null_ratio)
        score -= 0.15 * min(null_delta, 1.0)
        if null_delta > 0.3:
            issues.append(f"null ratio off by {null_delta:.2f}")

        # 3. Cardinality fidelity (0.20) — generated data shouldn't collapse to
        #    a handful of repeated values when the source was highly unique.
        uniq_delta = _abs(orig_col.unique_ratio, gen_col.unique_ratio)
        score -= 0.20 * min(uniq_delta, 1.0)
        if orig_col.unique_ratio > 0.8 and gen_col.unique_ratio < 0.5:
            issues.append("cardinality collapsed")

        # 4. Enum domain adherence (0.30) — for enum fields, every generated
        #    value must come from the declared domain (+ blank).
        enum_adherence = 1.0
        if field and field.enum_values:
            allowed = set(field.enum_values) | {""}
            gen_values = [str(v) for v in gen_col.samples]
            if gen_values:
                in_domain = sum(1 for v in gen_values if v in allowed)
                enum_adherence = in_domain / len(gen_values)
                score -= 0.30 * (1.0 - enum_adherence)
                if enum_adherence < 0.99:
                    issues.append(f"enum adherence {enum_adherence:.2f}")

        score = max(0.0, min(1.0, score))
        qualities.append(
            FieldQuality(
                name=name,
                score=round(score, 3),
                type_match=type_match,
                null_ratio_delta=round(null_delta, 3),
                unique_ratio_delta=round(uniq_delta, 3),
                enum_adherence=round(enum_adherence, 3),
                issues=issues,
            )
        )

    overall = round(sum(q.score for q in qualities) / len(qualities), 3) if qualities else 0.0
    return QualityReport(
        overall_score=overall,
        field_quality=qualities,
        rows_evaluated=len(generated_rows),
    )


def apply_feedback(
    report: QualityReport,
    fields: list[FieldSpec],
    rule_store=None,
    settings=None,
    min_score: float = 0.9,
) -> int:
    """Promote high-quality, high-confidence field specs into durable rules.

    Returns the number of rules upserted.  This is what makes the system learn:
    a field whose generated output faithfully matched the real sample is worth
    remembering so future tables with the same column resolve instantly.
    """
    from backend.config import get_settings
    from backend.rules.store import RuleStore

    settings = settings or get_settings()
    if not getattr(settings, "rules_autosave", False):
        return 0

    store = rule_store or RuleStore(settings.rules_file)
    field_by_name = {f.name: f for f in fields}
    good_specs: list[FieldSpec] = []
    for q in report.field_quality:
        if q.score < min_score:
            continue
        field = field_by_name.get(q.name)
        if field is None:
            continue
        if (field.confidence or 0) >= settings.rules_min_confidence:
            good_specs.append(field)

    if not good_specs:
        return 0
    return store.upsert_fields(
        good_specs,
        min_confidence=settings.rules_min_confidence,
        source="validated",
    )
