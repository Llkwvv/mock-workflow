from mockworkflow.schemas.field import FieldSpec, SqlType, TableSpec
from mockworkflow.sql.generator import generate_create_table_sql


def test_generate_mysql_create_table_sql() -> None:
    table = TableSpec(
        table_name="users",
        fields=[
            FieldSpec(name="id", type=SqlType.int, nullable=False, primary_key=True, auto_increment=True, comment="id"),
            FieldSpec(name="name", type=SqlType.varchar, length=255, comment="name"),
        ],
    )

    sql = generate_create_table_sql(table)

    assert "CREATE TABLE IF NOT EXISTS `users`" in sql
    assert "`id` INT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT 'id'" in sql
    assert "`name` VARCHAR(255) COMMENT 'name'" in sql
    assert "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4" in sql
