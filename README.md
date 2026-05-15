# MockAgent

**Intelligent sample-driven mock data generation and MySQL table creation system.**

MockAgent is a CLI tool that analyzes sample data files (CSV, Excel, JSON), automatically infers field types and semantics, generates MySQL `CREATE TABLE` SQL, and produces realistic mock data — all powered by LLM analysis and a rule-based fallback engine.

## Features

- **Sample-Driven Field Recognition**: Upload a CSV/Excel/JSON file; MockAgent automatically infers column types, constraints, and semantics.
- **LLM-Powered Analysis**: Uses OpenAI-compatible LLMs (DeepSeek, Ollama, vLLM, etc.) for high-accuracy field type and semantic inference.
- **Rule Engine Fallback**: Built-in rule engine infers fields from column names and data patterns when LLM is disabled or unavailable.
- **Rule Persistence**: High-confidence LLM results are automatically saved to a local rule store (JSON), reducing future LLM calls.
- **MySQL DDL Generation**: Generates `CREATE TABLE IF NOT EXISTS` SQL with proper types, primary keys, auto-increment, nullability, comments, and `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`.
- **Mock Data Generation**: Produces realistic fake data using Faker, semantic strategies, and value pools — with preview (5 rows) and full export support.
- **CSV Export**: Exports generated mock data to UTF-8 CSV files.
- **CLI-First Design**: Single-command workflow from sample file to SQL and data.
- **`.env` Configuration**: Sensitive settings (API keys, DB URLs) managed via `.env` file with `MOCKAGENT_` prefix.

## Quick Start

### Installation

```bash
pip install -e .
```

### Basic Usage

```bash
# Preview mode — show field JSON, CREATE TABLE SQL, and 5 sample rows
mockagent generate --sample-file ./samples/users.csv

# Generate 100 rows and export to CSV
mockagent generate \
  --sample-file ./samples/users.csv \
  --rows 100 \
  --output csv \
  --csv-path ./output/users.csv

# Enable LLM for more accurate field inference (DeepSeek example)
mockagent generate \
  --sample-file ./samples/users.csv \
  --rows 100 \
  --enable-llm \
  --llm-model deepseek-chat \
  --llm-base-url https://api.deepseek.com/v1 \
  --llm-api-key YOUR_API_KEY

# Save CREATE TABLE SQL to a file
mockagent generate \
  --sample-file ./samples/users.csv \
  --schema-output-path ./output/schema.sql

# Use a custom rule store and disable autosave
mockagent generate \
  --sample-file ./samples/users.csv \
  --rules-file ./rules/my_rules.json \
  --no-rules-autosave
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--sample-file` | Path to sample data file (CSV/Excel/JSON) | *required* |
| `--rows` | Number of mock rows to generate | `100` |
| `--table-name` | Target MySQL table name | `auto_table` |
| `--output` | Output mode: `preview` or `csv` | `preview` |
| `--csv-path` | CSV output path (required when `--output csv`) | — |
| `--schema-output-path` | Write CREATE TABLE SQL to file | (stdout) |
| `--rules-file` | Path to rule store JSON file | `mockagent/rules/default_rules.json` |
| `--rules-autosave / --no-rules-autosave` | Auto-save high-confidence LLM results | `true` |
| `--refresh-rules` | Bypass rule cache, force LLM for all columns | `false` |
| `--rules-min-confidence` | Min LLM confidence to save to rule store | `0.85` |
| `--enable-llm / --no-enable-llm` | Enable LLM for field inference | `false` |
| `--llm-model` | LLM model name | (from env) |
| `--llm-base-url` | LLM API base URL | (from env) |
| `--llm-api-key` | LLM API key | (from env) |
| `--llm-timeout` | LLM request timeout (seconds) | `90` |
| `--llm-temperature` | LLM temperature (0–2) | `0.1` |
| `--enable-value-pool / --no-enable-value-pool` | Generate per-field value pools via LLM | `false` |
| `--value-pool-size` | Target values per pool | `50` |

### Environment Variables

All CLI options can also be set via `.env` file with the `MOCKAGENT_` prefix:

```env
MOCKAGENT_LLM_ENABLED=true
MOCKAGENT_LLM_MODEL=deepseek-chat
MOCKAGENT_LLM_BASE_URL=https://api.deepseek.com/v1
MOCKAGENT_LLM_API_KEY=your-key-here
MOCKAGENT_RULES_AUTOSAVE=true
MOCKAGENT_RULES_MIN_CONFIDENCE=0.85
MOCKAGENT_RULES_FILE=./rules/default_rules.json
MOCKAGENT_LLM_VALUE_POOL_ENABLED=true
MOCKAGENT_LLM_VALUE_POOL_SIZE=50
```

## Architecture

```
mockagent/
├── cli.py                  # Typer-based CLI entry point
├── main.py                 # Application entry
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
│   └── uncertain_field_parser.py  # Uncertain field re-analysis
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
│   ├── csv_writer.py       # CSV export
│   └── db_writer.py        # MySQL bulk insert (planned)
├── services/
│   └── generation.py       # Orchestrates the full generation pipeline
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
mockagent generate --sample-file ./samples/users.csv --rows 10 --enable-llm --llm-model deepseek-chat
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