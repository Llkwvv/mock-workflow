from unittest.mock import patch

from typer.testing import CliRunner

from mockworkflow.cli import app


runner = CliRunner()


def test_cli_help_starts() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Mockworkflow CLI" in result.output


def test_generate_command_preview_flow() -> None:
    result = runner.invoke(
        app,
        [
            "generate",
            "--sample-file",
            "samples/users.csv",
            "--rows",
            "10",
            "--table-name",
            "users",
        ],
    )

    assert result.exit_code == 0
    assert "Sample Summary" in result.output
    assert "Fields JSON" in result.output
    assert "CREATE TABLE IF NOT EXISTS `users`" in result.output
    assert "Mock Preview Rows" in result.output
    assert "generated_rows: 5" in result.output


def test_generate_command_csv_flow(tmp_path) -> None:
    csv_path = tmp_path / "users.csv"

    result = runner.invoke(
        app,
        [
            "generate",
            "--sample-file",
            "samples/users.csv",
            "--rows",
            "3",
            "--table-name",
            "users",
            "--output",
            "csv",
            "--csv-path",
            str(csv_path),
        ],
    )

    assert result.exit_code == 0
    assert "output: csv" in result.output
    assert "generated_rows: 3" in result.output
    assert csv_path.exists()


def test_generate_schema_output_path_not_writable(tmp_path) -> None:
    # Point at a path under a non-existent parent that is also not creatable
    # because we use a regular file as the "parent" — open() will fail with
    # NotADirectoryError, which we expect to surface as exit code 1.
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x", encoding="utf-8")
    bad_path = blocker / "schema.sql"

    result = runner.invoke(
        app,
        [
            "generate",
            "--sample-file",
            "samples/users.csv",
            "--schema-output-path",
            str(bad_path),
        ],
    )

    assert result.exit_code == 1
    assert "Error writing schema to file" in result.output


def test_generate_command_rejects_unknown_output() -> None:
    result = runner.invoke(
        app,
        [
            "generate",
            "--sample-file",
            "samples/users.csv",
            "--output",
            "parquet",
        ],
    )

    assert result.exit_code != 0
    assert "output must be one of: preview, csv, mysql" in result.output


def test_generate_command_mysql_rejected_when_toggle_disabled(monkeypatch) -> None:
    # Master toggle defaults to off; --output mysql must error without DB ops.
    monkeypatch.delenv("MOCKWORKFLOW_DB_EXPORT_ENABLED", raising=False)
    result = runner.invoke(
        app,
        [
            "generate",
            "--sample-file",
            "samples/users.csv",
            "--output",
            "mysql",
        ],
    )

    assert result.exit_code != 0
    assert "Database export is disabled" in result.output


def test_generate_command_mysql_accepted_when_toggle_enabled(monkeypatch) -> None:
    monkeypatch.setenv("MOCKWORKFLOW_DB_EXPORT_ENABLED", "true")
    monkeypatch.setenv("MOCKWORKFLOW_MYSQL_URL", "mysql+pymysql://u:p@h/db")
    monkeypatch.setenv("MOCKWORKFLOW_LLM_ENABLED", "false")

    with patch("mockworkflow.services.generation.write_mysql", return_value=7) as mock_write:
        result = runner.invoke(
            app,
            [
                "generate",
                "--sample-file",
                "samples/users.csv",
                "--rows",
                "7",
                "--table-name",
                "users",
                "--output",
                "mysql",
            ],
        )

    assert result.exit_code == 0
    assert "output: mysql" in result.output
    assert "generated_rows: 7" in result.output
    mock_write.assert_called_once()
