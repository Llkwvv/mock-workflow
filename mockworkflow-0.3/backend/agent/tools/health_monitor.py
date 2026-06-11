"""Agent tool: system health monitoring with auto-healing."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from backend.config import Settings, get_settings


class HealthMonitor:
    """Async health monitor that checks task status, DB connectivity and LLM availability."""

    def __init__(
        self,
        task_manager: Any,
        schedule_manager: Any | None = None,
        broadcast_fn: Callable | None = None,
        interval_seconds: int = 300,
        failure_threshold: int = 3,
    ):
        self._task_manager = task_manager
        self._schedule_manager = schedule_manager
        self._broadcast_fn = broadcast_fn
        self._interval = interval_seconds
        self._failure_threshold = failure_threshold
        self._running = False
        self._task: asyncio.Task | None = None
        self._failures: dict[str, int] = {}

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run_loop(self):
        while self._running:
            try:
                await self._check_once()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error("Health check error: %s", e)
            await asyncio.sleep(self._interval)

    async def _check_once(self):
        settings = get_settings()
        issues: list[str] = []

        # 1. Check failed tasks
        try:
            tasks = await self._task_manager.list_tasks()
            failed_count = sum(1 for t in tasks if t.status == "failed")
            if failed_count > 5:
                issues.append(f"Too many failed tasks: {failed_count}")
                self._increment_failure("failed_tasks")
            else:
                self._reset_failure("failed_tasks")
        except Exception as e:
            issues.append(f"Task manager unreachable: {e}")

        # 2. Check MySQL connectivity
        if settings.mysql_url:
            try:
                from sqlalchemy import create_engine, text
                engine = create_engine(settings.mysql_url)
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                self._reset_failure("mysql")
            except Exception as e:
                issues.append(f"MySQL connection failed: {e}")
                self._increment_failure("mysql")

        # 3. Check LLM availability
        if settings.llm_enabled:
            try:
                from openai import OpenAI
                client = OpenAI(
                    api_key=settings.llm_api_key or "not-needed",
                    base_url=settings.llm_base_url,
                    timeout=10,
                )
                # Lightweight check: list models or a simple ping
                # Some providers don't support /models, so we just try a tiny completion
                client.chat.completions.create(
                    model=settings.llm_model or "gpt-3.5-turbo",
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=1,
                )
                self._reset_failure("llm")
            except Exception as e:
                issues.append(f"LLM unavailable: {e}")
                self._increment_failure("llm")
                # Auto-heal: disable LLM if consistently failing
                if self._failures.get("llm", 0) >= self._failure_threshold:
                    import logging
                    logging.getLogger(__name__).warning("Auto-healing: disabling LLM due to repeated failures")
                    settings.llm_enabled = False
                    issues.append("Auto-healed: LLM disabled")
                    self._reset_failure("llm")

        if issues and self._broadcast_fn:
            await self._broadcast_fn({
                "type": "system_alert",
                "timestamp": time.time(),
                "issues": issues,
            })

    def _increment_failure(self, key: str):
        self._failures[key] = self._failures.get(key, 0) + 1

    def _reset_failure(self, key: str):
        self._failures.pop(key, None)
