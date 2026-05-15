
# MockAgent Web Interface

## Overview

The MockAgent web interface provides a user-friendly browser-based frontend for the MockAgent CLI tool. It allows you to:

1. **Upload sample files** (CSV, Excel) for mock data generation
2. **Submit generation tasks** with custom table names and row counts
3. **View task status** in real-time (pending, running, completed, failed, cancelled)
4. **Preview generated data** with field information and SQL schema
5. **Cancel running tasks**

## Architecture

The web interface is built on:
- **FastAPI** - Modern async web framework
- **Jinja2** - Template engine (inline HTML/CSS/JS)
- **Python-Multipart** - File upload handling
- **AIOFiles** - Async file I/O

### Key Components

- `mockagent/web/app.py` - Main FastAPI application with all routes and HTML frontend
- `mockagent/web/task_manager.py` - In-memory task state management with async locks
- `mockagent/api/app.py` - FastAPI app factory
- `mockagent/api/routes.py` - API router exports

## Installation

The web dependencies are already included in the main `pyproject.toml`:

```toml
dependencies = [
    ...
    "fastapi>=0.104,<1.0",
    "uvicorn[standard]>=0.24,<1.0",
    "python-multipart>=0.0.6,<1.0",
    "jinja2>=3.1,<4.0",
    "aiofiles>=23.0,<25.0"
]
```

Install them with:

```bash
pip install -e .
# or
pip install fastapi uvicorn python-multipart jinja2 aiofiles
```

## Usage

### Starting the Web Server

**Option 1: Using the CLI command**

```bash
mockagent web --host 0.0.0.0 --port 8000
```

**Option 2: Using the standalone script**

```bash
python run_web.py
```

**Option 3: Using uvicorn directly**

```bash
uvicorn mockagent.api.app:create_app --host 0.0.0.0 --port 8000 --reload
```

Then open your browser to: **http://localhost:8000**

### Using the Web Interface

#### 1. Upload a Sample File

- Click or drag-and-drop a CSV or Excel file into the upload area
- Supported formats: `.csv`, `.xlsx`, `.xls`
- The file is saved to the `samples/` directory

#### 2. Configure Generation Parameters

- **Table Name**: The target MySQL table name (default: `auto_table`)
- **Rows**: Number of mock rows to generate (1-100,000)

#### 3. Submit the Task

Click "提交生成" (Submit Generation). The task will be:
- Queued for processing
- Executed in the background
- Updated in real-time

#### 4. Monitor Task Progress

The task list shows:
- **Status badges**: Pending (yellow), Running (blue), Completed (green), Failed (red), Cancelled (gray)
- **Progress bar**: For running/pending tasks
- **Task details**: Filename, table name, row count, creation time
- **Actions**: Cancel (for running/pending), View preview (for completed)

#### 5. Preview Results

Click "查看" (View) on a completed task to see:

- **Preview Data Tab**: First 5 generated rows in a table
- **Fields Info Tab**: Detailed field information including:
  - Field name and SQL type
  - Length, precision, scale
  - Semantic type (ID, time, coordinate, etc.)
  - Nullable constraint
  - Confidence score (for LLM-resolved fields)
  - Enum values or value pools
- **SQL Schema Tab**: Generated `CREATE TABLE` SQL statement

### Quick Preview (Without Full Task)

Use the "预览字段结构" (Preview Field Structure) button to generate a quick preview without creating a full task. This runs the generation synchronously and shows results immediately.

## API Endpoints

### Health Check

```
GET /health
```

Returns server health status.

**Response:**
```json
{"status": "ok", "timestamp": "2026-05-15T10:30:00"}
```

---

### Create Task

```
POST /api/tasks
Content-Type: application/json
```

**Request Body:**
```json
{
  "sample_filename": "samples/users.csv",
  "table_name": "users",
  "rows": 100
}
```

