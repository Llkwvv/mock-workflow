# 项目目录结构说明

## 重构概述
本项目已完成从 `mockagent/` 到 `mockworkflow/` 的完整重构整理，清理了多余的缓存文件和构建产物，建立了清晰的项目结构。

## 目录结构

```
mock-workflow/
├── .gitignore              # Git忽略规则（新增）
├── .env                    # 环境变量配置
├── pyproject.toml          # 项目配置和依赖
├── run_web.py              # Web服务器启动脚本
├── README.md               # 项目主文档
├── WEB_INTERFACE.md        # Web界面文档
├── BATCH_FEATURE_SUMMARY.md # 批量功能说明
├── CHANGES_SUMMARY.md      # 变更日志
├── IMPLEMENTATION_COMPLETE.md # 完成说明
├── PROJECT_REPORT.md       # 项目报告
├── mock-workflow-mvp-plan.md # MVP计划
├── mockworkflow/           # 主包目录（重构后）
│   ├── __init__.py
│   ├── cli.py              # CLI入口（Typer）
│   ├── config.py           # 配置管理（Pydantic Settings）
│   ├── main.py             # FastAPI应用入口
│   ├── api/                # API模块
│   │   ├── __init__.py
│   │   ├── app.py          # FastAPI应用工厂
│   │   └── routes.py       # API路由
│   ├── llm/                # LLM模块
│   │   ├── __init__.py
│   │   ├── base.py         # LLM解析器基类
│   │   ├── model_pool.py   # 模型池管理
│   │   ├── openai_parser.py # OpenAI兼容API客户端
│   │   ├── prompt.py       # Prompt模板
│   │   ├── uncertain_field_parser.py # 不确定字段解析
│   │   └── value_pool.py   # 值池生成
│   ├── mock/               # Mock数据生成模块
│   │   ├── __init__.py
│   │   ├── generator.py    # Mock数据生成器
│   │   └── strategies.py   # 生成策略
│   ├── rules/              # 规则引擎模块
│   │   ├── __init__.py
│   │   ├── default_rules.json # 默认规则
│   │   ├── detectors.py    # 模式检测器
│   │   ├── engine.py       # 规则引擎
│   │   ├── models-pool.json # 模型池配置
│   │   └── store.py        # 规则持久化
│   ├── sample/             # 样本处理模块
│   │   ├── __init__.py
│   │   ├── profiler.py     # 列分析器
│   │   └── reader.py       # 文件读取器
│   ├── schemas/            # 数据模型模块
│   │   ├── __init__.py
│   │   ├── field.py        # 字段规范
│   │   ├── request.py      # 请求模型
│   │   └── response.py     # 响应模型
│   ├── services/           # 业务服务模块
│   │   ├── __init__.py
│   │   └── generation.py   # 生成编排服务
│   ├── sql/                # SQL模块
│   │   ├── __init__.py
│   │   ├── dialects.py     # SQL方言
│   │   └── generator.py    # SQL生成器
│   ├── utils/              # 工具模块
│   │   ├── __init__.py
│   │   ├── naming.py       # 命名规范化
│   │   ├── pinyin.py       # 拼音转换（新增）
│   │   └── validators.py   # 输入验证
│   └── web/                # Web界面模块
│       ├── __init__.py
│       ├── app.py          # Web应用（FastAPI + Jinja2）
│       ├── task_manager.py # 任务管理器
│       ├── tasks.json      # 任务数据
│       ├── static/         # 静态资源
│       │   ├── css/style.css
│       │   └── js/main.js
│       └── templates/      # HTML模板
│           └── index.html
├── output/                 # 生成输出目录（已清理）
├── samples/                # 样本数据文件
├── tests/                  # 测试套件
│   ├── __init__.py
│   ├── test_cli.py
│   ├── test_csv_output.py
│   ├── test_db_export.py
│   ├── test_dashscope_native.py
│   ├── test_generation_service.py
│   ├── test_health.py
│   ├── test_llm.py
│   ├── test_mock_generator.py
│   ├── test_models.py
│   ├── test_qwen3_max.py
│   ├── test_rule_engine.py
│   ├── test_sample_profiler.py
│   ├── test_sql_generator.py
│   ├── test_value_pool.py
│   ├── test_value_pool_live.py
│   └── test_web_app.py
└── .venv/                  # 虚拟环境
```

