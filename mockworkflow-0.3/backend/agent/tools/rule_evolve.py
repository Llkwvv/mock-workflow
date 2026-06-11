"""Agent tool: evolve the rule store by auditing high-confidence patterns."""

from __future__ import annotations

from backend.rules.store import FieldRule, RuleStore
from backend.schemas.field import FieldSpec


def evolve_rules(
    store: RuleStore,
    successful_resolutions: list[tuple[str, FieldSpec]],
    min_confidence: float = 0.85,
    min_occurrences: int = 3,
) -> int:
    """Promote frequently successful field resolutions into durable rules.

    Args:
        store: The rule store to update.
        successful_resolutions: List of (column_name, field_spec) pairs that
            produced good mock data in recent tasks.
        min_confidence: Minimum confidence to promote a rule.
        min_occurrences: How many times a column name must succeed before
            it is promoted to a rule.

    Returns:
        Number of new rules added or updated.
    """
    from collections import Counter

    occurrence_counter: Counter[str] = Counter()
    best_spec: dict[str, FieldSpec] = {}

    for col_name, spec in successful_resolutions:
        occurrence_counter[col_name] += 1
        # Keep the highest-confidence spec seen for this column
        if col_name not in best_spec or (spec.confidence or 0) > (best_spec[col_name].confidence or 0):
            best_spec[col_name] = spec

    # Filter columns that appear often enough and have high confidence
    to_promote: list[FieldSpec] = []
    for col_name, count in occurrence_counter.items():
        if count >= min_occurrences:
            spec = best_spec[col_name]
            if spec.confidence is not None and spec.confidence >= min_confidence:
                to_promote.append(spec)

    if not to_promote:
        return 0

    return store.upsert_fields(to_promote, min_confidence=min_confidence, source="evolved")


def audit_rule_store(store: RuleStore, min_confidence: float = 0.3) -> dict[str, int]:
    """Clean up the rule store by removing low-confidence or duplicate rules.

    Returns:
        Stats dict with ``removed``, ``merged`` counts.
    """
    rules = store.load_rules()
    if not rules:
        return {"removed": 0, "merged": 0}

    # Remove low-confidence rules
    kept = [r for r in rules if r.confidence >= min_confidence]
    removed = len(rules) - len(kept)

    # Merge exact duplicates by normalized name
    by_name: dict[str, FieldRule] = {}
    merged = 0
    for rule in kept:
        key = _normalize(rule.name)
        if key in by_name:
            # Keep the one with higher confidence
            if rule.confidence > by_name[key].confidence:
                by_name[key] = rule
            merged += 1
        else:
            by_name[key] = rule

    store._save(list(by_name.values()))
    return {"removed": removed, "merged": merged}


def _normalize(value: str) -> str:
    return "".join(value.strip().lower().split())
