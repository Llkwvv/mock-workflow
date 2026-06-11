"""Tests for dynamic scheduler sleep interval logic."""

import pytest

from backend.agent.tools.scheduler import decide_schedule_params, get_system_metrics


def test_decide_schedule_params_idle():
    params = decide_schedule_params(pending_tasks=0, metrics={"load_avg": 0.0, "cpu_count": 4})
    assert params["sleep_seconds"] == 300
    assert params["max_concurrency"] == 1


def test_decide_schedule_params_light():
    params = decide_schedule_params(pending_tasks=2, metrics={"load_avg": 0.5, "cpu_count": 4})
    assert params["sleep_seconds"] == 60
    assert params["max_concurrency"] == 2


def test_decide_schedule_params_heavy():
    params = decide_schedule_params(pending_tasks=15, metrics={"load_avg": 5.0, "cpu_count": 4})
    assert params["sleep_seconds"] == 10
    assert params["max_concurrency"] == 2


def test_decide_schedule_params_default():
    params = decide_schedule_params(pending_tasks=5, metrics={"load_avg": 1.5, "cpu_count": 4})
    assert params["sleep_seconds"] == 30
    assert params["max_concurrency"] == 4


def test_get_system_metrics():
    metrics = get_system_metrics()
    assert "load_avg" in metrics
    assert "cpu_count" in metrics
    assert "timestamp" in metrics
    assert metrics["cpu_count"] >= 1
