from mockworkflow.mock.generator import generate_mock_rows, preview_mock_rows
from mockworkflow.schemas.field import FieldSemantic, FieldSpec, SqlType


def test_preview_mock_rows_returns_at_most_five_rows() -> None:
    fields = [
        FieldSpec(name="id", type=SqlType.int, semantic=FieldSemantic.id, auto_increment=True),
        FieldSpec(name="姓名", type=SqlType.varchar, semantic=FieldSemantic.text),
    ]

    rows = preview_mock_rows(fields, rows=10)

    assert len(rows) == 5
    assert rows[0]["id"] == 1
    assert rows[4]["id"] == 5
    assert "姓名" in rows[0]


def test_coordinate_generation_uses_latitude_range() -> None:
    fields = [FieldSpec(name="latitude", type=SqlType.decimal, semantic=FieldSemantic.coordinate)]

    rows = preview_mock_rows(fields, rows=5)

    assert all(-90 <= row["latitude"] <= 90 for row in rows)


def test_generate_value_boolean_semantic() -> None:
    field = FieldSpec(name="enabled", type=SqlType.int, semantic=FieldSemantic.boolean)

    rows = generate_mock_rows([field], rows=50)

    values = {row["enabled"] for row in rows}
    assert values.issubset({0, 1})
    assert len(values) <= 2
