
# Mockworkflow Web Interface

## Overview

The Mockworkflow web interface provides a user-friendly browser-based frontend for the Mockworkflow CLI tool. It allows you to:

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

- `mockworkflow/web/app.py` - Main FastAPI application with all routes and HTML frontend
- `mockworkflow/web/task_manager.py` - In-memory task state management with async locks
- `mockworkflow/api/app.py` - FastAPI app factory
- `mockworkflow/api/routes.py` - API router exports

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
mockworkflow web --host 0.0.0.0 --port 8000
```

**Option 2: Using the standalone script**

```bash
python run_web.py
```

**Option 3: Using uvicorn directly**

```bash
uvicorn mockworkflow.api.app:create_app --host 0.0.0.0 --port 8000 --reload
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
from mockworkflow.services.generation import build_generation_preview, generate_to_output

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

### Web界面功能状态总览

#### 1. 文件上传
| 功能 | 状态 | 说明 |
|------|------|------|
| CSV文件上传 | ✅ 已完成 | 拖拽和点击上传 |
| Excel文件上传 | ✅ 已完成 | 支持 .xls 和 .xlsx |
| 多文件批量上传 | ✅ 已完成 | 拖拽多个文件 |
| 文件列表展示 | ✅ 已完成 | samples目录文件浏览 |

#### 2. 参数配置
| 功能 | 状态 | 说明 |
|------|------|------|
| 表名配置 | ✅ 已完成 | 手动输入或自动生成 |
| 行数配置 | ✅ 已完成 | 1-100000范围 |
| 数据库导出开关 | ✅ 已完成 | 导出到MySQL |

#### 3. 任务管理
| 功能 | 状态 | 说明 |
|------|------|------|
| 任务创建 | ✅ 已完成 | 单个和批量创建 |
| 任务状态显示 | ✅ 已完成 | pending/running/completed/failed |
| 任务进度显示 | ✅ 已完成 | 进度条展示 |
| 任务列表刷新 | ✅ 已完成 | 3秒自动刷新 |
| 任务取消 | ✅ 已完成 | 删除进行中任务 |
| 任务详情查看 | ✅ 已完成 | 字段信息、SQL、预览数据 |
| 持久化存储 | ❌ 未完成 | 重启后任务丢失 |
| 任务历史记录 | ❌ 未完成 | 查看历史任务 |
| 任务统计图表 | ❌ 未完成 | 可视化统计 |

#### 4. 结果展示
| 功能 | 状态 | 说明 |
|------|------|------|
| 字段信息展示 | ✅ 已完成 | 类型、语义、置信度 |
| SQL预览 | ✅ 已完成 | CREATE TABLE语句 |
| 数据表格预览 | ✅ 已完成 | 5行样例数据 |
| CSV文件下载 | ✅ 已完成 | 任务完成后可下载CSV文件 |
| JSON格式导出 | ❌ 未完成 | JSON格式输出 |
| Excel格式导出 | ❌ 未完成 | Excel格式输出 |

#### 5. 系统功能
| 功能 | 状态 | 说明 |
|------|------|------|
| 健康检查 | ✅ 已完成 | /health 接口 |
| API文档 | ✅ 已完成 | FastAPI自动生成 |
| WebSocket实时 | ❌ 未完成 | 当前3秒轮询 |
| 用户认证 | ❌ 未完成 | 登录/权限控制 |
| 任务定时调度 | ❌ 未完成 | 定时执行任务 |

