from pydantic import BaseModel

from backend.config import Settings, get_settings
from backend.llm import resolve_fields
from backend.mock.generator import generate_mock_rows, preview_mock_rows
from backend.output.csv_writer import write_csv
from backend.output.db_writer import validate_mysql_url, write_mysql
from backend.output.excel_writer import write_excel
from backend.output.json_writer import write_json
from backend.sample.profiler import analyze_sample_file
from backend.schemas.field import FieldSpec, SampleProfile, TableSpec
from backend.sql.generator import generate_create_table_sql


class GenerationPreview(BaseModel):
    profile: SampleProfile
    fields: list[FieldSpec]
    create_table_sql: str
    preview_rows: list[dict[str, object]]
    llm_used: bool = False
    llm_resolved_count: int = 0
    rules_resolved_count: int = 0
    fallback_resolved_count: int = 0
    model_used: str | None = None


class GenerationResult(GenerationPreview):
    generated_rows: int
    output: str
    output_path: str | None = None


def build_generation_preview(
    sample_file: str,
    table_name: str = "auto_table",
    rows: int = 5,
    settings: Settings | None = None,
    refresh_rules: bool = False,
) -> GenerationPreview:
    if settings is None:
        settings = get_settings()

    profile = analyze_sample_file(sample_file)
    resolution = resolve_fields(profile, settings=settings, refresh_rules=refresh_rules)
    fields = resolution.fields

    # Agent Phase 1 #3: inject cross-field constraints
    from backend.agent.tools.constraint import infer_field_constraints
    constraints = infer_field_constraints(fields)
    for field in fields:
        relevant = [c for c in constraints if field.name in c.fields]
        if relevant:
            field.constraints = relevant

    # Agent Phase 1 #4: attach distribution info from profiler
    for field in fields:
        col_profile = profile.column_profiles.get(field.name)
        if col_profile and col_profile.distribution:
            field.distribution = col_profile.distribution
        if col_profile and col_profile.temporal_trend:
            field.temporal_trend = col_profile.temporal_trend

    table = TableSpec(table_name=table_name, fields=fields)
    create_table_sql = generate_create_table_sql(table)
    preview_rows = preview_mock_rows(fields, rows)
    return GenerationPreview(
        profile=profile,
        fields=fields,
        create_table_sql=create_table_sql,
        preview_rows=preview_rows,
        llm_used=resolution.llm_used,
        llm_resolved_count=resolution.llm_resolved_count,
        rules_resolved_count=resolution.rules_resolved_count,
        fallback_resolved_count=resolution.fallback_resolved_count,
        model_used=resolution.model_used,
    )


def generate_to_output(
    sample_file: str,
    table_name: str = "auto_table",
    rows: int = 100,
    output: str = "preview",
    csv_path: str | None = None,
    settings: Settings | None = None,
    preview: GenerationPreview | None = None,
    refresh_rules: bool = False,
) -> GenerationResult:
    if settings is None:
        settings = get_settings()
    if preview is None:
        preview = build_generation_preview(
            sample_file=sample_file,
            table_name=table_name,
            rows=5,
            settings=settings,
            refresh_rules=refresh_rules,
        )
    normalized_output = output.lower()
    generated_rows = 0
    output_path = None
    pii_map = None
    if settings.pii_enabled:
        from backend.agent.tools.pii import detect_pii_fields
        pii_map = detect_pii_fields(preview.fields)

    if normalized_output == "preview":
        generated_rows = len(preview.preview_rows)
    elif normalized_output == "csv":
        if not csv_path:
            raise ValueError("csv_path is required when output is csv")
        full_rows = generate_mock_rows(preview.fields, rows, pii_map=pii_map)
        output_path = str(write_csv(full_rows, csv_path))
        generated_rows = len(full_rows)
    elif normalized_output == "json":
        if not csv_path:
            raise ValueError("json_path is required when output is json")
        # Convert csv_path to json path if needed
        json_path = csv_path if csv_path.endswith(".json") else csv_path.rsplit(".", 1)[0] + ".json"
        full_rows = generate_mock_rows(preview.fields, rows, pii_map=pii_map)
        output_path = str(write_json(full_rows, json_path))
        generated_rows = len(full_rows)
    elif normalized_output == "excel":
        if not csv_path:
            raise ValueError("excel_path is required when output is excel")
        # Convert csv_path to excel path if needed
        excel_path = csv_path if csv_path.endswith((".xlsx", ".xls")) else csv_path.rsplit(".", 1)[0] + ".xlsx"
        full_rows = generate_mock_rows(preview.fields, rows, pii_map=pii_map)
        output_path = str(write_excel(full_rows, excel_path))
        generated_rows = len(full_rows)
    elif normalized_output == "mysql":
        if not settings.db_export_enabled:
            raise ValueError("Database export is disabled")
        if not settings.mysql_url:
            raise ValueError(
                "Database export is enabled but no connection string is configured. "
                "Set MOCKWORKFLOW_MYSQL_URL to a valid mysql connection string."
            )
        validate_mysql_url(settings.mysql_url)
        full_rows = generate_mock_rows(preview.fields, rows, pii_map=pii_map)
        generated_rows = write_mysql(
            settings.mysql_url,
            preview.create_table_sql,
            table_name,
            full_rows,
        )
        output_path = f"mysql://{table_name}"
    else:
        raise ValueError("output must be one of: preview, csv, mysql")

    return GenerationResult(
        profile=preview.profile,
        fields=preview.fields,
        create_table_sql=preview.create_table_sql,
        preview_rows=preview.preview_rows,
        llm_used=preview.llm_used,
        llm_resolved_count=preview.llm_resolved_count,
        rules_resolved_count=preview.rules_resolved_count,
        fallback_resolved_count=preview.fallback_resolved_count,
        generated_rows=generated_rows,
        output=normalized_output,
        output_path=output_path,
    )
