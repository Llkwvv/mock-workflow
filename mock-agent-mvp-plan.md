# 智能数据 Mock 生成与建表系统 MVP 规划

本计划以快速落地一个可用 MVP 为目标，优先实现基于样例数据文件的字段识别、MySQL 建表 SQL 生成、Faker Mock 数据生成、CSV 导出与 MySQL 写入能力。

## 1. MVP 目标边界

- **交互入口**：优先提供 CLI，一次性输入样例数据文件路径、数据行数、输出方式、表名、导出路径等参数。
- **服务能力**：MVP 不建设常驻服务端，采用脚本/CLI 工具形态；核心服务模块保持解耦，后续需要 Web 前端时再补 FastAPI 包装层。
- **LLM 接入**：采用「LLM 优先、规则后补」策略。初始不内置大量规则，由大模型分析样例数据直接输出字段识别结果；后续将 LLM 的高置信度输出沉淀为可复用的规则库，逐步减少 LLM 调用成本。
- **配置管理**：支持 `.env` 文件管理敏感配置（LLM API Key、MySQL URL 等），环境变量前缀为 `MOCKAGENT_`，CLI 参数优先级高于环境变量。
- **数据库支持**：仅支持 MySQL，覆盖建表 SQL 生成与数据写入。
- **Mock 生成**：使用 Faker + 类型/字段名启发式规则生成数据；SDV/CTGAN 仅作为扩展接口预留。

## 2. 推荐目录结构

```text
mockagent/
  __init__.py
  cli.py
  main.py
  config.py
  api/
    __init__.py
    app.py
    routes.py
  services/
    __init__.py
    generation.py
  schemas/
    field.py
    request.py
    response.py
  llm/
    base.py
    prompt.py
    openai_parser.py
    uncertain_field_parser.py
  sample/
    reader.py
    profiler.py
  rules/
    engine.py
    detectors.py
  sql/
    generator.py
    dialects.py
  mock/
    generator.py
    strategies.py
  output/
    csv_writer.py
    db_writer.py
  utils/
    validators.py
    naming.py

rules/
  default_rules.json    # 规则库文件（LLM 结果沉淀 + 手动编辑）

tests/
  test_rule_parser.py
  test_sql_generator.py
  test_mock_generator.py
  test_csv_output.py
```

## 3. 核心数据模型

- **FieldSpec**：字段结构化结果，是系统内最重要的中间表示。
  - `name`：字段名，例如 `user_id`。
  - `type`：SQL 类型，例如 `VARCHAR`、`INT`、`DECIMAL`、`DATETIME`。
  - `length`：可选长度，例如 `VARCHAR(64)`。
  - `precision` / `scale`：可选小数精度，例如 `DECIMAL(10,2)`。
  - `nullable`：是否允许为空。
  - `primary_key`：是否主键。
  - `auto_increment`：是否自增。
  - `comment`：字段注释。
  - `semantic`：语义标签，例如 `id`、`time`、`coordinate`、`status`、`flag`，以及扩展类型 `license_plate`、`company_name`、`vehicle_model`、`direction`、`phone_number`、`email`、`url`、`boolean`。
  - `enum_values`：状态/枚举类字段候选值。

- **SampleProfile**：样例数据文件分析结果。
  - `file_path`：样例数据文件路径。
  - `columns`：样例文件中的列名列表。
  - `samples`：每列抽样值。
  - `row_count`：样例文件行数。
  - `confidence`：字段识别置信度。

- **TableSpec**：建表与数据生成输入。
  - `table_name`：用户指定或默认 `auto_table`。
  - `fields`：`FieldSpec[]`。
  - `dialect`：固定为 `mysql`。

## 4. 模块职责规划

### 4.1 样例数据解析与字段识别模块（LLM 优先 + 规则沉淀）

- **输入**：用户提供的样例数据文件，例如 CSV、Excel 或 JSON 文件。
- **输出**：标准化 `FieldSpec[]` JSON。
- **核心策略：LLM 优先，规则后补**：

```text
样本数据 → profiler 字段画像 → LLM 分析全量字段 → 输出 FieldSpec[]
                                    ↓
                            高置信度结果沉淀为规则
                                    ↓
                            后续同类字段命中规则 → 跳过 LLM
```

