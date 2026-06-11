"""Lightweight observability: metrics collection and health diagnostics.

No external dependencies (Prometheus client optional).  Designed for
single-instance operation where an in-memory dict is sufficient.
"""
import time
from collections import deque
from typing import Any


class MetricsCollector:
    """In-memory metrics store with ring-buffered time series.

    Holds the last N samples for each metric to avoid unbounded growth.
    """

    def __init__(self, max_history: int = 1000):
        self._counters: dict[str, int] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, deque[tuple[float, float]]] = {}
        self._max_history = max_history

    # -- counter --

    def inc(self, name: str, value: int = 1) -> None:
        self._counters[name] = self._counters.get(name, 0) + value

    def counter(self, name: str) -> int:
        return self._counters.get(name, 0)

    # -- gauge --

    def gauge(self, name: str, value: float) -> None:
        self._gauges[name] = value

    def gauge_value(self, name: str) -> float | None:
        return self._gauges.get(name)

    # -- histogram / timing --

    def observe(self, name: str, value: float) -> None:
        buf = self._histograms.setdefault(name, deque(maxlen=self._max_history))
        buf.append((time.time(), value))

    def timing(self, name: str) -> Any:
        """Context manager for timing a block of code."""
        return _TimingContext(self, name)

    def summary(self, name: str) -> dict[str, float]:
        buf = self._histograms.get(name, deque())
        if not buf:
            return {"count": 0, "sum": 0.0, "avg": 0.0, "min": 0.0, "max": 0.0}
        values = [v for _, v in buf]
        return {
            "count": len(values),
            "sum": sum(values),
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
        }

    # -- snapshot --

    def snapshot(self) -> dict[str, Any]:
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {k: self.summary(k) for k in self._histograms},
        }


class _TimingContext:
    def __init__(self, collector: MetricsCollector, name: str):
        self._collector = collector
        self._name = name
        self._start: float | None = None

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._start is not None:
            elapsed = time.perf_counter() - self._start
            self._collector.observe(self._name, elapsed)


# Global singleton
_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    return _metrics
