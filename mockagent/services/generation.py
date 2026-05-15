from pydantic import BaseModel

from mockagent.config import Settings, get_settings
from mockagent.llm import resolve_fields
from mockagent.mock.generator import generate_mock_rows, preview_mock_rows
from mockagent.output.csv_writer import write_csv
from mockagent.sample.profiler import analyze_sample_file
from mockagent.schemas.field import FieldSpec, SampleProfile, TableSpec
from mockagent.sql.generator import generate_create_table_sql


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

    if normalized_output == "preview":
        generated_rows = len(preview.preview_rows)
    elif normalized_output == "csv":
        if not csv_path:
            raise ValueError("csv_path is required when output is csv")
        full_rows = generate_mock_rows(preview.fields, rows)
        output_path = str(write_csv(full_rows, csv_path))
        generated_rows = len(full_rows)
    # MySQL output has been removed - only preview and csv are supported
    else:
        raise ValueError("output must be one of: preview, csv")

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