## 清理内容

### 已删除的文件/目录
1. **构建产物**
   - `mockagent.egg-info/` - 旧版构建信息
   - `mockworkflow.egg-info/` - 新版构建信息（重复）
   - 所有 `__pycache__/` 目录
   - `.pytest_cache/`

2. **IDE配置**
   - `.windsurf/` - IDE工作区配置

3. **旧模块文件**
   - `mockagent/` 目录（已全部迁移到 `mockworkflow/`）
   - 相关 `__pycache__` 文件

### 已添加的文件
1. **`.gitignore`** - 完善的忽略规则
   - Python缓存和构建文件
   - 虚拟环境目录
   - IDE配置
   - 生成的输出文件（CSV、Excel等）
   - 测试缓存

2. **`mockworkflow/` 新模块**
   - `schemas/` - Pydantic数据模型
   - `services/` - 业务服务层
   - `sql/dialects.py` - SQL方言支持
   - `utils/pinyin.py` - 拼音转换工具

## 模块功能说明

### Core Modules
- **cli.py** - 命令行接口，支持 `generate` 和 `batch` 命令
- **config.py** - 配置管理，支持环境变量和 `.env` 文件
- **main.py** - FastAPI应用入口

### Business Modules
- **sample/** - 样本文件读取和分析
- **schemas/** - 数据模型定义
- **services/** - 业务逻辑编排
- **mock/** - Mock数据生成
- **sql/** - SQL生成和方言支持

### LLM Integration
- **llm/** - LLM相关功能
  - `openai_parser.py` - OpenAI API客户端
  - `model_pool.py` - 模型自动选择
  - `uncertain_field_parser.py` - 不确定字段处理
  - `value_pool.py` - 值池生成

### Rule Engine
- **rules/** - 规则引擎
  - `engine.py` - 规则引擎核心
  - `detectors.py` - 模式检测
  - `store.py` - 规则持久化

### Web Interface
- **web/** - Web界面
  - `app.py` - FastAPI + Jinja2应用
  - `task_manager.py` - 任务管理
  - `templates/` - HTML模板
  - `static/` - CSS/JS资源

### API
- **api/** - REST API
  - `app.py` - API应用工厂
  - `routes.py` - API端点

## Git History

```
* ffe39eb - 重构: 将项目从 mockagent 重命名为 mockworkflow
* 60d47d2 - Add web interface, API routes, and test files
* a496475 - Add model pool feature for automatic model selection
* d8eeae6 - Initial commit: MockAgent project
```

## 使用方式

### CLI
```bash
# 单文件生成
mockworkflow generate --sample-file samples/users.csv --rows 100

# 批量生成
mockworkflow batch samples/*.csv --rows 100 --output csv --csv-path ./output

# 启动Web界面
mockworkflow web
```

### Web API
```bash
# 启动服务
python run_web.py
# 或
mockworkflow web

# API端点
GET  /health              - 健康检查
GET  /api/samples         - 列出样本文件
POST /api/tasks           - 创建任务
POST /api/tasks/batch     - 批量创建任务
GET  /api/tasks/{id}      - 获取任务详情
DELETE /api/tasks/{id}    - 取消任务
```

## 测试
```bash
pytest tests/
```

## 技术栈
- **CLI**: Typer
- **Web**: FastAPI, Jinja2, Uvicorn
- **Data**: Pydantic, Pandas
- **Database**: SQLAlchemy, PyMySQL
- **Mock**: Faker
- **LLM**: OpenAI SDK (兼容DeepSeek/Ollama等)
