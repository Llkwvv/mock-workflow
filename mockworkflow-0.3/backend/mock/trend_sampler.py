"""Temporal trend sampler for time-series mock data generation."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from backend.schemas.field import TemporalTrendInfo


def infer_temporal_trend(series: pd.Series) -> TemporalTrendInfo | None:
    """Detect trend and seasonality in a datetime series.

    Uses linear regression for trend slope and FFT for periodicity.
    Returns None if fewer than 10 valid timestamps.
    """
    dt_values = pd.to_datetime(series.dropna(), errors="coerce").dropna()
    if len(dt_values) < 10:
        return None

    # Sort and convert to seconds since first value
    sorted_vals = dt_values.sort_values()
    base = sorted_vals.iloc[0]
    deltas = (sorted_vals - base).dt.total_seconds().values.astype(float)
    if len(deltas) < 2:
        return None

    # Linear regression slope (seconds per index step)
    x = np.arange(len(deltas))
    if len(set(deltas)) == 1:
        slope = 0.0
    else:
        slope = float(np.polyfit(x, deltas, 1)[0])

    direction = "up" if slope > 0 else "down" if slope < 0 else "flat"

    # Detrend for FFT seasonality check
    detrended = deltas - (slope * x)
    has_seasonality = False
    period_seconds = None
    if len(detrended) >= 16:
        fft = np.fft.rfft(detrended)
        power = np.abs(fft) ** 2
        # Skip DC component
        if len(power) > 1:
            peak_idx = int(np.argmax(power[1:])) + 1
            if power[peak_idx] > np.mean(power[1:]) * 3:
                has_seasonality = True
                freq = np.fft.rfftfreq(len(detrended))
                if freq[peak_idx] > 0:
                    period_seconds = float(1.0 / freq[peak_idx])

    return TemporalTrendInfo(
        slope=slope,
        has_seasonality=has_seasonality,
        period_seconds=period_seconds,
        direction=direction,
    )


def sample_trend_datetime(
    rows: int,
    trend: TemporalTrendInfo,
    base_time: datetime | None = None,
) -> list[str]:
    """Generate a list of datetime strings following a trend."""
    if base_time is None:
        base_time = datetime.now() - timedelta(days=365)

    indices = np.arange(rows)
    # Base progression using slope (seconds per step)
    seconds = indices * trend.slope
    if trend.has_seasonality and trend.period_seconds:
        seconds += np.sin(2 * np.pi * indices / max(1, trend.period_seconds)) * max(1, abs(trend.slope) * 10)

    # Add small noise
    noise = np.random.normal(0, max(1, abs(trend.slope) * 0.1), rows)
    seconds = seconds + noise

    # Ensure non-negative progression from base_time
    seconds = np.maximum.accumulate(seconds)

    times = [base_time + timedelta(seconds=float(s)) for s in seconds]
    return [t.strftime("%Y-%m-%d %H:%M:%S") for t in times]
