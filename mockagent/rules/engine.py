from mockagent.schemas.field import FieldSemantic, FieldSpec, SampleProfile, SqlType


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
            enum_values = _infer_enum_values(profile.samples.get(column, []), semantic)
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
                    uncertain=confidence < 0.75 and semantic == FieldSemantic.unknown,
                    confidence=confidence,
                )
            )
        return fields


def _infer_semantic(column_name: str) -> FieldSemantic:
    normalized = column_name.lower()
    if normalized == "id" or normalized.endswith("_id") or "编号" in column_name:
        return FieldSemantic.id
    if any(keyword in normalized for keyword in ("time", "date", "created_at", "updated_at")) or any(
        keyword in column_name for keyword in ("时间", "日期")
    ):
        return FieldSemantic.time
    if any(keyword in normalized for keyword in ("lng", "lon", "latitude", "longitude")) or any(
        keyword in column_name for keyword in ("经度", "纬度", "坐标")
    ):
        return FieldSemantic.coordinate
    if any(keyword in normalized for keyword in ("status", "state", "type")) or any(
        keyword in column_name for keyword in ("状态", "类型")
    ):
        return FieldSemantic.status
    if normalized.startswith("is_") or any(keyword in column_name for keyword in ("是否", "标记")):
        return FieldSemantic.flag
    if any(keyword in column_name for keyword in ("名称", "姓名", "地址", "描述")):
        return FieldSemantic.text
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


def _infer_enum_values(samples: list[str], semantic: FieldSemantic) -> list[str]:
    if semantic not in {FieldSemantic.status, FieldSemantic.flag}:
        return []
    values = list(dict.fromkeys(str(value) for value in samples if str(value)))
    return values[:20]
