from mockagent.schemas.field import FieldSpec, SqlType, TableSpec


def generate_create_table_sql(table: TableSpec) -> str:
    columns = [_column_definition(field) for field in table.fields]
    joined_columns = ",\n  ".join(columns)
    return f"CREATE TABLE IF NOT EXISTS `{table.table_name}` (\n  {joined_columns}\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"


def _column_definition(field: FieldSpec) -> str:
    parts = [f"`{field.name}`", _render_type(field)]
    if not field.nullable:
        parts.append("NOT NULL")
    if field.auto_increment:
        parts.append("AUTO_INCREMENT")
    if field.primary_key:
        parts.append("PRIMARY KEY")
    if field.comment:
        parts.append(f"COMMENT '{_escape_comment(field.comment)}'")
    return " ".join(parts)


def _render_type(field: FieldSpec) -> str:
    if field.type == SqlType.varchar:
        return f"VARCHAR({field.length or 255})"
    if field.type == SqlType.decimal:
        return f"DECIMAL({field.precision or 10},{field.scale or 2})"
    if field.type == SqlType.boolean:
        return "BOOLEAN"
    return field.type.value


def _escape_comment(comment: str) -> str:
    return comment.replace("'", "''")