- **MVP 策略**：
  - 读取样例数据文件，抽取列名、样例值、空值比例、唯一值比例、数值范围、时间格式等特征。
  - 将全量字段画像提交给 LLM，由 LLM 一次性分析所有字段的类型、语义、约束和枚举值。
  - LLM 返回结构化 `FieldSpec[]`，经 Pydantic 校验后直接使用。
  - **规则沉淀机制**：LLM 高置信度（≥0.85）的字段识别结果自动写入本地规则库（JSON/YAML）。
  - **规则命中**：后续处理时，先检查规则库是否已有该字段名/模式的记录，命中则直接使用规则结果，跳过 LLM 调用。
  - **规则库可手动编辑**：用户可自行增删改规则，逐步积累领域知识。规则支持 `aliases`（别名匹配）和 `pattern`（正则匹配）。
  - **初始阶段不预置大量业务规则**：只保留最小技术兜底（例如文件读取、类型校验、输出格式校验），字段语义知识主要由 LLM 生成并沉淀。
  - LLM 不可用时，回退到最小技术兜底路径，而不是依赖大量内置业务规则。

### 4.2 SQL 建表生成模块

- **输入**：`TableSpec`。
- **输出**：建表 SQL 字符串。
- **MVP 能力**：
  - 支持 MySQL 建表 SQL。
  - 自动处理默认表名 `auto_table`。
  - 支持 `NOT NULL`、`PRIMARY KEY`、`AUTO_INCREMENT`。
  - 字段支持 `COMMENT`。
  - 支持 `BOOLEAN` 类型。
  - 默认生成 `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`。
  - 建表语句使用 `CREATE TABLE IF NOT EXISTS`，避免重复建表报错。

### 4.3 Mock 数据生成模块

- **输入**：`FieldSpec[]`、行数、可选时间范围。
- **输出**：`list[dict]`，并提供前 5 条预览。
- **生成策略**：
  - **ID 类**：自增整数，或随机唯一值。
  - **VARCHAR 类**：根据字段语义生成姓名、地址、邮箱、手机号、普通文本。
  - **INT 类**：普通随机整数，状态字段从枚举中选择。
  - **DECIMAL 类**：金额/价格生成合理数值；经纬度生成合法范围。
  - **DATETIME 类**：在用户指定时间段内随机生成，未指定则近一年。
  - **状态/标记类**：从预定义枚举随机选择，例如 `active/inactive`、`0/1`、`success/failed`。

### 4.4 数据输出模块

- **CSV 导出**：
  - 用户指定路径。
  - 自动创建父目录可作为可选能力。
  - 输出 UTF-8 CSV，字段顺序与 `FieldSpec[]` 保持一致。

- **数据库写入**：
  - MySQL 作为 MVP 唯一支持数据库。
  - 自动建表后批量插入。
  - 通过 SQLAlchemy Engine 或 MySQL 连接字符串配置写入目标库。

### 4.5 CLI 交互模块

- **推荐命令形式**：

```bash
mockagent generate \
  --sample-file ./samples/users.csv \
  --rows 100 \
  --table-name users \
  --output csv \
  --csv-path ./output/users.csv \
  --mysql-url mysql+pymysql://user:password@localhost:3306/mock_db
```

- **CLI 输出**：
  - 解析后的字段 JSON。
  - 建表 SQL（支持 `--schema-output-path` 输出到文件，便于手动执行）。
  - 前 5 条 Mock 数据预览。
  - 字段解析来源统计（规则命中数、LLM 解析数、兜底解析数）。
  - CSV/数据库写入成功或失败信息。

### 4.6 脚本工具执行流程

- **读取输入**：CLI 接收样例数据文件、表名、行数、输出方式等参数。
- **核心处理**：直接调用样例分析、LLM 字段识别、规则库沉淀、SQL 生成、Mock 生成和输出模块。
- **结果展示**：在终端展示字段 JSON、MySQL 建表 SQL、前 5 条 Mock 数据和执行结果。
- **扩展方式**：后续如果需要 Web 前端，可在核心服务模块外层增加 FastAPI 包装，不影响 CLI 主流程；字段规则库可独立维护，不绑定具体 UI。

## 5. 推荐依赖

- **Pydantic**：请求、响应、字段模型校验。
- **Faker**：基础 Mock 数据生成。
- **SQLAlchemy**：MySQL 建表与批量插入。
- **PyMySQL**：MySQL 驱动。
- **pandas / openpyxl**：读取 CSV、Excel 样例数据文件。
- **openai**：兼容 OpenAI API 的 LLM 调用层，支持 DeepSeek、Ollama、vLLM 等。
- **chardet**：CSV 中文编码检测与自动识别。
- **Typer 或 Click**：CLI 命令行交互。
- **python-dotenv**：读取 LLM API Key、数据库连接等配置。
- **pytest**：单元测试。

## 6. Phase 拆分与实施计划

### Phase 1：搭建 CLI 工具基础框架，并运行测试 ✅ 已完成