**Response (201 Created):**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Task created and queued for processing"
}
```

---

### Get Task Status

```
GET /api/tasks/{task_id}
```

**Response (200 OK):**
```json
{
  "task": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "sample_filename": "samples/users.csv",
    "table_name": "users",
    "rows": 100,
    "status": "completed",
    "progress": 100,
    "error_message": null,
    "created_at": "2026-05-15T10:30:00",
    "started_at": "2026-05-15T10:30:01",
    "completed_at": "2026-05-15T10:30:05",
    "result_preview": { ... },
    "result_full": { ... }
  }
}
```

---

### List All Tasks

```
GET /api/tasks?limit=50
```

**Response (200 OK):**
```json
{
  "tasks": [
    { ... }  // Array of task objects
  ],
  "total": 10
}
```

**Query Parameters:**
- `limit` (int, default: 50): Maximum number of tasks to return

---

### Cancel Task

```
DELETE /api/tasks/{task_id}
```

**Response (200 OK):**
```json
{"message": "Task cancelled"}
```

---

### Generate Preview (Synchronous)

```
POST /api/generate/preview
Content-Type: application/json
```

**Request Body:**
```json
{
  "sample_file": "samples/users.csv",
  "rows": 100,
  "table_name": "users"
}
```

**Response (200 OK):**
```json
{
  "task_id": "sync",
  "preview": {
    "row_count": 3,
    "columns": ["id", "name", "email"]
  },
  "fields": [
    {
      "name": "id",
      "type": "INT",
      "nullable": false,
      ...
    }
  ],
  "create_table_sql": "CREATE TABLE IF NOT EXISTS `users` ...",
  "preview_rows": [
    {"id": 1, "name": "张三", "email": "zhangsan@example.com"},
    ...
  ]
}
```

---

### Upload File

```
POST /api/upload
Content-Type: multipart/form-data
```

**Form Data:**
- `file`: The file to upload (CSV, XLS, or XLSX)

**Response (200 OK):**
```json
{
  "message": "File uploaded successfully",
  "filename": "users.csv",
  "filepath": "samples/users.csv"
}
```

---

## Task Status Flow

```
[PENDING] → [RUNNING] → [COMPLETED]
    ↓            ↓           ↓
  (queued)   (processing)  (done)
    ↓            ↓
[CANCELLED]  [FAILED]
```

- **PENDING**: Task created, waiting to be processed
- **RUNNING**: Task is being processed (field resolution, SQL generation, mock data generation)
- **COMPLETED**: Task finished successfully, results available
- **FAILED**: Task failed due to an error, error message available
- **CANCELLED**: Task was cancelled before completion

## Integration with Existing Code

The web interface reuses the existing generation service without modification:

```python
from mockagent.services.generation import build_generation_preview, generate_to_output

# Build preview (field resolution, SQL generation, 5-row preview)
preview = build_generation_preview(
    sample_file="samples/users.csv",
    table_name="users",
    rows=5,
    settings=settings,
)

# Generate full output (if rows > 5)
result = generate_to_output(
    sample_file="samples/users.csv",
    table_name="users",
    rows=100,
    output="csv",
    csv_path=None,
    settings=settings,
    preview=preview,
)
```

## Thread Safety

The `TaskManager` uses `asyncio.Lock` to ensure thread-safe operations:

- Concurrent task creation
- Status updates from multiple background tasks
- Task cancellation during processing
- Listing tasks while others are being updated

## Error Handling

### File Validation
- Invalid file types are rejected with 400 Bad Request
- Non-existent files are rejected with 422 Unprocessable Entity

### Task Processing
- Errors during generation are caught and stored in `error_message`
- Task status is set to `FAILED`
- Error details are available via the task detail endpoint

### API Errors
- 400: Bad request (invalid parameters)
- 404: Resource not found
- 422: Validation error
- 500: Internal server error

## Browser Compatibility

The web interface uses vanilla JavaScript (no frameworks) and is compatible with:
- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)
- Mobile browsers (iOS Safari, Chrome for Android)

## Performance Considerations

- **In-memory task storage**: Tasks are stored in memory and will be lost on server restart
- **Background processing**: Uses FastAPI's `BackgroundTasks` for non-blocking task execution
- **Auto-refresh**: Task list refreshes every 3 seconds
- **File upload**: Files are read into memory (suitable for sample files < 100MB)

## Future Enhancements

Potential improvements:
- Persistent task storage (SQLite, Redis)
- Task result export (download CSV)
- Multiple file upload
- Task scheduling/cron jobs
- User authentication
- Task history and statistics
- WebSocket for real-time updates

