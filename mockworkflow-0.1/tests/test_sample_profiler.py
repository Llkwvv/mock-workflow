import pytest

from mockworkflow.sample.profiler import analyze_sample_file
from mockworkflow.schemas.field import SqlType


def test_analyze_sample_file_empty(tmp_path) -> None:
    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text("a,b,c\n", encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        analyze_sample_file(str(empty_csv))

    assert str(empty_csv) in str(excinfo.value)
    assert "no data rows" in str(excinfo.value)


def test_analyze_sample_file_profiles_csv_columns() -> None:
    profile = analyze_sample_file("samples/users.csv")

    assert profile.row_count == 3
    assert profile.columns == ["id", "姓名", "phone", "created_at", "status", "amount", "longitude", "latitude"]
    assert profile.column_profiles["id"].inferred_type == SqlType.int
    assert profile.column_profiles["created_at"].inferred_type == SqlType.datetime
    assert profile.column_profiles["amount"].inferred_type == SqlType.decimal
