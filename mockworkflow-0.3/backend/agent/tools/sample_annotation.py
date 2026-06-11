"""Agent tool: automatic sample annotation for uploaded files."""

from __future__ import annotations

import json
import os
from typing import Any

from backend.config import Settings
from backend.llm.client import get_client


def auto_annotate(
    file_name: str,
    columns: list[str],
    sample_rows: list[dict[str, Any]],
    settings: Settings,
) -> dict[str, Any]:
    """Generate a human-readable annotation for an uploaded sample file.

    Returns {"title": "...", "description": "...", "tags": [...], "suggested_table_name": "..."}.
    """
    if not settings.llm_enabled:
        return _fallback_annotation(file_name, columns)

    try:
        client = get_client(settings)
        prompt = (
            f"Analyze the following sample data file and provide metadata.\n"
            f"File name: {file_name}\n"
            f"Columns: {columns}\n"
            f"Sample rows (first 3):\n{json.dumps(sample_rows[:3], ensure_ascii=False)}\n\n"
            f"Return ONLY a JSON object with keys: title, description, tags (list), suggested_table_name.\n"
            f"Use Chinese for title and description."
        )
        response = client.chat.completions.create(
            model=settings.llm_model or "gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a data analyst annotating sample datasets."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=500,
            temperature=0.2,
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        return {
            "title": parsed.get("title", file_name),
            "description": parsed.get("description", ""),
            "tags": parsed.get("tags", []),
            "suggested_table_name": parsed.get("suggested_table_name", file_name.split(".")[0]),
        }
    except Exception as e:
        return {**_fallback_annotation(file_name, columns), "error": str(e)}


def _fallback_annotation(file_name: str, columns: list[str]) -> dict[str, Any]:
    from backend.utils.pinyin import filename_to_table_name
    return {
        "title": file_name,
        "description": f"包含 {len(columns)} 列的数据文件",
        "tags": ["auto"],
        "suggested_table_name": filename_to_table_name(file_name) or file_name.split(".")[0],
    }
