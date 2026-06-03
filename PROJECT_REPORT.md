# MockWorkflow 项目功能汇报文档

## 一、项目概述

**MockWorkflow** 是一个智能化的样例数据驱动型 Mock 数据生成与 MySQL 建表系统。

该系统通过分析 CSV/Excel/JSON 样例文件，自动推断字段类型和语义，生成 MySQL `CREATE TABLE` SQL 语句，并输出真实的 Mock 数据。整个过程由 LLM 分析和基于规则的备用引擎驱动。

## 二、核心功能

### 2.1 样例驱动的字段识别

- 支持上传 **CSV、Excel、JSON** 三种格式的文件
- 自动检测文件编码
- 自动分析列的数据类型、约束条件和语义信息

### 2.2 LLM 智能分析

- 支持 **OpenAI 兼容的 LLM**（DeepSeek、Ollama、vLLM 等）
- 高精度字段类型和语义推断
- 返回结构化的字段规格 JSON（FieldSpec）

### 2.3 规则引擎备用机制

- 内置规则引擎根据**列名**和**数据模式**推断字段类型
- 当 LLM 禁用或不可用时，自动降级到规则引擎
- 示例：`user_id` → 主键，`created_at` → 时间字段

### 2.4 规则持久化

- 高置信度（≥0.85）的 LLM 结果自动保存到本地规则存储（JSON）
- 后续运行相似列时跳过 LLM 调用，直接使用缓存规则
- 支持自定义规则存储路径和手动刷新

### 2.5 MySQL DDL 生成

- 生成完整的 `CREATE TABLE IF NOT EXISTS` SQL 语句
- 支持类型映射、主键、自增、空值约束、注释
- 使用 `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`

### 2.6 Mock 数据生成

- 使用 **Faker** 库生成真实感数据
- 基于语义策略生成（ID、时间、坐标、状态、邮箱等）
- 支持值池（Value Pool）预生成，保证数据一致性
- 支持预览模式（5行）和完整导出

### 2.7 多种输出方式

| 输出模式 | 说明 |
|---------|------|
| `preview` | 终端预览（字段信息 + SQL + 5行样例） |
| `csv` | 导出为 UTF-8 CSV 文件 |
| `mysql` | 直接写入 MySQL 数据库 |

### 2.8 批量处理功能

- 支持**一次性处理多个样例文件**
- CLI 命令：`mockworkflow batch file1.csv file2.csv --rows 100`
- Web 界面：拖拽多文件批量上传
- 支持表名前缀、数据库导出等批量参数

## 三、两种使用方式

### 3.1 CLI 命令行模式

```bash
# 预览模式
mockworkflow generate --sample-file ./samples/users.csv

# 生成 100 行并导出 CSV
mockworkflow generate --sample-file ./users.csv --rows 100 --output csv --csv-path ./output/users.csv

# 启用 LLM 分析
mockworkflow generate --sample-file ./users.csv --enable-llm --llm-model deepseek-chat

# 批量处理
mockworkflow batch samples/*.csv --rows 100 --output csv
```

### 3.2 Web 界面模式

- 启动服务：`mockworkflow web` 或 `python run_web.py`
- 浏览器访问：http://localhost:8000
- 支持文件上传、任务管理、实时状态查看、结果预览

## 四、Web API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/api/tasks` | POST | 创建单个任务 |
| `/api/tasks/batch` | POST | 批量创建任务 |
| `/api/tasks/batch-from-files` | POST | 从上传文件批量创建任务 |
| `/api/tasks` | GET | 获取任务列表 |
| `/api/tasks/{task_id}` | GET | 获取任务详情 |
| `/api/tasks/{task_id}` | DELETE | 取消任务 |
| `/api/generate/preview` | POST | 快速预览生成 |
| `/api/upload` | POST | 上传样例文件 |
| `/api/samples` | GET | 获取样例文件列表 |

## 五、配置管理

### 环境变量（`.env` 文件）

```env
# LLM 配置
MOCKWORKFLOW_LLM_ENABLED=true
MOCKWORKFLOW_LLM_MODEL=deepseek-chat
MOCKWORKFLOW_LLM_BASE_URL=https://api.deepseek.com/v1
MOCKWORKFLOW_LLM_API_KEY=your-key-here

# 规则存储配置
MOCKWORKFLOW_RULES_AUTOSAVE=true
MOCKWORKFLOW_RULES_MIN_CONFIDENCE=0.85

# 数据库导出配置
MOCKWORKFLOW_DB_EXPORT_ENABLED=false
MOCKWORKFLOW_MYSQL_URL=mysql+pymysql://user:pass@localhost:3306/dbname
```

