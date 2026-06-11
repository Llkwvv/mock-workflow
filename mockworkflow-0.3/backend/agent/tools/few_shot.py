"""Agent tool: recommend few-shot samples based on task history similarity."""

from __future__ import annotations

from typing import Any

from difflib import SequenceMatcher


def recommend_few_shot(
    current_file: str,
    current_columns: list[str],
    task_history: list[dict[str, Any]],
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Recommend the most similar past tasks as few-shot examples.

    Similarity is based on column name overlap and file name similarity.
    """
    if not task_history:
        return []

    scored = []
    current_set = set(c.lower() for c in current_columns)

    for task in task_history:
        past_file = task.get("sample_filename", "")
        past_cols = task.get("columns", [])
        if not past_cols:
            continue

        # Column Jaccard similarity
        past_set = set(c.lower() for c in past_cols)
        intersection = len(current_set & past_set)
        union = len(current_set | past_set)
        col_sim = intersection / union if union > 0 else 0.0

        # File name similarity
        name_sim = SequenceMatcher(None, current_file.lower(), past_file.lower()).ratio()

        # Weighted score
        score = col_sim * 0.7 + name_sim * 0.3
        scored.append({"task": task, "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return [
        {
            "sample_filename": s["task"].get("sample_filename", ""),
            "table_name": s["task"].get("table_name", ""),
            "columns": s["task"].get("columns", []),
            "similarity": round(s["score"], 3),
        }
        for s in scored[:top_k]
    ]
