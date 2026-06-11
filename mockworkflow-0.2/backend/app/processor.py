"""Task processing logic for backend."""
import asyncio
import traceback
from pathlib import Path

from backend.app.executor import TaskExecutor
from backend.app.task_manager import TaskManager, TaskStatus

# Global references set by main.py
task_manager: TaskManager | None = None
project_root: Path | None = None
executor: TaskExecutor | None = None


def set_globals(tm: TaskManager, pr: Path, ex: TaskExecutor | None = None):
    global task_manager, project_root, executor
    task_manager = tm
    project_root = pr
    executor = ex


async def process_task(task_id: str):
    if not task_manager or not project_root:
        raise RuntimeError("Processor not initialized")
    from backend.config import get_settings
    from backend.services.generation import build_generation_preview, generate_to_output
    from backend.output.db_writer import TableSchemaMismatchError
    from backend.app.metrics import get_metrics

    metrics = get_metrics()
    metrics.inc("tasks_started")
    metrics.gauge("active_tasks", metrics.gauge_value("active_tasks") or 0 + 1)

    task = await task_manager.get_task(task_id)
    if not task:
        metrics.gauge("active_tasks", max(0, (metrics.gauge_value("active_tasks") or 1) - 1))
        return

    def _check_cancelled() -> None:
        if executor and executor.is_cancelled(task_id):
            raise asyncio.CancelledError()

    try:
        _check_cancelled()
        await task_manager.update_task_status(task_id, TaskStatus.RUNNING, progress=10)
        settings = get_settings()
        sample_path = Path(task.sample_filename)
        if not sample_path.is_absolute():
            sample_path = project_root / "data" / task.sample_filename
            if not sample_path.is_file():
                sample_path = project_root / task.sample_filename
        if not sample_path.is_file():
            raise FileNotFoundError(f"Sample file not found: {task.sample_filename}")

        sample_file = str(sample_path)
        _check_cancelled()
        await task_manager.update_task_status(task_id, TaskStatus.RUNNING, progress=30)

        # Time the generation preview
        with metrics.timing("generation_duration"):
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

        _check_cancelled()
        await task_manager.update_task_status(task_id, TaskStatus.RUNNING, progress=70)
        output_dir = project_root / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        if task.enable_db_export:
            with metrics.timing("db_export_duration"):
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
            metrics.inc("db_exports")
        elif task.rows <= 5:
            result = preview_result
        else:
            csv_filename = f"{task.table_name}_{task_id[:8]}.csv"
            csv_path = str(output_dir / csv_filename)
            with metrics.timing("csv_export_duration"):
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

        # Record generated rows
        generated_rows = result.get("generated_rows", 0) or task.rows
        metrics.inc("rows_generated", generated_rows)

        # Agent Phase 1 #1: rule store evolution
        if preview.llm_used and settings.rules_autosave:
            from backend.agent.tools.rule_evolve import evolve_rules
            from backend.rules.store import RuleStore
            store = RuleStore(settings.rules_file)
            successful = [(f.name, f) for f in preview.fields if f.confidence and f.confidence >= settings.rules_min_confidence]
            if successful:
                evolve_rules(store, successful, min_confidence=settings.rules_min_confidence)

        # -- RAG Phase 2.5: self-learning loop --
        try:
            from backend.rag.self_learn import learn_from_task
            learn_summary = learn_from_task(
                profile=preview.profile,
                fields=preview.fields,
                task_id=task_id,
            )
            print(f"RAG self-learn: {learn_summary}")
        except Exception as exc:
            print(f"Warning: RAG self-learning skipped ({exc})")

        _check_cancelled()
        metrics.inc("tasks_completed")
        await task_manager.update_task_status(
            task_id, TaskStatus.COMPLETED, progress=100,
            result_preview=preview_result, result_full=result,
        )
    except asyncio.CancelledError:
        metrics.inc("tasks_cancelled")
        await task_manager.update_task_status(
            task_id, TaskStatus.CANCELLED, progress=0,
            error_message="Task was cancelled by user",
        )
        raise
    except TableSchemaMismatchError as e:
        traceback.print_exc()
        metrics.inc("tasks_failed")
        await task_manager.update_task_status(
            task_id, TaskStatus.FAILED, progress=0,
            error_message=str(e), schema_mismatch=True, retryable=True,
        )
    except Exception as e:
        traceback.print_exc()
        metrics.inc("tasks_failed")
        await task_manager.update_task_status(
            task_id, TaskStatus.FAILED, progress=0, error_message=str(e),
        )
    finally:
        metrics.gauge("active_tasks", max(0, (metrics.gauge_value("active_tasks") or 1) - 1))


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
        if not settings.mysql_url:
            raise ValueError("MySQL connection not configured")
        from sqlalchemy import create_engine, text
        engine = create_engine(settings.mysql_url)
        with engine.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS `{task.table_name}`"))
        await process_task(task_id)
    except Exception as e:
        traceback.print_exc()
        await task_manager.update_task_status(
            task_id, TaskStatus.FAILED, progress=0, error_message=str(e),
        )
