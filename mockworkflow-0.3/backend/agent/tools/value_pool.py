"""Agent tool: generate enhanced value pools with business-context awareness."""

from __future__ import annotations

import json
from typing import Any

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI

from backend.config import Settings, get_settings
from backend.schemas.field import FieldSpec, SampleProfile


def generate_enhanced_pool(
    field: FieldSpec,
    profile: SampleProfile,
    settings: Settings | None = None,
    size: int = 50,
) -> list[str] | None:
    """Generate a value pool for a field using business-context-aware prompt.

    Unlike the raw value_pool module, this tool constructs richer prompts
    by including neighboring field semantics and table context.
    """
    if settings is None:
        settings = get_settings()

    if not (settings.llm_enabled and settings.llm_model):
        return None

    client = OpenAI(
        api_key=settings.llm_api_key or "not-needed",
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout,
    )

    prompt = _build_enhanced_pool_prompt(field, profile, size)
    try:
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "You generate realistic candidate values for a database column. Always return valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
        )
    except (APITimeoutError, APIConnectionError, APIError, ValueError):
        return None

    content = response.choices[0].message.content if response.choices else ""
    if not content:
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None

    return _extract_pool(parsed, size)


def _build_enhanced_pool_prompt(field: FieldSpec, profile: SampleProfile, size: int) -> str:
    sample_preview = profile.samples.get(field.name, [])[:5]
    semantic_hint = field.semantic.value if field.semantic else "unknown"
    length_hint = f"<= {field.length} characters" if field.length else "concise"

    # Include neighboring field names for context
    neighbors = [c for c in profile.columns if c != field.name][:5]

    return (
        f"Generate {size} realistic candidate values for the database column below. "
        f"Values must be plausible, distinct, and culturally consistent with the samples.\n\n"
        f"Column name: {field.name}\n"
        f"Comment: {field.comment or field.name}\n"
        f"Semantic: {semantic_hint}\n"
        f"SQL type: {field.type.value}\n"
        f"Length constraint: {length_hint}\n"
        f"Other columns in the same table: {neighbors}\n"
        f"Sample values from real data: {sample_preview}\n\n"
        f"Return ONLY a valid JSON object of the form:\n"
        f'{{"values": ["v1", "v2", ...]}}\n\n'
        f"Rules:\n"
        f"- Return exactly {size} unique values when possible.\n"
        f"- Each value must be a single string, no surrounding quotes or commentary.\n"
        f"- Do not include null, empty strings, or duplicates.\n"
        f"- Match the language and style of the samples (e.g., Chinese if samples are Chinese)."
    )


def _extract_pool(data: Any, size: int) -> list[str]:
    if isinstance(data, dict):
        values = data.get("values")
    else:
        values = data
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values:
        if item is None:
            continue
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
        if len(cleaned) >= size:
            break
    return cleaned
