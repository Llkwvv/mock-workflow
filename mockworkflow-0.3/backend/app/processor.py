"""Task processing logic for backend."""
import json
import sqlite3
import traceback
from pathlib import Path

from backend.app.task_manager import TaskManager, TaskStatus

# Global task manager set by main.py
task_manager: TaskManager | None = None
project_root: Path | None = None


def set_globals(tm: TaskManager, pr: Path):
    global task_manager, project_root
    task_manager = tm
    project_root = pr


async def _find_cached_task(task) -> dict | None:
    """Find a previous completed task with identical sample/table/rows and valid output file."""
    if not task_manager or task.rows <= 10000:
        return None
    conn = sqlite3.connect(str(task_manager._db_path))
    cursor = conn.execute(
        """
        SELECT result_preview, result_full FROM tasks
        WHERE status = ? AND sample_filename = ? AND table_name = ? AND rows = ? AND id != ?
        ORDER BY completed_at DESC LIMIT 1
        """,
        (TaskStatus.COMPLETED.value, task.sample_filename, task.table_name, task.rows, task.id),
    )
    row = cursor.fetchone()
    conn.close()
    if row and row[1]:
        result_full = json.loads(row[1])
        output_path = result_full.get("output_path")
        if output_path and Path(output_path).exists():
            return {
                "result_preview": json.loads(row[0]) if row[0] else None,
                "result_full": result_full,
            }
    return None


async def process_task(task_id: str):
    if not task_manager or not project_root:
        raise RuntimeError("Processor not initialized")
    from backend.config import get_settings
    from backend.services.generation import build_generation_preview, generate_to_output
    from backend.output.db_writer import TableSchemaMismatchError

    task = await task_manager.get_task(task_id)
    if not task:
        return
    try:
        await task_manager.update_task_status(task_id, TaskStatus.RUNNING, progress=10)
        settings = get_settings()
        sample_path = Path(task.sample_filename)
        if not sample_path.is_absolute():
            sample_path = project_root / "samples" / task.sample_filename
            if not sample_path.is_file():
                sample_path = project_root / task.sample_filename
        if not sample_path.is_file():
            raise FileNotFoundError(f"Sample file not found: {task.sample_filename}")

        sample_file = str(sample_path)
        await task_manager.update_task_status(task_id, TaskStatus.RUNNING, progress=30)
        preview = build_generation_preview(
            sample_file=sample_file,
            table_name=task.table_name,
            rows=min(task.rows, 5),
            settings=settings,
        )
        preview_result = {
            "row_count": preview.profile.row_count,
            "columns": preview.profile.columns,
            "fields": [f.model_dump() for f in preview.fields],
            "create_table_sql": preview.create_table_sql,
            "preview_rows": preview.preview_rows,
            "llm_used": preview.llm_used,
            "llm_resolved_count": preview.llm_resolved_count,
            "rules_resolved_count": preview.rules_resolved_count,
        }

        await task_manager.update_task_status(task_id, TaskStatus.RUNNING, progress=70)
        output_dir = project_root / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Phase 2 #2: avoid duplicate generation for large tasks
        cached = await _find_cached_task(task)
        if cached:
            import logging
            logging.getLogger(__name__).info("Reusing cached output for %s rows=%s", task.table_name, task.rows)
            result = {
                **preview_result,
                "generated_rows": cached["result_full"].get("generated_rows"),
                "output": cached["result_full"].get("output"),
                "output_path": cached["result_full"].get("output_path"),
            }
        elif task.enable_db_export:
            full_result = generate_to_output(
                sample_file=sample_file,
                table_name=task.table_name,
                rows=task.rows,
                output="mysql",
                settings=settings,
                preview=preview,
            )
            result = {
                **preview_result,
                "generated_rows": full_result.generated_rows,
                "output": full_result.output,
                "output_path": full_result.output_path,
            }
        elif task.rows <= 5:
            result = preview_result
        else:
            csv_filename = f"{task.table_name}_{task_id[:8]}.csv"
            csv_path = str(output_dir / csv_filename)
            full_result = generate_to_output(
                sample_file=sample_file,
                table_name=task.table_name,
                rows=task.rows,
                output="csv",
                csv_path=csv_path,
                settings=settings,
                preview=preview,
            )
            result = {
                **preview_result,
                "generated_rows": full_result.generated_rows,
                "output": full_result.output,
                "output_path": full_result.output_path,
            }

        # Agent Phase 1 #1: rule store evolution
        if preview.llm_used and settings.rules_autosave:
            from backend.agent.tools.rule_evolve import evolve_rules
            from backend.rules.store import RuleStore
            store = RuleStore(settings.rules_file)
            successful = [(f.name, f) for f in preview.fields if f.confidence and f.confidence >= settings.rules_min_confidence]
            if successful:
                evolve_rules(store, successful, min_confidence=settings.rules_min_confidence)

        # Agent Phase 2 #7: validation
        if result.get("generated_rows"):
            from backend.agent.tools.validator import validate_generated_data
            rows_to_validate = preview.preview_rows
            if task.enable_db_export or task.rows > 5:
                # Re-generate rows for validation (preview already used full_result)
                from backend.mock.generator import generate_mock_rows
                from backend.agent.tools.pii import detect_pii_fields
                pii_map = detect_pii_fields(preview.fields) if settings.pii_enabled else None
                rows_to_validate = generate_mock_rows(preview.fields, task.rows, pii_map=pii_map)
            validation = validate_generated_data(
                rows=rows_to_validate,
                fields=preview.fields,
                profile=preview.profile,
            )
            result["validation"] = validation

        # Agent Phase 2 #8: distribution comparison
        if result.get("generated_rows"):
            from backend.agent.tools.distribution_compare import compare_distributions
            distribution_check = compare_distributions(
                generated_rows=rows_to_validate,
                fields=preview.fields,
                profile=preview.profile,
            )
            result["distribution_check"] = distribution_check

        await task_manager.update_task_status(
            task_id, TaskStatus.COMPLETED, progress=100,
            result_preview=preview_result, result_full=result,
        )
    except TableSchemaMismatchError as e:
        traceback.print_exc()
        await task_manager.update_task_status(
            task_id, TaskStatus.FAILED, progress=0,
            error_message=str(e), schema_mismatch=True, retryable=True,
        )
    except Exception as e:
        traceback.print_exc()
        await task_manager.update_task_status(
            task_id, TaskStatus.FAILED, progress=0, error_message=str(e),
        )


