"""Engine diagnostics routes: expose internal state for the frontend engine page."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.state import project_root, SAMPLES_DIR
from backend.config import get_settings
from backend.schemas.field import FieldSemantic, FieldSpec, SampleProfile, SqlType

router = APIRouter()


# --------------------------------------------------------------------------- #
# Response models
# --------------------------------------------------------------------------- #

class FieldDiagnostic(BaseModel):
    name: str
    sql_type: str
    semantic: str
    confidence: float
    strategy_layer: str = ""
    strategy_desc: str = ""
    nullable: bool = True
    enum_values: list[str] = Field(default_factory=list)
    value_pool_size: int = 0
    has_value_pool: bool = False
    distribution: dict | None = None
    min_value: float | None = None
    max_value: float | None = None
    unique_ratio: float | None = None
    null_ratio: float | None = None


class CoherenceLink(BaseModel):
    description: str
    fields: list[str]
    category: str  # "identity" | "region" | "postal" | "credit" | "bank"


class ConstraintInfo(BaseModel):
    expression: str
    fields: list[str]
    confidence: float


class RagMatch(BaseModel):
    column: str
    matched_rule: str
    matched_semantic: str
    distance: float
    confidence: float


class ResolutionStats(BaseModel):
    total_columns: int
    rule_store_hits: int
    rag_hits: int
    llm_resolved: int
    fallback_resolved: int
    value_pools_generated: int
    llm_used: bool
    model_used: str | None = None


class ModelInfo(BaseModel):
    name: str
    enabled: bool
    priority: int
    description: str | None = None


class EngineStatus(BaseModel):
    models: list[ModelInfo]
    working_model: str | None
    rules_count: int
    rules_file: str
    rag_rules_count: int
    rag_samples_count: int
    cache_size: int
    cache_maxsize: int


class AnalyzeRequest(BaseModel):
    sample_file: str = Field(default="", description="Sample file path relative to project root")


class AnalyzeResponse(BaseModel):
    sample_file: str
    row_count: int
    columns: list[str]
    fields: list[FieldDiagnostic]
    coherence_links: list[CoherenceLink]
    constraints: list[ConstraintInfo]
    rag_matches: list[RagMatch]
    resolution: ResolutionStats
    create_table_sql: str = ""


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


@router.get("/api/engine/status", tags=["engine"])
async def engine_status():
    """Return engine-level status: models, rules, RAG indices, cache."""
    settings = get_settings()

    # -- Model pool --
    from backend.llm.model_pool import get_model_pool
    pool = get_model_pool()
    enabled_models = pool.get_enabled_models()
    models = [
        ModelInfo(
            name=m.name,
            enabled=m.enabled,
            priority=m.priority,
            description=m.description,
        )
        for m in enabled_models
    ]
    working = pool.find_working_model(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout,
    )

    # -- Rule store --
    from backend.rules.store import RuleStore
    store = RuleStore(settings.rules_file)
    rules = store.load_rules()
    rules_count = len(rules)

    # -- RAG vector indices --
    rag_rules_count = 0
    rag_samples_count = 0
    try:
        from backend.app.state import get_vector_store
        vs = get_vector_store()
        rag_rules_count = vs.count("rules")
        rag_samples_count = vs.count("samples")
    except Exception:
        pass

    # -- Cache --
    from backend.cache import get_app_cache
    cache = get_app_cache()
    cache_info = cache.info()

    return EngineStatus(
        models=models,
        working_model=working,
        rules_count=rules_count,
        rules_file=str(settings.rules_file),
        rag_rules_count=rag_rules_count,
        rag_samples_count=rag_samples_count,
        cache_size=cache_info["size"],
        cache_maxsize=cache_info["maxsize"],
    )


@router.post("/api/engine/analyze", response_model=AnalyzeResponse, tags=["engine"])
async def engine_analyze(request: AnalyzeRequest):
    """Run the full analysis pipeline on a sample file and return diagnostics."""
    settings = get_settings()

    sample_file = request.sample_file
    if not sample_file:
        # Default to first available sample
        samples_dir = SAMPLES_DIR
        if samples_dir.exists():
            csv_files = sorted(samples_dir.glob("*.csv"))
            if csv_files:
                sample_file = str(csv_files[0].relative_to(project_root))
    if not sample_file:
        raise HTTPException(status_code=400, detail="No sample file available")

    full_path = project_root / sample_file
    if not full_path.exists():
        raise HTTPException(status_code=404, detail=f"Sample file not found: {sample_file}")

    # -- Step 1: Profile the sample --
    from backend.sample.profiler import analyze_sample_file
    profile = analyze_sample_file(str(full_path))

    # -- Step 2: Resolve fields (rule store -> RAG -> LLM -> fallback) --
    from backend.llm.uncertain_field_parser import resolve_fields
    resolution = resolve_fields(profile, settings=settings)
    fields = resolution.fields

    # -- Step 3: Enrich with sample data --
    from backend.services.generation import _enrich_fields_with_sample_data
    _enrich_fields_with_sample_data(fields, profile)

    # -- Step 4: Infer constraints --
    from backend.agent.tools.constraint import infer_field_constraints
    constraints_raw = infer_field_constraints(fields)
    for field in fields:
        relevant = [c for c in constraints_raw if field.name in c.fields]
        if relevant:
            field.constraints = relevant

    # -- Step 5: Attach distribution info --
    for field in fields:
        col_profile = profile.column_profiles.get(field.name)
        if col_profile and col_profile.distribution:
            field.distribution = col_profile.distribution

    # -- Step 6: Detect coherence links --
    from backend.mock.coherence import detect_roles
    roles = detect_roles(fields)
    coherence_links = _build_coherence_links(roles)

    # -- Step 7: RAG matching diagnostics --
    rag_matches = _build_rag_matches(profile, fields)

    # -- Step 8: Build field diagnostics with strategy layer info --
    field_diags = [
        _build_field_diagnostic(field, profile) for field in fields
    ]

    # -- Step 9: SQL --
    from backend.schemas.field import TableSpec
    from backend.sql.generator import generate_create_table_sql
    table = TableSpec(
        table_name=Path(sample_file).stem,
        fields=fields,
    )
    create_sql = generate_create_table_sql(table)

    # -- Build resolution stats --
    resolution_stats = ResolutionStats(
        total_columns=len(profile.columns),
        rule_store_hits=resolution.rules_resolved_count,
        rag_hits=resolution.rag_resolved_count,
        llm_resolved=resolution.llm_resolved_count,
        fallback_resolved=resolution.fallback_resolved_count,
        value_pools_generated=resolution.value_pools_generated,
        llm_used=resolution.llm_used,
        model_used=resolution.model_used,
    )

    # -- Collect all constraints --
    all_constraints = [
        ConstraintInfo(expression=c.expression, fields=c.fields, confidence=c.confidence)
        for c in constraints_raw
    ]

    return AnalyzeResponse(
        sample_file=sample_file,
        row_count=profile.row_count,
        columns=profile.columns,
        fields=field_diags,
        coherence_links=coherence_links,
        constraints=all_constraints,
        rag_matches=rag_matches,
        resolution=resolution_stats,
        create_table_sql=create_sql,
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _determine_strategy_layer(field: FieldSpec) -> tuple[str, str]:
    """Return (layer_name, description) for the strategy this field would use."""
    # 0. All-empty
    if field.value_frequency and not [v for v in field.value_pool if v != ""]:
        if all(k == "" for k in field.value_frequency):
            return ("empty", "全空列 → 复制空值")

    # 1. Identity / auto-increment
    if field.auto_increment or field.semantic == FieldSemantic.id:
        return ("identity", "自增ID / 主键")

    # 1b. Chinese identifiers
    cn_semantics = {
        FieldSemantic.id_card: "身份证号 (GB 11643 校验)",
        FieldSemantic.credit_code: "统一社会信用代码 (GB 32100 校验)",
        FieldSemantic.bank_card: "银行卡号 (Luhn 校验)",
        FieldSemantic.postal_code: "邮政编码",
        FieldSemantic.gender: "性别 (Coherence 驱动)",
    }
    if field.semantic in cn_semantics:
        return ("cn_identifier", cn_semantics[field.semantic])

    # 2. Datetime
    if field.semantic in (FieldSemantic.time, FieldSemantic.birthdate) or field.type == SqlType.datetime:
        return ("datetime", "日期时间 → 样本范围内随机")

    # 3. Boolean
    if field.type == SqlType.boolean or field.semantic in (FieldSemantic.boolean, FieldSemantic.flag):
        return ("boolean", "布尔/标志 → 随机 0/1")

    # 4. Numeric / coordinate
    if field.semantic == FieldSemantic.coordinate:
        return ("numeric", "坐标 → 经纬度范围内随机")
    if field.type in (SqlType.int, SqlType.decimal):
        suffix = ""
        if field.distribution:
            suffix = f" | 分布: {field.distribution.type}"
        return ("numeric", f"数值 → 观测范围随机{suffix}")

    # 5. Faker priority semantics
    faker_map = {
        FieldSemantic.license_plate: "车牌号 (Faker)",
        FieldSemantic.phone_number: "电话号码 (Faker)",
        FieldSemantic.email: "邮箱 (Faker)",
        FieldSemantic.url: "URL (Faker)",
        FieldSemantic.vehicle_model: "车辆型号 (内置列表)",
        FieldSemantic.direction: "方向角度 (0-360)",
    }
    if field.semantic in faker_map:
        return ("faker", faker_map[field.semantic])

    # 6. Entity fabrication
    from backend.mock.entity_faker import build_entity_generator
    if build_entity_generator(field) is not None:
        return ("entity", "实体伪造 → Faker 生成，绝不复用真实值")

    pool = [v for v in field.value_pool if v != ""]

    # 7. Structured identifiers
    from backend.mock.template_engine import looks_structured
    if pool and looks_structured(pool):
        return ("template", "结构化模板 → 格式骨架 + 随机数字替换")

    # 8. Enum values
    if field.enum_values:
        return ("enum", f"枚举采样 ({len(field.enum_values)} 个值) → 频率加权，唯一可复用真实值")

    # 9. Markov text
    from backend.mock.markov_generator import build_markov_generator
    if pool and build_markov_generator(pool):
        return ("markov", "马尔可夫文本 → N-gram 伪造，绝不精确复制")

    # 10. Column-name heuristics
    name_lower = field.name.lower()
    if field.semantic == FieldSemantic.company_name:
        return ("heuristic", "列名启发式 → 公司名 (Faker)")
    if any(k in name_lower for k in ("phone", "mobile")) or "手机" in field.name:
        return ("heuristic", "列名启发式 → 电话号码 (Faker)")
    if any(k in name_lower for k in ("email", "mail")) or "邮箱" in field.name:
        return ("heuristic", "列名启发式 → 邮箱 (Faker)")
    if "姓名" in field.name or "name" in name_lower:
        return ("heuristic", "列名启发式 → 人名 (Faker)")
    if "地址" in field.name or "address" in name_lower:
        return ("heuristic", "列名启发式 → 地址 (Faker)")

    # 11. Last resort
    return ("fallback", "兜底 → 合成短句 (Faker)")


def _build_field_diagnostic(field: FieldSpec, profile: SampleProfile) -> FieldDiagnostic:
    layer, desc = _determine_strategy_layer(field)
    col_profile = profile.column_profiles.get(field.name)
    return FieldDiagnostic(
        name=field.name,
        sql_type=field.type.value,
        semantic=field.semantic.value if field.semantic else "unknown",
        confidence=round(field.confidence or 0, 3),
        strategy_layer=layer,
        strategy_desc=desc,
        nullable=field.nullable,
        enum_values=field.enum_values[:15] if field.enum_values else [],
        value_pool_size=len(field.value_pool),
        has_value_pool=bool(field.value_pool),
        distribution=field.distribution.model_dump() if field.distribution else None,
        min_value=field.min_value,
        max_value=field.max_value,
        unique_ratio=round(field.unique_ratio, 3) if field.unique_ratio else None,
        null_ratio=round(col_profile.null_ratio, 3) if col_profile else None,
    )


def _build_coherence_links(roles) -> list[CoherenceLink]:
    links: list[CoherenceLink] = []
    if hasattr(roles, 'id_card') and roles.id_card:
        fields = [f.name for f in roles.id_card]
        if roles.birthdate:
            fields.extend(f.name for f in roles.birthdate)
        if roles.gender:
            fields.extend(f.name for f in roles.gender)
        if roles.age:
            fields.extend(f.name for f in roles.age)
        if len(fields) > 1:
            links.append(CoherenceLink(
                description="身份证号 → 出生日期 / 性别 / 年龄",
                fields=fields,
                category="identity",
            ))
    if hasattr(roles, 'region') and len(roles.region) >= 2:
        links.append(CoherenceLink(
            description="省/市/区县 层级一致",
            fields=[f.name for f in roles.region],
            category="region",
        ))
    if hasattr(roles, 'postal') and roles.postal:
        region_fields = [f.name for f in roles.region] if hasattr(roles, 'region') else []
        links.append(CoherenceLink(
            description="邮政编码跟随区域",
            fields=[f.name for f in roles.postal] + region_fields,
            category="postal",
        ))
    if hasattr(roles, 'credit_code') and roles.credit_code:
        region_fields = [f.name for f in roles.region] if hasattr(roles, 'region') else []
        links.append(CoherenceLink(
            description="统一社会信用代码共享区域",
            fields=[f.name for f in roles.credit_code] + region_fields,
            category="credit",
        ))
    if hasattr(roles, 'bank_card') and roles.bank_card:
        links.append(CoherenceLink(
            description="银行卡号 (Luhn 独立校验)",
            fields=[f.name for f in roles.bank_card],
            category="bank",
        ))
    return links


def _build_rag_matches(profile: SampleProfile, fields: list[FieldSpec]) -> list[RagMatch]:
    """Query RAG for similar rules per column."""
    matches: list[RagMatch] = []
    try:
        from backend.rag.rule_indexer import get_rule_indexer
        indexer = get_rule_indexer()
        for field in fields:
            results = indexer.search_similar_rules(field.name, top_k=3)
            for r in results:
                meta = r.get("metadata", {})
                dist = r.get("distance", 1.0)
                if dist > 0.6:  # only show decent matches
                    continue
                matches.append(RagMatch(
                    column=field.name,
                    matched_rule=meta.get("name", r.get("id", "?")),
                    matched_semantic=str(meta.get("semantic", "unknown")),
                    distance=round(dist, 4),
                    confidence=round(1.0 - dist, 3),
                ))
    except Exception:
        pass
    return matches
