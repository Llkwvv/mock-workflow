"""Agent tool: compare original sample vs generated data distributions."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.spatial.distance import jensenshannon

from backend.schemas.field import FieldSpec, SampleProfile, SqlType


def compare_distributions(
    generated_rows: list[dict[str, Any]],
    fields: list[FieldSpec],
    profile: SampleProfile,
) -> dict[str, Any]:
    """Compare sample and generated distributions, returning a fit_score per field.

    Numeric: histogram overlap + KL divergence proxy.
    Categorical: chi-square-like distance.
    Datetime: inter-arrival KS-like score.
    """
    if not generated_rows:
        return {"overall_fit_score": 0.0, "fields": []}

    df_gen = pd.DataFrame(generated_rows)
    field_scores: list[dict[str, Any]] = []

    for field in fields:
        col_name = field.name
        if col_name not in df_gen.columns:
            continue
        col_profile = profile.column_profiles.get(col_name)
        if not col_profile:
            continue

        sample_vals = col_profile.samples
        gen_vals = df_gen[col_name].dropna().astype(str).tolist()
        if not sample_vals or not gen_vals:
            continue

        score = 0.0
        method = "unknown"

        if field.type in (SqlType.int, SqlType.decimal):
            score, method = _compare_numeric(sample_vals, gen_vals)
        elif field.type == SqlType.datetime:
            score, method = _compare_datetime(sample_vals, gen_vals)
        else:
            score, method = _compare_categorical(sample_vals, gen_vals)

        field_scores.append({
            "field": col_name,
            "fit_score": round(score, 3),
            "method": method,
        })

    overall = round(np.mean([f["fit_score"] for f in field_scores]) if field_scores else 0.0, 3)
    return {
        "overall_fit_score": overall,
        "fields": field_scores,
    }


def _to_numeric(values: list[str]) -> np.ndarray:
    nums = pd.to_numeric(values, errors="coerce").dropna().values.astype(float)
    return nums


def _compare_numeric(sample: list[str], generated: list[str]) -> tuple[float, str]:
    s = _to_numeric(sample)
    g = _to_numeric(generated)
    if len(s) < 5 or len(g) < 5:
        return 0.0, "insufficient_data"

    # Histogram overlap (normalized)
    bins = min(20, len(s) // 2, len(g) // 2)
    if bins < 2:
        return 0.0, "insufficient_data"
    min_v, max_v = min(s.min(), g.min()), max(s.max(), g.max())
    if max_v == min_v:
        return 1.0, "constant"

    s_hist, _ = np.histogram(s, bins=bins, range=(min_v, max_v))
    g_hist, _ = np.histogram(g, bins=bins, range=(min_v, max_v))
    s_hist = s_hist / s_hist.sum() if s_hist.sum() else s_hist
    g_hist = g_hist / g_hist.sum() if g_hist.sum() else g_hist

    # Overlap: sum(min(p,q))
    overlap = float(np.sum(np.minimum(s_hist, g_hist)))
    # JS distance (bounded 0-1)
    js = float(jensenshannon(s_hist, g_hist, base=2))
    if np.isnan(js):
        js = 1.0
    score = max(0.0, min(1.0, overlap * (1 - js)))
    return score, "histogram_overlap"


def _compare_categorical(sample: list[str], generated: list[str]) -> tuple[float, str]:
    s_counts = pd.Series(sample).value_counts(normalize=True)
    g_counts = pd.Series(generated).value_counts(normalize=True)
    all_cats = set(s_counts.index) | set(g_counts.index)
    s_vec = np.array([s_counts.get(c, 0.0) for c in all_cats])
    g_vec = np.array([g_counts.get(c, 0.0) for c in all_cats])
    # Chi-square-like: 1 - sum(|p-q|)/2
    l1 = float(np.sum(np.abs(s_vec - g_vec)))
    score = max(0.0, min(1.0, 1.0 - l1 / 2.0))
    return score, "chi_square_proxy"


def _compare_datetime(sample: list[str], generated: list[str]) -> tuple[float, str]:
    s_dt = pd.to_datetime(sample, errors="coerce").dropna()
    g_dt = pd.to_datetime(generated, errors="coerce").dropna()
    if len(s_dt) < 5 or len(g_dt) < 5:
        return 0.0, "insufficient_data"
    s_diff = s_dt.sort_values().diff().dt.total_seconds().dropna().values.astype(float)
    g_diff = g_dt.sort_values().diff().dt.total_seconds().dropna().values.astype(float)
    if len(s_diff) < 5 or len(g_diff) < 5:
        return 0.0, "insufficient_data"
    # Compare log-scaled inter-arrival distributions with histogram overlap
    s_log = np.log1p(s_diff[s_diff > 0])
    g_log = np.log1p(g_diff[g_diff > 0])
    if len(s_log) < 5 or len(g_log) < 5:
        return 0.0, "insufficient_data"
    bins = min(20, len(s_log) // 2, len(g_log) // 2)
    if bins < 2:
        return 0.0, "insufficient_data"
    min_v, max_v = min(s_log.min(), g_log.min()), max(s_log.max(), g_log.max())
    if max_v == min_v:
        return 1.0, "constant"
    s_hist, _ = np.histogram(s_log, bins=bins, range=(min_v, max_v))
    g_hist, _ = np.histogram(g_log, bins=bins, range=(min_v, max_v))
    s_hist = s_hist / s_hist.sum() if s_hist.sum() else s_hist
    g_hist = g_hist / g_hist.sum() if g_hist.sum() else g_hist
    overlap = float(np.sum(np.minimum(s_hist, g_hist)))
    return max(0.0, min(1.0, overlap)), "interarrival_overlap"
