# mock-workflow

**Intelligent sample-driven mock data generation and MySQL table creation system.**

mock-workflow (formerly MockAgent) is a CLI tool that analyzes sample data files (CSV, Excel, JSON), automatically infers field types and semantics, generates MySQL `CREATE TABLE` SQL, and produces realistic mock data — all powered by LLM analysis and a rule-based fallback engine.

**MVP entry points**: both `mockworkflow generate` (CLI, scripted batch use) and `mockworkflow web` (Web UI, interactive upload + task management) are supported MVP entry points and share the same generation core.

## Features

- **Sample-Driven Field Recognition**: Upload a CSV/Excel/JSON file; mock-workflow automatically infers column types, constraints, and semantics.
- **LLM-Powered Analysis**: Uses OpenAI-compatible LLMs (DeepSeek, Ollama, vLLM, etc.) for high-accuracy field type and semantic inference.
- **Rule Engine Fallback**: Built-in rule engine infers fields from column names and data patterns when LLM is disabled or unavailable.
- **Rule Persistence**: High-confidence LLM results are automatically saved to a local rule store (JSON), reducing future LLM calls.
- **MySQL DDL Generation**: Generates `CREATE TABLE IF NOT EXISTS` SQL with proper types, primary keys, auto-increment, nullability, comments, and `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`.
- **Mock Data Generation**: Produces realistic fake data using Faker, semantic strategies, and value pools — with preview (5 rows) and full export support.
- **CSV Export**: Exports generated mock data to UTF-8 CSV files.
- **CLI-First Design**: Single-command workflow from sample file to SQL and data.
- **`.env` Configuration**: Sensitive settings (API keys, DB URLs) managed via `.env` file with `MOCKWORKFLOW_` prefix.

## Quick Start

### Installation

```bash
# Install in the current environment or venv
pip install -e .

# Or use the project's virtual environment
source .venv/bin/activate
pip install -e .
```

> **Note**: After installation, you can run `mockworkflow` directly if it's in your PATH. Otherwise use `.venv/bin/mockworkflow` or activate the venv with `source .venv/bin/activate`.

### Starting the Web Interface

```bash
# Start the web interface (default: http://localhost:8000)
mockworkflow web

# Custom host and port
mockworkflow web --host 127.0.0.0 --port 8080

# Or use the standalone script
python run_web.py
```

### Basic Usage

```bash
# Preview mode — show field JSON, CREATE TABLE SQL, and 5 sample rows
mockworkflow generate --sample-file ./samples/users.csv

# Generate 100 rows and export to CSV
mockworkflow generate \
  --sample-file ./samples/users.csv \
  --rows 100 \
  --output csv \
  --csv-path ./output/users.csv

# Enable LLM for more accurate field inference (DeepSeek example)
mockworkflow generate \
  --sample-file ./samples/users.csv \
  --rows 100 \
  --enable-llm \
  --llm-model deepseek-chat \
  --llm-base-url https://api.deepseek.com/v1 \
  --llm-api-key YOUR_API_KEY

# Save CREATE TABLE SQL to a file
mockworkflow generate \
  --sample-file ./samples/users.csv \
  --schema-output-path ./output/schema.sql

# Use a custom rule store and disable autosave
mockworkflow generate \
  --sample-file ./samples/users.csv \
  --rules-file ./rules/my_rules.json \
  --no-rules-autosave

# Use model pool for automatic model selection
mockworkflow generate \
  --sample-file ./samples/users.csv \
  --enable-llm \
  --models-pool-file ./rules/models-pool.json
```

### Batch Processing (New Feature! 🚀)

Process multiple sample files at once:

```bash
# Batch process multiple files
mockworkflow batch samples/users.csv samples/vehicles.csv samples/taizhou.csv \
  --rows 100 \
  --output csv \
  --csv-path ./output/batch

# Batch process with table name prefix
mockworkflow batch samples/users.csv samples/vehicles.csv \
  --rows 50 \
  --table-prefix myapp_ \
  --output preview

# Batch process with database export
mockworkflow batch samples/*.csv \
  --rows 1000 \
  --enable-db-export \
  --output mysql

# Batch process with LLM field inference
mockworkflow batch samples/*.csv \
  --rows 100 \
  --enable-llm \
  --llm-model deepseek-chat
```

