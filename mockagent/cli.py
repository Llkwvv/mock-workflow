from typing import Annotated

import typer
from pydantic import ValidationError

from mockagent.config import Settings, get_settings
from mockagent.schemas.request import GenerateRequest
from mockagent.services.generation import generate_to_output, build_generation_preview, generate_mock_rows

app = typer.Typer(help="MockAgent CLI for sample-driven mock data generation.")


@app.command()
def web(
    host: Annotated[str, typer.Option("--host", help="Host to bind to.")] = "0.0.0.0",
    port: Annotated[int, typer.Option("--port", help="Port to listen on.")] = 8000,
) -> None:
    """Start the MockAgent web interface."""
    try:
        import uvicorn
    except ImportError:
        typer.secho(
            "Error: web interface requires FastAPI and uvicorn.\n"
            "Install with: pip install 'mockagent[web]' or 'pip install fastapi uvicorn python-multipart jinja2 aiofiles'",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    typer.secho(f"Starting MockAgent web server on http://{host}:{port}", fg=typer.colors.GREEN, bold=True)
    typer.secho("Press Ctrl+C to stop", fg=typer.colors.YELLOW)
    uvicorn.run(
        "mockagent.api.app:create_app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )



@app.callback()
def main() -> None:
    pass


@app.command()
def generate(
    sample_file: Annotated[str, typer.Option("--sample-file", help="Path to the sample data file.")],
    rows: Annotated[int, typer.Option("--rows", help="Number of mock rows to generate.")] = 100,
    table_name: Annotated[str, typer.Option("--table-name", help="Target MySQL table name.")] = "auto_table",
    output: Annotated[str, typer.Option("--output", help="Output mode: preview or csv.")] = "preview",
    csv_path: Annotated[str | None, typer.Option("--csv-path", help="CSV output path.")] = None,
    schema_output_path: Annotated[str | None, typer.Option("--schema-output-path", help="Path to output the CREATE TABLE SQL schema. If not specified, schema will be printed to console.")] = None,
    rules_file: Annotated[str | None, typer.Option("--rules-file", help="Path to the rule store JSON file.")] = None,
    models_pool_file: Annotated[str | None, typer.Option("--models-pool-file", help="Path to the models pool JSON file.")] = None,
    rules_autosave: Annotated[bool | None, typer.Option("--rules-autosave/--no-rules-autosave", help="Automatically persist high-confidence LLM outputs to the rule store.")] = None,
    refresh_rules: Annotated[bool, typer.Option("--refresh-rules/--no-refresh-rules", help="Bypass existing rule store hits and force every column through the LLM (results still honor --rules-autosave).")] = False,
    rules_min_confidence: Annotated[float | None, typer.Option("--rules-min-confidence", help="Minimum LLM confidence required before saving to the rule store.")] = None,
    enable_llm: Annotated[bool, typer.Option("--enable-llm/--no-enable-llm", help="Enable LLM for uncertain field parsing.")] = False,
    llm_model: Annotated[str | None, typer.Option("--llm-model", help="LLM model name.")] = None,
    llm_base_url: Annotated[str | None, typer.Option("--llm-base-url", help="LLM API base URL (e.g., http://localhost:11434/v1 for Ollama).")]= None,
    llm_api_key: Annotated[str | None, typer.Option("--llm-api-key", help="LLM API key.")] = None,
    llm_timeout: Annotated[int | None, typer.Option("--llm-timeout", help="LLM request timeout in seconds.")] = None,
    llm_temperature: Annotated[float | None, typer.Option("--llm-temperature", help="LLM temperature (0-2).")] = None,
    disable_llm: Annotated[bool, typer.Option("--disable-llm/--no-disable-llm", help="Disable LLM for uncertain field parsing to improve performance with large files.")] = False,
    enable_value_pool: Annotated[bool, typer.Option("--enable-value-pool/--no-enable-value-pool", help="Generate per-field value pools via LLM (persisted to the rule store, reused across runs).")] = False,
    value_pool_size: Annotated[int | None, typer.Option("--value-pool-size", help="Target number of values per generated pool.")] = None,
) -> None:
    try:
        base_settings = get_settings()

        request = GenerateRequest(
            sample_file=sample_file,
            rows=rows,
            table_name=table_name,
            output=output,
            csv_path=csv_path,
        )

        # Build settings with CLI overrides
        settings = Settings(
            rules_file=rules_file or base_settings.rules_file,
            llm_models_pool_file=models_pool_file or base_settings.llm_models_pool_file,
            rules_autosave=base_settings.rules_autosave if rules_autosave is None else rules_autosave,
            rules_min_confidence=rules_min_confidence or base_settings.rules_min_confidence,
            llm_enabled=enable_llm and not disable_llm,
            llm_model=llm_model or base_settings.llm_model,
            llm_base_url=llm_base_url or base_settings.llm_base_url,
            llm_api_key=llm_api_key or base_settings.llm_api_key,
            llm_timeout=llm_timeout or base_settings.llm_timeout,
            llm_temperature=llm_temperature or base_settings.llm_temperature,
            llm_value_pool_enabled=enable_value_pool and enable_llm and not disable_llm,
            llm_value_pool_size=value_pool_size or base_settings.llm_value_pool_size,
        )

        # Generate the preview with schema
        preview = build_generation_preview(
            sample_file=request.sample_file,
            table_name=request.table_name,
            rows=5,
            settings=settings,
            refresh_rules=refresh_rules,
        )

        # Handle schema output to file
        if schema_output_path:
            try:
                with open(schema_output_path, 'w', encoding='utf-8') as f:
                    f.write(preview.create_table_sql)
                typer.secho(f"\nCREATE TABLE SQL has been written to {schema_output_path}", fg=typer.colors.BLUE, bold=True)
            except Exception as e:
                typer.secho(f"Error writing schema to file: {e}", fg=typer.colors.RED, err=True)

        # Pass the pre-built preview to avoid re-running schema resolution + LLM
        result = generate_to_output(
            sample_file=request.sample_file,
            rows=request.rows,
            table_name=request.table_name,
            output=request.output,
            csv_path=request.csv_path,
            settings=settings,
            preview=preview,
        )
    except (FileNotFoundError, ValueError, ValidationError) as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.secho("Sample Summary", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"file_path: {result.profile.file_path}")
    typer.echo(f"row_count: {result.profile.row_count}")
    typer.echo(f"columns: {', '.join(result.profile.columns)}")

    typer.secho("\nFields JSON", fg=typer.colors.GREEN, bold=True)
    typer.echo(result.model_dump_json(indent=2, include={"fields"}))

    typer.secho("\nMySQL Create Table SQL", fg=typer.colors.GREEN, bold=True)
    typer.echo(result.create_table_sql)

    typer.secho("\nMock Preview Rows", fg=typer.colors.GREEN, bold=True)
    for row in result.preview_rows:
        typer.echo(row)

    typer.secho("\nField Resolution Info", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"rules_resolved_count: {result.rules_resolved_count}")
    typer.echo(f"llm_used: {'Yes' if result.llm_used else 'No'}")
    typer.echo(f"llm_resolved_count: {result.llm_resolved_count}")
    typer.echo(f"fallback_resolved_count: {result.fallback_resolved_count}")
    typer.echo(f"value_pools_generated: {sum(1 for f in result.fields if f.value_pool)}")
    if result.model_used:
        typer.echo(f"model_used: {result.model_used}")

    typer.secho("\nOutput Result", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"output: {result.output}")
    typer.echo(f"generated_rows: {result.generated_rows}")
    if result.output_path:
        typer.echo(f"output_path: {result.output_path}")


if __name__ == "__main__":
    app()
