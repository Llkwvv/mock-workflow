from mockworkflow.output.csv_writer import write_csv


def test_write_csv_creates_file(tmp_path) -> None:
    csv_path = tmp_path / "users.csv"

    written_path = write_csv([{"id": 1, "name": "Alice"}], str(csv_path))

    assert written_path == csv_path
    assert csv_path.read_text(encoding="utf-8").splitlines()[0] == "id,name"
