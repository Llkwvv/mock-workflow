"""Agent tool: cluster uploaded samples by semantic similarity."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from difflib import SequenceMatcher


def cluster_samples(
    samples: list[dict[str, Any]],
    similarity_threshold: float = 0.6,
) -> dict[str, list[dict[str, Any]]]:
    """Cluster sample files by column name and file name similarity.

    Returns clusters as a dict {cluster_id: [sample, ...]}.
    """
    if not samples:
        return {}

    n = len(samples)
    visited = [False] * n
    clusters: list[list[int]] = []

    def _sim(a: dict, b: dict) -> float:
        cols_a = set(c.lower() for c in a.get("columns", []))
        cols_b = set(c.lower() for c in b.get("columns", []))
        union = len(cols_a | cols_b)
        col_sim = len(cols_a & cols_b) / union if union else 0.0
        name_sim = SequenceMatcher(None, a.get("name", "").lower(), b.get("name", "").lower()).ratio()
        return col_sim * 0.7 + name_sim * 0.3

    for i in range(n):
        if visited[i]:
            continue
        cluster = [i]
        visited[i] = True
        for j in range(i + 1, n):
            if not visited[j] and _sim(samples[i], samples[j]) >= similarity_threshold:
                cluster.append(j)
                visited[j] = True
        clusters.append(cluster)

    result: dict[str, list[dict[str, Any]]] = {}
    for idx, cluster in enumerate(clusters):
        cluster_id = f"cluster_{idx + 1}"
        result[cluster_id] = [samples[i] for i in cluster]
    return result
