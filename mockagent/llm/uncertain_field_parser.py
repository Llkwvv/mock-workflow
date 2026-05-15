"""Resolve fields using the rule store first and LLM as fallback."""

from pydantic import BaseModel

from mockagent.config import Settings, get_settings
from mockagent.llm.openai_parser import OpenAIFieldParser
from mockagent.rules import RuleEngine, RuleStore
from mockagent.schemas.field import FieldSemantic, FieldSpec, SampleProfile, SqlType


class FieldResolutionResult(BaseModel):
    fields: list[FieldSpec]
    llm_used: bool = False
    llm_resolved_count: int = 0
    rules_resolved_count: int = 0
    fallback_resolved_count: int = 0
    value_pools_generated: int = 0


def resolve_fields(
    profile: SampleProfile,
    settings: Settings | None = None,
    rule_store: RuleStore | None = None,
    refresh_rules: bool = False,
) -> FieldResolutionResult:
    """Resolve fields in this order: rule store -> LLM -> minimal fallback.

    When ``refresh_rules`` is True, the rule store is bypassed for lookups so
    every column is re-resolved via the LLM (and still persisted back when
    ``settings.rules_autosave`` is enabled).
    """
    if settings is None:
        settings = get_settings()

    store = rule_store or RuleStore(settings.rules_file)
    if refresh_rules:
        rules: dict[str, FieldSpec | None] = {column: None for column in profile.columns}
    else:
        rules = {column: store.resolve(column) for column in profile.columns}
    resolved_fields: list[FieldSpec] = []
    unresolved_columns: list[str] = []

    for column in profile.columns:
        field = rules.get(column)
        if field is not None:
            resolved_fields.append(field)
        else:
            unresolved_columns.append(column)

    llm_used = False
    llm_resolved_count = 0
    fallback_resolved_count = 0

    if unresolved_columns and settings.llm_enabled:
        try:
            parser = OpenAIFieldParser(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                model=settings.llm_model,
                timeout=settings.llm_timeout,
                max_tokens=settings.llm_max_tokens,
                temperature=settings.llm_temperature,
            )
            llm_fields = parser.parse_fields(profile, unresolved_columns)
            llm_by_name = {field.name: field for field in llm_fields}
            llm_used = True
            llm_resolved_count = len(llm_by_name)

            if settings.rules_autosave:
                store.upsert_fields(
                    list(llm_by_name.values()),
                    min_confidence=settings.rules_min_confidence,
                    source="llm",
                )

            fallback_fields = {
                field.name: field
                for field in RuleEngine().infer_fields(profile)
            }

            for column in unresolved_columns:
                field = llm_by_name.get(column) or fallback_fields.get(column)
                if field is None:
                    field = _build_minimal_fallback_field(profile, column)
                else:
                    if column not in llm_by_name:
                        fallback_resolved_count += 1
                resolved_fields.append(field)
        except (TimeoutError, ConnectionError, ValueError) as exc:
            print(f"Warning: LLM resolution failed ({exc}), falling back to minimal rules")
            fallback_fields = {field.name: field for field in RuleEngine().infer_fields(profile)}
            for column in unresolved_columns:
                field = fallback_fields.get(column) or _build_minimal_fallback_field(profile, column)
                fallback_resolved_count += 1
                resolved_fields.append(field)
    else:
        fallback_fields = {field.name: field for field in RuleEngine().infer_fields(profile)}
        for column in unresolved_columns:
            field = fallback_fields.get(column) or _build_minimal_fallback_field(profile, column)
            fallback_resolved_count += 1
            resolved_fields.append(field)

    pools_generated = 0
    if settings.llm_enabled and settings.llm_value_pool_enabled:
        from mockagent.llm.value_pool import ensure_value_pools
        try:
            pools_generated = ensure_value_pools(
                resolved_fields,
                profile,
                settings=settings,
                rule_store=store,
            )
        except (TimeoutError, ConnectionError, ValueError) as exc:
            print(f"Warning: value pool generation skipped ({exc})")

    return FieldResolutionResult(
        fields=resolved_fields,
        llm_used=llm_used or pools_generated > 0,
        llm_resolved_count=llm_resolved_count,
        rules_resolved_count=len(profile.columns) - len(unresolved_columns),
        fallback_resolved_count=fallback_resolved_count,
        value_pools_generated=pools_generated,
    )


def resolve_uncertain_fields(
    profile: SampleProfile,
    fields: list[FieldSpec] | None = None,
    settings: Settings | None = None,
) -> list[FieldSpec]:
    """Backward-compatible wrapper that now resolves all fields via rule store and LLM."""
    return resolve_fields(profile, settings=settings).fields


def _build_minimal_fallback_field(profile: SampleProfile, column: str) -> FieldSpec:
    sample_values = profile.samples.get(column, [])
    has_numeric = any(_looks_like_number(value) for value in sample_values)

    return FieldSpec(
        name=column,
        type=SqlType.int if has_numeric else SqlType.varchar,
        length=255 if not has_numeric else None,
        nullable=True,
        comment=column,
        semantic=FieldSemantic.unknown,
        confidence=0.1,
        uncertain=True,
    )


def _looks_like_number(value: str) -> bool:
    try:
        float(str(value))
        return True
    except ValueError:
        return False
