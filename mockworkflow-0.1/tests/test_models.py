import pytest
from pydantic import ValidationError

from mockworkflow.schemas.field import FieldSemantic, FieldSpec, SqlType, TableSpec


def test_field_spec_accepts_mysql_field_metadata() -> None:
    field = FieldSpec(
        name="user_id",
        type=SqlType.int,
        nullable=False,
        primary_key=True,
        auto_increment=True,
        semantic=FieldSemantic.id,
        confidence=0.95,
    )

    assert field.name == "user_id"
    assert field.type == SqlType.int
    assert field.primary_key is True


def test_table_spec_rejects_non_mysql_dialect() -> None:
    with pytest.raises(ValidationError):
        TableSpec(table_name="users", fields=[], dialect="sqlite")
