from mockworkflow.services.generation import build_generation_preview


def test_build_generation_preview_runs_minimal_backend_flow() -> None:
    result = build_generation_preview("samples/users.csv", table_name="users", rows=5)

    assert result.profile.row_count == 3
    assert len(result.fields) == 8
    assert "CREATE TABLE IF NOT EXISTS `users`" in result.create_table_sql
    assert len(result.preview_rows) == 5
    assert result.preview_rows[0]["id"] == 1