## 六、系统架构

```
mockworkflow/
├── cli.py                  # Typer CLI 入口
├── config.py               # Pydantic 配置管理
├── schemas/                # 数据模型
│   ├── field.py            # FieldSpec, SampleProfile, TableSpec
│   ├── request.py          # 请求模型
│   └── response.py         # 响应模型
├── sample/                 # 样例文件处理
│   ├── reader.py           # CSV/Excel/JSON 读取 + 编码检测
│   └── profiler.py         # 列分析（类型、统计、模式）
├── llm/                    # LLM 分析模块
│   ├── base.py             # LLM 解析器抽象接口
│   ├── prompt.py           # 提示词模板
│   ├── openai_parser.py    # OpenAI 兼容 API 客户端
│   └── value_pool.py       # 值池生成
├── rules/                  # 规则引擎
│   ├── engine.py           # 基于列名/模式的字段推断
│   ├── detectors.py        # 常见字段类型检测器
│   └── store.py            # 规则持久化
├── mock/                   # Mock 数据生成
│   ├── generator.py        # Faker + 语义策略生成器
│   └── strategies.py      # 语义类型生成策略
├── sql/                    # SQL 生成
│   ├── generator.py        # CREATE TABLE SQL 生成
│   └── dialects.py         # SQL 类型映射
├── services/
│   └── generation.py       # 生成管道编排
├── web/                    # Web 界面
│   ├── app.py              # FastAPI + Jinja2 模板
│   └── task_manager.py     # 任务状态管理
└── api/                    # REST API
    ├── app.py              # FastAPI 应用工厂
    └── routes.py            # API 路由
```

## 七、支持的字段语义类型

| 语义类型 | 示例列名 |
|----------|----------|
| `id` | user_id, 编号 |
| `time` | created_at, 日期, update_time |
| `coordinate` | lng, latitude, 经度 |
| `status` | status, state, 状态 |
| `flag` | is_active, 是否启用 |
| `text` | name, address, 描述 |
| `phone_number` | phone, mobile, 电话 |
| `email` | email, 邮箱 |
| `url` | url, website |
| `boolean` | is_valid, enabled |
| `license_plate` | license_plate, 车牌号 |
| `company_name` | company_name, 公司名称 |
| `vehicle_model` | vehicle_model, 车型 |
| `direction` | direction, 方向 |

## 八、技术栈

- **Pydantic** — 数据验证与配置管理
- **Typer** — CLI 框架
- **Faker** — Mock 数据生成
- **SQLAlchemy / PyMySQL** — SQL 生成与 MySQL 支持
- **Pandas / OpenPyXL** — 文件读取
- **OpenAI SDK** — LLM API 客户端（兼容 DeepSeek、Ollama、vLLM）
- **FastAPI** — Web 框架
- **Uvicorn** — ASGI 服务器
- **Jinja2** — 模板引擎

## 九、使用场景

1. **数据库设计与测试** — 快速生成测试数据，验证表结构
2. **开发环境初始化** — 为新项目生成初始数据集
3. **数据迁移** — 将样例数据转换为 MySQL 表结构
4. **批量建表** — 通过批量处理一次生成多张表

## 十、功能状态总览（按工作流程分组）

### 1. 任务输入
| 功能 | 状态 | 说明 |
|------|------|------|
| CSV文件上传 | ✅ 已完成 | 支持拖拽和点击上传 |
| Excel文件上传 | ✅ 已完成 | 支持 .xls 和 .xlsx 格式 |
| JSON文件上传 | ✅ 已完成 | 支持 JSON 格式样例文件 |
| 编码自动检测 | ✅ 已完成 | 自动检测文件编码 |
| 多文件批量上传 | ✅ 已完成 | 支持拖拽多个文件 |