- **目标**：先建立可运行、可测试、可扩展的工程骨架。
- **核心基础框架**：
  - 初始化 Python 包结构和依赖管理文件（`pyproject.toml`，使用 `uv` 管理依赖）。
  - 定义 `FieldSpec`、`SampleProfile`、`TableSpec`、`ColumnProfile`、请求/响应模型。
  - 预留样例数据读取、规则引擎、LLM、SQL、Mock、输出等模块目录。
- **CLI 基础框架**：
  - MVP 阶段采用命令行 CLI 代替真实 Web UI。
  - 初始化 CLI 入口和基础命令，例如 `mockagent --help`、`mockagent generate --help`。
- **测试要求**：
  - 建立 `pytest` 测试目录。
  - 添加模型校验、CLI 启动和核心模块导入的基础测试。
  - 确保首次运行测试通过，形成后续开发基线。
- **交付物**：
  - 可执行的 CLI 命令。
  - 通过的基础单元测试。
- **实际完成**：13 项测试通过，CLI scaffold 可用。

### Phase 2：研发后端核心最小闭环 ✅ 已完成

- **目标**：先稳定核心业务能力，跑通"样例文件 → 字段 JSON → MySQL SQL → Mock 预览"的最小闭环。
- **样例数据分析能力**：
  - 读取 CSV、Excel 或 JSON 样例数据文件。
  - 自动检测文件编码（支持 UTF-8、GBK、GB2312 等中文编码）。
  - 输出列名、样例值、空值比例、唯一值比例、数值范围、时间格式和置信度。
- **字段识别能力：LLM 优先 + 最小技术兜底**：
  - LLM 启用时：将全量字段画像提交给 LLM，由 LLM 一次性分析所有字段的类型、语义、约束和枚举值。
  - LLM 未启用时：仅使用最小技术兜底（例如文件读取、类型校验、基础字段校验），不预置大量业务规则。
  - 设计 LLM Prompt、结构化 JSON 输出 Schema 和 Pydantic 校验。
  - LLM 不可用、超时或返回格式异常时，回退到最小技术兜底并明确提示。
- **SQL 与 Mock 能力**：
  - 生成 MySQL/MariaDB 建表 SQL（含字段注释、主键、AUTO_INCREMENT）。
  - 根据字段类型和语义生成 Mock 数据（Faker + 语义策略）。
  - 支持前 5 条 Mock 数据预览。
- **规则沉淀与语义增强**：
  - 设计规则库存储格式（JSON/YAML），存放字段名 → FieldSpec 的映射。
  - LLM 高置信度（≥0.85，可通过 `--rules-min-confidence` 或 `MOCKAGENT_RULES_MIN_CONFIDENCE` 调整）结果自动写入规则库。
  - 后续处理时优先查询规则库（支持字段名精确匹配和别名匹配），命中则跳过 LLM 调用。
  - 支持 `--rules-file` 指定规则库路径，并允许手动编辑规则库。
  - 扩展 `FieldSemantic` 枚举，逐步补充 `license_plate`、`company_name`、`vehicle_model`、`direction`、`phone_number`、`email`、`url` 等语义。
  - 对应 Mock 生成策略同步增强，例如车牌号生成真实格式、公司名从枚举抽样、方向限制 0-360 等。
- **输出能力**：
  - 实现 CSV 导出基础能力。
  - MySQL/MariaDB 写入能力完整实现，包括：连接校验、自动建表（先检查表是否存在，存在则跳过建表）、批量插入。
- **交付物**：
  - 可被 CLI 和后续可选服务化包装复用的核心服务。
  - 样例分析、字段识别、LLM 解析、SQL 生成、Mock 预览的单元测试。
  - 一组可复用的样例数据文件。
- **实际完成**：20 项测试通过，DeepSeek 模型接入验证通过，MariaDB 真实写入验证通过。

### Phase 3：研发命令行 UI 与端到端脚本能力 ✅ 已完成

- **目标**：在核心能力稳定后，用 CLI 承载用户交互，完成端到端脚本工具能力。
- **CLI 输入能力**：
  - 支持传入样例数据文件路径，例如 `--sample-file ./samples/users.csv`。
  - 支持指定生成行数，例如 `--rows 100`。
  - 支持指定表名，例如 `--table-name users`。
  - 支持指定输出方式，例如 `--output preview`、`--output csv`、`--output mysql`。
  - 支持指定 CSV 输出路径和 MySQL 连接字符串。
  - 支持开启或关闭 LLM，例如 `--enable-llm / --no-enable-llm`，也可通过 `.env` 的 `MOCKAGENT_LLM_ENABLED` 设置默认值。
  - 支持指定 LLM 模型、Base URL 和超时时间，敏感信息优先从 `.env` 文件或环境变量读取。
  - 支持 `--schema-output-path` 将建表 SQL 输出到文件，便于手动审阅和执行。
