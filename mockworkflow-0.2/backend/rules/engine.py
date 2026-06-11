from backend.schemas.field import FieldSemantic, FieldSpec, SampleProfile, SqlType


def is_probable_id_column(column_name: str) -> bool:
    normalized = column_name.lower()
    return normalized == "id" or normalized.endswith("_id")


class RuleEngine:
    def infer_fields(self, profile: SampleProfile) -> list[FieldSpec]:
        fields: list[FieldSpec] = []
        for column in profile.columns:
            column_profile = profile.column_profiles.get(column)
            inferred_type = column_profile.inferred_type if column_profile else SqlType.varchar
            confidence = column_profile.confidence if column_profile else 0.3
            semantic = _infer_semantic(column)
            sql_type = _adjust_type_by_semantic(inferred_type or SqlType.varchar, semantic)
            if _is_phone_column(column):
                sql_type = SqlType.varchar
            is_id = semantic == FieldSemantic.id
            is_nullable = bool(column_profile.null_ratio > 0) if column_profile else True

            sample_values = profile.samples.get(column, [])
            unique_ratio = column_profile.unique_ratio if column_profile else None
            value_frequency = dict(column_profile.value_frequency) if column_profile else {}
            min_value = column_profile.min_value if column_profile else None
            max_value = column_profile.max_value if column_profile else None

            # Distinct, non-empty real values from the sample, preserving order.
            value_pool = [v for v in dict.fromkeys(str(s) for s in sample_values) if v != ""]

            enum_values = _infer_enum_values(sample_values, semantic, unique_ratio)

            fields.append(
                FieldSpec(
                    name=column,
                    type=sql_type,
                    length=_default_length(sql_type),
                    precision=10 if sql_type == SqlType.decimal else None,
                    scale=2 if sql_type == SqlType.decimal else None,
                    nullable=False if is_id else is_nullable,
                    primary_key=is_id,
                    auto_increment=is_id and sql_type == SqlType.int,
                    comment=column,
                    semantic=semantic,
                    enum_values=enum_values,
                    value_pool=value_pool,
                    value_frequency=value_frequency,
                    unique_ratio=unique_ratio,
                    min_value=min_value,
                    max_value=max_value,
                    uncertain=confidence < 0.75 and semantic == FieldSemantic.unknown,
                    confidence=confidence,
                )
            )
        return fields


def _infer_semantic(column_name: str) -> FieldSemantic:
    """Infer field semantic from column name using semantics.yaml configuration."""
    from backend.rules.semantics import SemanticRegistry

    registry = SemanticRegistry.get()
    match = registry.match(column_name)
    if match is not None:
        return FieldSemantic(match.name)
    return FieldSemantic.unknown


def _is_phone_column(column_name: str) -> bool:
    normalized = column_name.lower()
    return any(keyword in normalized for keyword in ("phone", "mobile", "tel")) or any(
        keyword in column_name for keyword in ("手机", "电话")
    )


def _adjust_type_by_semantic(sql_type: SqlType, semantic: FieldSemantic) -> SqlType:
    if semantic == FieldSemantic.id:
        return SqlType.int
    if semantic == FieldSemantic.time:
        return SqlType.datetime
    if semantic == FieldSemantic.coordinate:
        return SqlType.decimal
    return sql_type


def _default_length(sql_type: SqlType) -> int | None:
    if sql_type == SqlType.varchar:
        return 255
    return None


def _infer_enum_values(
    samples: list[str],
    semantic: FieldSemantic,
    unique_ratio: float | None = None,
) -> list[str]:
    """Detect enum-like columns.

    Beyond the explicit status/flag semantics, any column whose sample has very
    few distinct values (low unique ratio) is treated as an enumeration so that
    the generator reuses those real values instead of inventing junk.
    """
    values = [v for v in dict.fromkeys(str(value) for value in samples if str(value))]
    if not values:
        return []
    if semantic in {FieldSemantic.status, FieldSemantic.flag}:
        return values[:20]
    # Low-cardinality categorical columns: few distinct values relative to rows.
    if len(values) <= 10 and (unique_ratio is None or unique_ratio <= 0.5):
        return values[:20]
    return []