### 2. 字段识别与分析
| 功能 | 状态 | 说明 |
|------|------|------|
| 列数据类型分析 | ✅ 已完成 | 自动识别数值、字符串、日期等类型 |
| 列统计信息 | ✅ 已完成 | 空值比、唯一值比等统计 |
| 规则引擎推断 | ✅ 已完成 | 基于列名和数据模式推断语义 |
| LLM智能分析 | ✅ 已完成 | 调用大模型进行高精度推断 |
| 规则持久化 | ✅ 已完成 | 高置信度结果缓存复用 |
| 模型池自动选择 | ✅ 已完成 | 自动选择可用LLM模型 |
| 不确定字段重分析 | ✅ 已完成 | 对置信度低的字段二次分析 |
| 值池生成 | ✅ 已完成 | 为枚举字段生成候选值池 |

### 3. SQL生成
| 功能 | 状态 | 说明 |
|------|------|------|
| CREATE TABLE生成 | ✅ 已完成 | 生成完整DDL语句 |
| 类型映射 | ✅ 已完成 | Python类型到MySQL类型映射 |
| 主键/自增处理 | ✅ 已完成 | 自动识别主键和自增列 |
| 注释生成 | ✅ 已完成 | 生成字段中文注释 |

### 4. Mock数据生成
| 功能 | 状态 | 说明 |
|------|------|------|
| Faker数据生成 | ✅ 已完成 | 生成真实感虚拟数据 |
| 语义策略生成 | ✅ 已完成 | 按语义类型生成对应数据 |
| 预览模式 | ✅ 已完成 | 生成5行样例预览 |
| 批量数据生成 | ✅ 已完成 | 支持1-100000行生成 |

### 5. 输出与导出
| 功能 | 状态 | 说明 |
|------|------|------|
| 终端预览输出 | ✅ 已完成 | 终端显示字段信息和样例 |
| CSV文件导出 | ✅ 已完成 | UTF-8编码CSV文件 |
| MySQL数据库导出 | ✅ 已完成 | 直接写入MySQL数据库 |
| 任务结果下载 | ✅ 已完成 | Web界面下载CSV文件 |
| JSON格式导出 | ✅ 已完成 | 支持JSON格式输出（output/json_writer.py） |
| Excel格式导出 | ✅ 已完成 | 支持Excel格式输出（output/excel_writer.py） |

### 6. 任务管理
| 功能 | 状态 | 说明 |
|------|------|------|
| 任务创建 | ✅ 已完成 | 单个和批量任务创建 |
| 任务状态跟踪 | ✅ 已完成 | 实时显示任务进度 |
| 任务取消 | ✅ 已完成 | 支持取消进行中任务 |
| 任务列表展示 | ✅ 已完成 | 分页展示任务列表 |
| 持久化任务存储 | ✅ 已完成 | 任务保存到JSON文件，重启后恢复（web/task_manager.py） |
| 任务历史记录 | ✅ 已完成 | 持久化存储后自动支持历史查看 |
| 任务统计图表 | ❌ 未完成 | 生成统计可视化（需要前端图表组件） |
| 任务定时调度 | ❌ 未完成 | 支持定时/周期任务（需要定时任务模块） |

### 7. Web界面
| 功能 | 状态 | 说明 |
|------|------|------|
| 文件上传界面 | ✅ 已完成 | 拖拽上传UI |
| 参数配置界面 | ✅ 已完成 | 表名、行数等配置 |
| 任务列表界面 | ✅ 已完成 | 实时刷新任务状态 |
| 任务详情查看 | ✅ 已完成 | 查看字段信息和SQL |
| 结果预览展示 | ✅ 已完成 | 表格形式展示生成数据 |
| 多文件批量处理 | ✅ 已完成 | 批量上传和处理 |
| 3秒轮询更新 | ✅ 已完成 | 定时刷新任务状态 |
| WebSocket实时更新 | ❌ 未完成 | 改为WebSocket推送 |
| 用户认证登录 | ❌ 未完成 | 简单的登录/权限控制 |

### 8. CLI命令行
| 功能 | 状态 | 说明 |
|------|------|------|
| generate命令 | ✅ 已完成 | 单文件生成命令 |
| batch命令 | ✅ 已完成 | 批量处理命令 |
| web命令 | ✅ 已完成 | 启动Web服务 |
| 环境变量配置 | ✅ 已完成 | .env文件支持 |
| 参数覆盖配置 | ✅ 已完成 | CLI参数优先于环境变量 |

---

*文档生成日期：2026-06-03*