In the Web interface, click **"➕ 批量导入文件"** (or "➕ Batch Import") to drag-and-drop multiple files for batch processing!

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--sample-file` | Path to sample data file (CSV/Excel/JSON) | *required* |
| `--rows` | Number of mock rows to generate | `100` |
| `--table-name` | Target MySQL table name | `auto_table` |
| `--output` | Output mode: `preview`, `csv`, or `mysql` | `preview` |
| `--csv-path` | CSV output path (required when `--output csv`) | — |
| `--schema-output-path` | Write CREATE TABLE SQL to file | (stdout) |
| `--rules-file` | Path to rule store JSON file | (auto) |
| `--models-pool-file` | Path to models pool JSON file | (auto) |
| `--rules-autosave / --no-rules-autosave` | Auto-save high-confidence LLM results | `true` |
| `--refresh-rules` | Bypass rule cache, force LLM for all columns | `false` |
| `--rules-min-confidence` | Min LLM confidence to save to rule store | `0.85` |
| `--enable-llm / --no-enable-llm` | Enable LLM for field inference | `false` |
| `--disable-llm / --no-disable-llm` | Disable LLM (overrides --enable-llm) | `false` |
| `--llm-model` | LLM model name | (from env) |
| `--llm-base-url` | LLM API base URL | (from env) |
| `--llm-api-key` | LLM API key | (from env) |
| `--llm-timeout` | LLM request timeout (seconds) | `90` |
| `--llm-temperature` | LLM temperature (0–2) | `0.1` |
| `--enable-value-pool / --no-enable-value-pool` | Generate per-field value pools via LLM | `false` |
| `--value-pool-size` | Target values per pool | `50` |

### Environment Variables

All CLI options can also be set via `.env` file with the `MOCKWORKFLOW_` prefix:

```env
# LLM Settings
MOCKWORKFLOW_LLM_ENABLED=true
MOCKWORKFLOW_LLM_MODEL=deepseek-chat
MOCKWORKFLOW_LLM_BASE_URL=https://api.deepseek.com/v1
MOCKWORKFLOW_LLM_API_KEY=your-key-here
MOCKWORKFLOW_LLM_TIMEOUT=90
MOCKWORKFLOW_LLM_TEMPERATURE=0.1

# Rule Store Settings
MOCKWORKFLOW_RULES_AUTOSAVE=true
MOCKWORKFLOW_RULES_MIN_CONFIDENCE=0.85
MOCKWORKFLOW_RULES_FILE=./rules/default_rules.json

# Value Pool Settings
MOCKWORKFLOW_LLM_VALUE_POOL_ENABLED=true
MOCKWORKFLOW_LLM_VALUE_POOL_SIZE=50

# Model Pool Settings
MOCKWORKFLOW_LLM_MODELS_POOL_FILE=./rules/models-pool.json

# Database Export Settings (auto table creation + one-directional export, MySQL only)
# Master switch — disabled by default. When false, no table is created and no data is exported.
MOCKWORKFLOW_DB_EXPORT_ENABLED=false
MOCKWORKFLOW_MYSQL_URL=mysql+pymysql://user:pass@127.0.0.1:3306/dbname
```

**Database export** (`--output mysql` for the CLI, `enable_db_export` for the Web API) is gated by the `MOCKWORKFLOW_DB_EXPORT_ENABLED` master toggle. When enabled, the target table is created if it does not exist (`CREATE TABLE IF NOT EXISTS`) and generated rows are inserted (one-directional, MySQL only, no schema migration or conflict-resolution). When the toggle is disabled, selecting the `mysql` output produces a readable error and performs no database operations.

## Web API

The web interface provides a REST API for programmatic access. Start the server with:

```bash
mockworkflow web
# or
python run_web.py
```

### API Endpoints

#### Health Check
```bash
curl http://localhost:8000/health
```

#### Create Single Task
```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "sample_filename": "samples/users.csv",
    "table_name": "users",
    "rows": 100,
    "enable_db_export": false
  }'
```

#### Create Batch Tasks
```bash
curl -X POST http://localhost:8000/api/tasks/batch \
  -H "Content-Type: application/json" \
  -d '{
    "tasks": [
      {"sample_filename": "samples/users.csv", "table_name": "users", "rows": 100},
      {"sample_filename": "samples/vehicles.csv", "table_name": "vehicles", "rows": 100}
    ],
    "auto_table_name": false
  }'
```

#### Create Batch Tasks from Uploaded Files
```bash
curl -X POST http://localhost:8000/api/tasks/batch-from-files \
  -F "files=@samples/users.csv" \
  -F "files=@samples/vehicles.csv" \
  -F "rows=100" \
  -F "enable_db_export=false"
```

#### List Tasks
```bash
curl http://localhost:8000/api/tasks?limit=50
```

#### Get Task Details
```bash
curl http://localhost:8000/api/tasks/{task_id}
```

#### Cancel Task
```bash
curl -X DELETE http://localhost:8000/api/tasks/{task_id}
```

#### Preview Generation
```bash
curl -X POST http://localhost:8000/api/generate/preview \
  -H "Content-Type: application/json" \
  -d '{
    "sample_file": "samples/users.csv",
    "rows": 5,
    "table_name": "users"
  }'
