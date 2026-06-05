"""Task processing logic for backend."""
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

        if task.enable_db_export:
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
