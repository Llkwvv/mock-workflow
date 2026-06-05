from typing import Annotated

import typer
from pydantic import ValidationError
from pathlib import Path

from mockworkflow.config import Settings, get_settings
from mockworkflow.schemas.request import GenerateRequest
from mockworkflow.services.generation import generate_to_output, build_generation_preview, generate_mock_rows
from mockworkflow.utils.pinyin import filename_to_table_name

app = typer.Typer(help="Mockworkflow CLI for sample-driven mock data generation.")
schedule_app = typer.Typer(help="Schedule management commands.")
app.add_typer(schedule_app, name="schedule")


@app.command()
def web(
    host: Annotated[str, typer.Option("--host", help="Host to bind to.")] = "0.0.0.0",
    port: Annotated[int, typer.Option("--port", help="Port to listen on.")] = 8000,
) -> None:
    """Start the Mockworkflow web interface."""
    try:
        import uvicorn
    except ImportError:
        typer.secho(
            "Error: web interface requires FastAPI and uvicorn.\n"
            "Install with: pip install 'mockworkflow[web]' or 'pip install fastapi uvicorn python-multipart jinja2 aiofiles'",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    typer.secho(f"Starting Mockworkflow web server on http://{host}:{port}", fg=typer.colors.GREEN, bold=True)
    typer.secho("Press Ctrl+C to stop", fg=typer.colors.YELLOW)
    uvicorn.run(
        "mockworkflow.api.app:create_app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


@app.command()
def batch(
    files: Annotated[
        list[str],
        typer.Argument(help="List of sample files to process"),
    ],
    rows: Annotated[int, typer.Option("--rows", help="Number of mock rows to generate per file.")] = 100,
    output: Annotated[str, typer.Option("--output", help="Output mode: preview, csv, json, excel, or mysql.")] = "preview",
    csv_path: Annotated[str | None, typer.Option("--csv-path", help="CSV/JSON/Excel output directory.")] = None,
    table_prefix: Annotated[str | None, typer.Option("--table-prefix", help="Prefix for all table names.")] = None,
    enable_db_export: Annotated[bool, typer.Option("--enable-db-export", help="Export to database.")] = False,
    enable_llm: Annotated[bool, typer.Option("--enable-llm/--no-enable-llm", help="Enable LLM for field inference.")] = False,
) -> None:
    """Batch process multiple sample files and generate mock data for each."""
    import asyncio
    from pathlib import Path
    from typing import List

    from mockworkflow.config import get_settings
    from mockworkflow.schemas.request import GenerateRequest
    from mockworkflow.services.generation import build_generation_preview, generate_to_output
    from mockworkflow.utils.pinyin import filename_to_table_name

    try:
        base_settings = get_settings()

        # Validate files exist
        valid_files: List[str] = []
        for f in files:
            path = Path(f)
            if not path.is_file():
                # Try in samples directory
                samples_path = Path.cwd() / "samples" / f
                if samples_path.is_file():
                    valid_files.append(str(samples_path))
                else:
                    typer.secho(f"Warning: File not found: {f}, skipping...", fg=typer.colors.YELLOW, err=True)
            else:
                valid_files.append(str(path))

        if not valid_files:
            typer.secho("Error: No valid files to process", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        typer.secho(f"Processing {len(valid_files)} file(s)...", fg=typer.colors.GREEN, bold=True)

        # Process each file
        for i, sample_file in enumerate(valid_files, 1):
            typer.secho(f"\n[{i}/{len(valid_files)}] Processing: {Path(sample_file).name}", fg=typer.colors.CYAN, bold=True)

            # Auto-generate table name from filename
            file_stem = Path(sample_file).stem
            base_name = filename_to_table_name(file_stem) or "auto_table"
            table_name = table_prefix + base_name if table_prefix else base_name

            request = GenerateRequest(
                sample_file=sample_file,
                rows=rows,
                table_name=table_name,
                output=output,
                csv_path=csv_path,
            )

            # Build settings with CLI overrides
            settings = Settings(
                rules_file=base_settings.rules_file,
                llm_models_pool_file=base_settings.llm_models_pool_file,
                rules_autosave=base_settings.rules_autosave,
                rules_min_confidence=base_settings.rules_min_confidence,
                llm_enabled=enable_llm,
                llm_model=base_settings.llm_model,
                llm_base_url=base_settings.llm_base_url,
                llm_api_key=base_settings.llm_api_key,
                llm_timeout=base_settings.llm_timeout,
                llm_temperature=base_settings.llm_temperature,
                llm_value_pool_enabled=False,  # Disable for batch to speed up
                db_export_enabled=base_settings.db_export_enabled if enable_db_export else False,
                mysql_url=base_settings.mysql_url,
            )

            # Generate the preview
            preview = build_generation_preview(
                sample_file=request.sample_file,
                table_name=request.table_name,
                rows=5,
                settings=settings,
                refresh_rules=False,
            )

            # Handle schema output to file if csv_path is specified
            if output == "csv" and csv_path:
                csv_file = Path(csv_path) / f"{table_name}_mock.csv"
                csv_file.parent.mkdir(parents=True, exist_ok=True)
                request.csv_path = str(csv_file)

            # Generate mock data
            result = generate_to_output(
                sample_file=request.sample_file,
                rows=request.rows,
                table_name=request.table_name,
                output=request.output,
                csv_path=request.csv_path,
                settings=settings,
                preview=preview,
            )

            typer.secho(f"  Table: {request.table_name}", fg=typer.colors.GREEN)
            typer.secho(f"  Rows: {result.generated_rows}", fg=typer.colors.GREEN)
            if result.output_path:
                typer.secho(f"  Output: {result.output_path}", fg=typer.colors.GREEN)
            typer.secho(f"  LLM used: {'Yes' if result.llm_used else 'No'}", fg=typer.colors.BLUE)

        typer.secho("\nBatch processing complete!", fg=typer.colors.GREEN, bold=True)

    except (FileNotFoundError, ValueError, ValidationError) as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc



@app.callback()
def main() -> None:
    pass


@app.command()
def generate(
    sample_file: Annotated[str, typer.Option("--sample-file", help="Path to the sample data file.")],
    rows: Annotated[int, typer.Option("--rows", help="Number of mock rows to generate.")] = 100,
    table_name: Annotated[str | None, typer.Option("--table-name", help="Target MySQL table name. If not specified, auto-generated from filename pinyin initials.")] = None,
    output: Annotated[str, typer.Option("--output", help="Output mode: preview, csv, json, excel, or mysql (mysql requires MOCKWORKFLOW_DB_EXPORT_ENABLED=true).")] = "preview",
    csv_path: Annotated[str | None, typer.Option("--csv-path", help="CSV/JSON/Excel output path.")] = None,
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

        # Auto-generate table name from filename if not specified
        if table_name is None:
            file_stem = Path(sample_file).stem
            table_name = filename_to_table_name(file_stem) or "auto_table"

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
            db_export_enabled=base_settings.db_export_enabled,
            mysql_url=base_settings.mysql_url,
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
                raise typer.Exit(code=1) from e

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


@schedule_app.command("list")
def list_schedules():
    """List all scheduled tasks."""
    try:
        from mockworkflow.web.scheduler import ScheduleManager
        import asyncio

        schedule_manager = ScheduleManager()
        schedules = asyncio.run(schedule_manager.list_schedules())

        if not schedules:
            typer.secho("No scheduled tasks found.", fg=typer.colors.YELLOW)
            return

        typer.secho(f"\nFound {len(schedules)} scheduled tasks:\n", fg=typer.colors.GREEN, bold=True)

        for schedule in schedules:
            status = "✅ Enabled" if schedule.enabled else "⏸️ Disabled"
            last_run = schedule.last_run.strftime("%Y-%m-%d %H:%M:%S") if schedule.last_run else "Never"
            next_run = schedule.next_run.strftime("%Y-%m-%d %H:%M:%S") if schedule.next_run else "N/A"

            typer.secho(f"ID: {schedule.id}", fg=typer.colors.CYAN)
            typer.echo(f"  File: {schedule.sample_filename}")
            typer.echo(f"  Table: {schedule.table_name}")
            typer.echo(f"  Rows: {schedule.rows}")
            typer.echo(f"  Cron: {schedule.cron}")
            typer.echo(f"  DB Export: {'Yes' if schedule.enable_db_export else 'No'}")
            typer.echo(f"  Status: {status}")
            typer.echo(f"  Last run: {last_run}")
            typer.echo(f"  Next run: {next_run}")
            typer.echo(f"  Created: {schedule.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            typer.echo()

    except Exception as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@schedule_app.command("add")
def add_schedule(
    sample_file: Annotated[str, typer.Option("--sample-file", help="Path to the sample data file.")],
    cron: Annotated[str, typer.Option("--cron", help="5-field cron expression (e.g., '0 9 * * *' for daily at 9am).")],
    rows: Annotated[int, typer.Option("--rows", help="Number of mock rows to generate.")] = 100,
    table_name: Annotated[str | None, typer.Option("--table-name", help="Target table name. Auto-generated if not specified.")] = None,
    enable_db_export: Annotated[bool, typer.Option("--enable-db-export", help="Export generated rows to database.")] = False,
):
    """Add a new scheduled task."""
    try:
        from mockworkflow.web.scheduler import ScheduleManager
        from pathlib import Path
        import asyncio

        # Validate sample file exists
        sample_path = Path(sample_file)
        if not sample_path.is_file():
            # Check in samples directory
            samples_path = Path.cwd() / "samples" / sample_file
            if samples_path.is_file():
                sample_path = samples_path
            else:
                raise FileNotFoundError(f"Sample file not found: {sample_file}")

        # Auto-generate table name if not specified
        if table_name is None:
            file_stem = sample_path.stem
            table_name = filename_to_table_name(file_stem) or "auto_table"

        schedule_manager = ScheduleManager()
        schedule = asyncio.run(
            schedule_manager.create_schedule(
                sample_filename=str(sample_path),
                table_name=table_name,
                rows=rows,
                cron=cron,
                enable_db_export=enable_db_export,
            )
        )

        next_run = schedule.next_run.strftime("%Y-%m-%d %H:%M:%S") if schedule.next_run else "N/A"

        typer.secho("\nSchedule created successfully!", fg=typer.colors.GREEN, bold=True)
        typer.echo(f"ID: {schedule.id}")
        typer.echo(f"Sample: {schedule.sample_filename}")
        typer.echo(f"Table: {schedule.table_name}")
        typer.echo(f"Rows: {schedule.rows}")
        typer.echo(f"Cron: {schedule.cron}")
        typer.echo(f"DB Export: {'Yes' if schedule.enable_db_export else 'No'}")
        typer.echo(f"Status: {'Enabled' if schedule.enabled else 'Disabled'}")
        typer.echo(f"Next run: {next_run}")

    except Exception as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@schedule_app.command("remove")
def remove_schedule(
    schedule_id: Annotated[str, typer.Argument(help="Schedule ID to remove.")],
):
    """Remove a scheduled task."""
    try:
        from mockworkflow.web.scheduler import ScheduleManager
        import asyncio

        schedule_manager = ScheduleManager()
        schedule = asyncio.run(schedule_manager.delete_schedule(schedule_id))

        if not schedule:
            typer.secho(f"Schedule not found: {schedule_id}", fg=typer.colors.YELLOW)
            return

        typer.secho(f"Schedule removed: {schedule_id}", fg=typer.colors.GREEN, bold=True)

    except Exception as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@schedule_app.command("toggle")
def toggle_schedule(
    schedule_id: Annotated[str, typer.Argument(help="Schedule ID to toggle.")],
):
    """Enable or disable a scheduled task."""
    try:
        from mockworkflow.web.scheduler import ScheduleManager
        import asyncio

        schedule_manager = ScheduleManager()
        schedule = asyncio.run(schedule_manager.toggle_schedule(schedule_id))

        if not schedule:
            typer.secho(f"Schedule not found: {schedule_id}", fg=typer.colors.YELLOW)
            return

        status = "enabled" if schedule.enabled else "disabled"
        typer.secho(f"Schedule {schedule_id} is now {status}", fg=typer.colors.GREEN, bold=True)

    except Exception as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
