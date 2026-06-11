"""Agent tool: Smart Scheduler for dynamic sleep interval and concurrency."""

from __future__ import annotations

import os
import time
from typing import Any


def get_system_metrics() -> dict[str, Any]:
    """Collect lightweight system metrics for scheduling decisions."""
    try:
        load_avg = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
    except Exception:
        load_avg = 0.0
    return {
        "load_avg": load_avg,
        "cpu_count": os.cpu_count() or 1,
        "timestamp": time.time(),
    }


def decide_schedule_params(
    pending_tasks: int,
    metrics: dict[str, Any] | None = None,
    default_sleep: int = 30,
) -> dict[str, Any]:
    """Return recommended sleep seconds and max concurrency.

    Rules:
    - If pending_tasks == 0 and load_avg < 1.0 -> sleep 5min (300s)
    - If pending_tasks <= 3 and load_avg < 2.0 -> sleep 60s
    - If pending_tasks > 10 or load_avg > cpu_count * 0.8 -> sleep 10s, concurrency 2
    - Otherwise -> sleep 30s, concurrency 4
    """
    if metrics is None:
        metrics = get_system_metrics()

    load_avg = metrics.get("load_avg", 0.0)
    cpu_count = metrics.get("cpu_count", 1)
    max_sleep = 300
    min_sleep = 10

    if pending_tasks == 0 and load_avg < 1.0:
        sleep = max_sleep
        concurrency = 1
    elif pending_tasks <= 3 and load_avg < 2.0:
        sleep = 60
        concurrency = 2
    elif pending_tasks > 10 or load_avg > cpu_count * 0.8:
        sleep = min_sleep
        concurrency = 2
    else:
        sleep = default_sleep
        concurrency = 4

    return {
        "sleep_seconds": sleep,
        "max_concurrency": concurrency,
        "pending_tasks": pending_tasks,
        "load_avg": load_avg,
    }
