from unittest.mock import MagicMock, patch

import pytest

from mockworkflow.config import Settings
from mockworkflow.output.db_writer import write_mysql
from mockworkflow.services.generation import generate_to_output


def _settings(**overrides) -> Settings:
    base = dict(llm_enabled=False, db_export_enabled=False, mysql_url=None)
    base.update(overrides)
    return Settings(**base)


def test_mysql_output_disabled_raises_and_skips_db() -> None:
    settings = _settings(db_export_enabled=False, mysql_url="mysql+pymysql://u:p@h/db")
    with patch("mockworkflow.services.generation.write_mysql") as mock_write:
        with pytest.raises(ValueError, match="Database export is disabled"):
            generate_to_output(
                sample_file="samples/users.csv",
                table_name="users",
                rows=10,
                output="mysql",
                settings=settings,
            )
    mock_write.assert_not_called()


def test_mysql_output_missing_url_raises_before_db() -> None:
    settings = _settings(db_export_enabled=True, mysql_url=None)
    with patch("mockworkflow.services.generation.write_mysql") as mock_write:
        with pytest.raises(ValueError, match="no connection string"):
            generate_to_output(
                sample_file="samples/users.csv",
                table_name="users",
                rows=10,
                output="mysql",
                settings=settings,
            )
    mock_write.assert_not_called()


def test_mysql_output_malformed_url_raises_before_db() -> None:
    settings = _settings(db_export_enabled=True, mysql_url="postgres://u:p@h/db")
    with patch("mockworkflow.services.generation.write_mysql") as mock_write:
        with pytest.raises(ValueError, match="must start with mysql"):
            generate_to_output(
                sample_file="samples/users.csv",
                table_name="users",
                rows=10,
                output="mysql",
                settings=settings,
            )
    mock_write.assert_not_called()


def test_mysql_output_happy_path_reports_rows() -> None:
    settings = _settings(db_export_enabled=True, mysql_url="mysql+pymysql://u:p@h/db")
    with patch("mockworkflow.services.generation.write_mysql", return_value=10) as mock_write:
        result = generate_to_output(
            sample_file="samples/users.csv",
            table_name="users",
            rows=10,
            output="mysql",
            settings=settings,
        )
    assert result.output == "mysql"
    assert result.generated_rows == 10
    assert result.output_path == "mysql://users"
    mock_write.assert_called_once()
    args = mock_write.call_args.args
    assert args[0] == "mysql+pymysql://u:p@h/db"
    assert "CREATE TABLE IF NOT EXISTS `users`" in args[1]
    assert args[2] == "users"
    assert len(args[3]) == 10


def test_write_mysql_creates_table_then_inserts() -> None:
    rows = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
    fake_conn = MagicMock()
    fake_engine = MagicMock()
    fake_engine.begin.return_value.__enter__.return_value = fake_conn
    fake_engine.begin.return_value.__exit__.return_value = False

    with patch("mockworkflow.output.db_writer.create_engine", return_value=fake_engine):
        written = write_mysql(
            "mysql+pymysql://u:p@h/db",
            "CREATE TABLE IF NOT EXISTS `t` (`id` INT)",
            "t",
            rows,
        )

    assert written == 2
    # First execute = DDL, second execute = SHOW COLUMNS (schema check), third execute = bulk insert
    assert fake_conn.execute.call_count == 3
