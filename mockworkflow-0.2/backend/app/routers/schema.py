"""Schema (MySQL) routes."""
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, status
from pydantic import BaseModel, Field

from backend.app.exceptions import DatabaseConnectionError, GenerationError
from backend.app.state import project_root, SAMPLES_DIR, task_manager
from backend.app import processor

router = APIRouter()


# ---------- Models ----------

class SchemaConnectRequest(BaseModel):
    host: str = Field(min_length=1)
    database: str = Field(min_length=1)
    user: str = Field(min_length=1)
    password: str


class TableInfo(BaseModel):
    name: str
    columns: int
    rows: int


class SchemaTablesResponse(BaseModel):
    tables: list[TableInfo]


class SchemaGenerateRequest(BaseModel):
    host: str = Field(min_length=1)
    database: str = Field(min_length=1)
    user: str = Field(min_length=1)
    password: str
    table_name: str = Field(min_length=1)
    rows: int = Field(default=100, gt=0, le=100000)
    output: str = Field(default="preview")  # preview, csv, mysql


class SchemaGenerateResponse(BaseModel):
    task_id: str
    message: str


# ---------- Routes ----------

@router.post("/api/schema/tables", response_model=SchemaTablesResponse, tags=["schema"])
async def list_schema_tables(request: SchemaConnectRequest):
    import pymysql
    from pymysql import Error

    if ":" in request.host:
        host, port = request.host.split(":", 1)
        port = int(port)
    else:
        host = request.host
        port = 3306

    tables = []
    try:
        connection = pymysql.connect(
            host=host,
            port=port,
            user=request.user,
            password=request.password,
            database=request.database,
            connect_timeout=5
        )
        with connection.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            table_names = [row[0] for row in cursor.fetchall()]
            for table_name in table_names:
                cursor.execute(f"DESCRIBE `{table_name}`")
                columns = cursor.rowcount
                cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
                rows = cursor.fetchone()[0]
                tables.append(TableInfo(name=table_name, columns=columns, rows=rows))
        connection.close()
        return {"tables": tables}
    except Error as e:
        raise DatabaseConnectionError(message=f"MySQL connection failed: {str(e)}")
    except Exception as e:
        raise GenerationError(message=f"Unexpected error: {str(e)}")


@router.post("/api/schema/generate", response_model=SchemaGenerateResponse, status_code=status.HTTP_201_CREATED, tags=["schema"])
async def generate_from_schema(background_tasks: BackgroundTasks, request: SchemaGenerateRequest):
    import csv
    import uuid
    import pymysql
    from pymysql import Error

    if ":" in request.host:
        host, port = request.host.split(":", 1)
        port = int(port)
    else:
        host = request.host
        port = 3306

    try:
        connection = pymysql.connect(
            host=host,
            port=port,
            user=request.user,
            password=request.password,
            database=request.database,
            connect_timeout=5
        )
        with connection.cursor() as cursor:
            cursor.execute(f"DESCRIBE `{request.table_name}`")
            columns_info = cursor.fetchall()
            column_names = [col[0] for col in columns_info]
            cursor.execute(f"SELECT * FROM `{request.table_name}` LIMIT 5")
            sample_rows = cursor.fetchall()
        connection.close()

        samples_dir = SAMPLES_DIR
        samples_dir.mkdir(parents=True, exist_ok=True)
        sample_filename = f"schema_{request.database}_{request.table_name}_{uuid.uuid4().hex[:8]}.csv"
        sample_path = samples_dir / sample_filename

        with open(sample_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(column_names)
            for row in sample_rows:
                writer.writerow(row)

        task = await task_manager.create_task(
            sample_filename=str(sample_path.relative_to(project_root)),
            table_name=request.table_name,
            rows=request.rows,
            enable_db_export=(request.output == "mysql"),
        )
        background_tasks.add_task(processor.process_task, task.id)

        return {
            "task_id": task.id,
            "message": f"Schema-based generation task created for table {request.table_name}"
        }

    except Error as e:
        raise DatabaseConnectionError(message=f"MySQL connection failed: {str(e)}")
    except Exception as e:
        raise GenerationError(message=f"Unexpected error: {str(e)}")
