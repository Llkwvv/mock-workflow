from sqlalchemy import create_engine, inspect, text


def validate_mysql_url(mysql_url: str) -> str:
    if not mysql_url.startswith("mysql"):
        raise ValueError("MySQL URL must start with mysql")
    return mysql_url


def write_mysql(mysql_url: str, create_table_sql: str, table_name: str, rows: list[dict[str, object]]) -> int:
    validate_mysql_url(mysql_url)
    engine = create_engine(mysql_url)
    with engine.begin() as connection:
        # 直接执行CREATE TABLE SQL，依赖SQL语句中的IF NOT EXISTS来处理表已存在的情况
        connection.execute(text(create_table_sql))
        if rows:
            columns = list(rows[0].keys())
            column_sql = ", ".join(f"`{column}`" for column in columns)
            value_sql = ", ".join(f":{column}" for column in columns)
            insert_sql = text(f"INSERT INTO `{table_name}` ({column_sql}) VALUES ({value_sql})")
            connection.execute(insert_sql, rows)
    return len(rows)