```

#### List Sample Files
```bash
curl http://localhost:8000/api/samples
```

#### Upload File
```bash
curl -X POST http://localhost:8000/api/upload \
  -F "file=@path/to/your/file.csv"
```

## Architecture

```
mockworkflow/
├── cli.py                  # Typer-based CLI entry point
├── config.py               # Settings management (pydantic-settings)
├── schemas/
│   ├── field.py            # FieldSpec, SampleProfile, TableSpec models
│   ├── request.py          # GenerateRequest schema
│   └── response.py         # GenerationResult response model
├── sample/
│   ├── reader.py           # CSV/Excel/JSON file reader with encoding detection
│   └── profiler.py         # Column profiling (types, stats, patterns)
├── llm/
│   ├── base.py             # LLM parser abstract interface
│   ├── prompt.py           # LLM prompt templates
│   ├── openai_parser.py    # OpenAI-compatible API client
│   ├── uncertain_field_parser.py  # Uncertain field re-analysis
│   └── value_pool.py       # LLM-powered value pool generation
├── rules/
│   ├── engine.py           # Rule-based field inference from column names/data
│   ├── detectors.py        # Pattern detectors for common field types
│   └── store.py            # Rule persistence (JSON read/write)
├── mock/
│   ├── generator.py        # Mock data generation (Faker + semantic strategies)
│   └── strategies.py       # Per-semantic generation strategies
├── sql/
│   ├── generator.py        # MySQL CREATE TABLE SQL generation
│   └── dialects.py         # SQL type mappings
├── output/
│   └── csv_writer.py       # CSV export
├── services/
│   └── generation.py       # Orchestrates the full generation pipeline
├── web/
│   ├── app.py             # Web interface (FastAPI + Jinja2 templates)
│   └── task_manager.py    # Task state management
├── api/
│   ├── app.py             # FastAPI app factory
│   └── routes.py          # API endpoints
└── utils/
    ├── naming.py           # Name normalization utilities
    └── validators.py       # Input validation
```

## How It Works

1. **Read & Profile**: The sample file is read with automatic encoding detection. Each column is profiled (data type, null ratio, unique ratio, sample values, patterns).

2. **Rule Engine**: The built-in rule engine infers field types and semantics from column names and data patterns (e.g., columns ending in `_id` → primary key, columns containing `时间` → datetime).

3. **LLM Analysis** (optional): When enabled, all field profiles are sent to the LLM in a single request. The LLM returns structured `FieldSpec` JSON with types, semantics, constraints, and enum values.

4. **Rule Persistence**: High-confidence LLM results (≥0.85, configurable) are automatically saved to the rule store. Subsequent runs with similar columns skip the LLM call.

5. **SQL Generation**: A `CREATE TABLE IF NOT EXISTS` statement is generated with proper MySQL types, constraints, and comments.

6. **Mock Data Generation**: Using Faker and semantic strategies, realistic mock data is generated. Value pools can be pre-generated via LLM for consistency.

7. **Output**: Results are displayed in the terminal or exported to CSV.

## Field Semantics

The system recognizes these semantic types:

| Semantic | Examples |
|----------|----------|
| `id` | `user_id`, `编号` |
| `time` | `created_at`, `日期`, `update_time` |
| `coordinate` | `lng`, `latitude`, `经度` |
| `status` | `status`, `state`, `状态` |
| `flag` | `is_active`, `是否启用` |
| `text` | `name`, `address`, `描述` |
| `phone_number` | `phone`, `mobile`, `电话` |
| `email` | `email`, `邮箱` |
| `url` | `url`, `website` |
| `boolean` | `is_valid`, `enabled` |
| `license_plate` | `license_plate`, `车牌号` |
| `company_name` | `company_name`, `公司名称` |
| `vehicle_model` | `vehicle_model`, `车型` |
| `direction` | `direction`, `方向` |

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run CLI
mockworkflow generate --sample-file ./samples/users.csv --rows 10 --enable-llm --llm-model deepseek-chat

# Run web interface
mockworkflow web

# Or run web server with Python
python run_web.py
```

## Dependencies

- **pydantic** — Data validation and settings
- **typer** — CLI framework
- **faker** — Mock data generation
- **sqlalchemy** / **pymysql** — SQL generation and MySQL support
- **pandas** / **openpyxl** — File reading
- **openai** — LLM API client (compatible with DeepSeek, Ollama, vLLM, etc.)
- **python-dotenv** — Environment variable management

## License

MIT