- **CLI 展示能力**：
  - 展示样例文件解析摘要。
  - 展示字段识别 JSON 和不确定字段列表。
  - 展示哪些字段由规则确定、哪些字段由 LLM 修正或补充。
  - 展示 MySQL 建表 SQL。
  - 展示前 5 条 Mock 数据预览。
  - 展示 CSV 导出或 MySQL 写入结果。
- **端到端脚本能力**：
  - `preview` 模式只展示字段 JSON、MySQL 建表 SQL 和前 5 条 Mock 数据。
  - `csv` 模式生成完整 Mock 数据并导出到指定 CSV 路径。
  - `mysql` 模式生成完整 Mock 数据，连接真实 MySQL/MariaDB，自动建表并批量写入。
  - LLM 未启用时使用最小规则集；LLM 启用时使用 LLM 全量分析。
  - 参数缺失、文件不存在、输出路径不可写、MySQL 连接失败时给出可读错误。
  - **MySQL/MariaDB 验证要求**（已通过）：
    - 能连接本地或远程 MySQL/MariaDB 实例 ✅
    - 能自动创建表（含字段注释、主键、索引）✅
    - 能批量插入生成的 Mock 数据 ✅
    - 连接失败、权限错误、表已存在等异常有清晰提示 ✅
    - 至少在一个真实数据库环境验证通过 ✅（MariaDB 10.11）
- **交付物**：
  - 完整 `generate` 命令。
  - 可直接安装和执行的脚本工具。
  - CLI 端到端测试。
  - 真实 MySQL/MariaDB 环境验证通过。
- **实际完成**：20 项测试通过，DeepSeek + MariaDB 全链路验证通过。

### Phase 4：真实场景验证与可选服务化扩展

- **目标**：用多种真实样例数据验证 CLI 工具，并评估是否需要服务化扩展。
- **验证流程**：
  - CLI 接收用户参数。
  - 核心模块完成样例分析、字段识别、SQL 生成、Mock 生成和数据输出。
  - CLI 展示字段 JSON、建表 SQL、前 5 条 Mock 数据和执行结果。
  - 对比 LLM 模式 vs 规则命中模式的识别准确率和耗时。
- **异常验证**：
  - 样例文件不存在或格式不支持。
  - 字段识别置信度过低。
  - LLM 不可用或返回格式异常。
  - MySQL 连接失败、建表失败或写入失败。
  - CSV 路径不可写。
- **验收场景**：
  - 使用多个不同领域的样例 CSV 文件，一条 CLI 命令完成全流程。
  - CSV 和 MySQL 两种输出链路可独立验证。
  - CLI 错误信息一致、可读、可定位。
  - 规则库积累后，同类样例的 LLM 调用次数明显下降。
- **交付物**：
  - 端到端脚本工具验证通过。
  - 后续是否增加 FastAPI/Web 前端的评估结论。
  - 可复用的联调用例和测试样例文件。

## 7. 风险与取舍

- **LLM 解析不稳定**：LLM 输出必须用 Pydantic 校验；LLM 不可用时仅回退到最小技术兜底路径，不预置大量业务规则。
- **样例数据质量不足**：样例行数过少、空值过多或字段命名混乱会影响识别准确率，需要输出置信度和不确定字段列表。
- **字段语义识别有限**：初始不内置大量业务规则，依赖 LLM 的理解能力；后续通过规则沉淀机制逐步积累领域知识，降低 LLM 依赖。
- **LLM 调用成本**：通过规则沉淀和命中机制逐步减少重复调用；同类样例文件只需首次调用 LLM。
- **大规模数据性能**：MVP 可先支持千到十万级数据；更大规模再引入分批生成和流式写入。
- **高保真数据生成**：SDV/CTGAN 暂不进入 MVP 主链路，仅保留扩展接口。

## 8. MVP 验收标准

- 用户输入样例数据文件后，可得到结构化字段 JSON。
- LLM 启用时，由 LLM 全量分析字段；LLM 未启用时，仅使用最小技术兜底。
- 可输出字段识别置信度，并标记不确定字段。
- 可基于字段 JSON 生成 MySQL/MariaDB 建表 SQL。
- 可指定生成 `N` 行 Mock 数据，并展示前 5 条。
- 可导出 CSV 到用户指定路径。
- 可写入 MySQL/MariaDB，自动创建表并插入数据。
- CLI 可一条命令完成解析、建表 SQL 生成、Mock 数据生成和输出。
- LLM 高置信度结果可自动沉淀到规则库，后续同类字段命中规则后跳过 LLM 调用。
