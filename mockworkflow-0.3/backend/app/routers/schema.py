"""MySQL schema reverse-engineering endpoints."""
import csv
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field

from backend.app.deps import SAMPLES_DIR, project_root, task_manager
from backend.app import processor

router = APIRouter()


def _validate_table_name(name: str) -> str:
    if not re.match(r'^[a-zA-Z0-9_]+$', name):
        raise ValueError(f"Invalid table name: {name}")
    return name


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


@router.post("/api/schema/tables", response_model=SchemaTablesResponse, tags=["schema"])
async def list_schema_tables(request: SchemaConnectRequest):
    """Connect to MySQL and list all tables with column counts."""
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
                _validate_table_name(table_name)
                cursor.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s", (request.database, table_name))
                columns = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM `{}`".format(table_name))
                rows = cursor.fetchone()[0]
                tables.append(TableInfo(name=table_name, columns=columns, rows=rows))
        connection.close()
        return {"tables": tables}
    except Error as e:
        raise HTTPException(status_code=400, detail=f"MySQL connection failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


@router.post("/api/schema/generate", response_model=SchemaGenerateResponse, status_code=status.HTTP_201_CREATED, tags=["schema"])
async def generate_from_schema(background_tasks: BackgroundTasks, request: SchemaGenerateRequest):
    """Generate mock data from a MySQL table schema."""
    import pymysql
    from pymysql import Error

    _validate_table_name(request.table_name)

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
            cursor.execute("DESCRIBE `{}`".format(request.table_name))
            columns_info = cursor.fetchall()
            column_names = [col[0] for col in columns_info]
            cursor.execute("SELECT * FROM `{}` LIMIT 5".format(request.table_name))
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
        raise HTTPException(status_code=400, detail=f"MySQL connection failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