async def retry_task(task_id: str):
    if not task_manager:
        raise RuntimeError("Processor not initialized")
    from backend.config import get_settings
    task = await task_manager.get_task(task_id)
    if not task:
        return
    try:
        await task_manager.update_task_status(task_id, TaskStatus.RUNNING, progress=10)
        settings = get_settings()

        # Phase 2 #9: diagnose previous failure
        from backend.agent.tools.diagnosis import diagnose
        previous_error = Exception(task.error_message or "Unknown error")
        diagnosis = diagnose(previous_error)

        if diagnosis["category"] == "schema_mismatch":
            if not settings.mysql_url:
                raise ValueError("MySQL connection not configured for schema mismatch retry")
            from sqlalchemy import create_engine, text
            engine = create_engine(settings.mysql_url)
            with engine.begin() as connection:
                connection.execute(text(f"DROP TABLE IF EXISTS `{task.table_name}`"))

        # LLM degradation: if LLM failed, retry with LLM disabled
        llm_degraded = diagnosis["category"] in ("llm_timeout", "llm_unavailable", "llm_error")
        if llm_degraded:
            import logging
            logging.getLogger(__name__).warning("Diagnosed LLM issue (%s), disabling LLM for retry", diagnosis['category'])
            settings.llm_enabled = False

        await process_task(task_id)
    except Exception as e:
        traceback.print_exc()
        await task_manager.update_task_status(
            task_id, TaskStatus.FAILED, progress=0, error_message=str(e),
        )
