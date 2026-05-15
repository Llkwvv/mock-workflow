"""Generate and persist per-field value pools via LLM.

Value pools are realistic candidate values produced once by an LLM and stored
in the rule store. At generation time, the mock generator samples from the
pool instead of using Faker fallbacks. Pools are reused across runs and only
regenerated for fields whose pool is empty.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI

from mockagent.config import Settings, get_settings
from mockagent.rules.store import RuleStore
from mockagent.schemas.field import FieldSemantic, FieldSpec, SampleProfile, SqlType


# Semantics for which a value pool is meaningful. Faker already covers
# phone/email/url/license_plate/coordinate/time/flag/status/direction well.
_POOL_ELIGIBLE_SEMANTICS: set[FieldSemantic] = {
    FieldSemantic.company_name,
    FieldSemantic.vehicle_model,
    FieldSemantic.text,
    FieldSemantic.unknown,
}

def is_pool_eligible(field: FieldSpec) -> bool:
    """Return True if the field should have a value pool generated.

    SqlType.text is skipped: long descriptions are better handled by per-row
    generation than a fixed pool. VARCHAR length is NOT used as a filter
    because sample-driven schemas default to 255 even for short content.
    """
    if field.enum_values:
        return False
    if field.semantic not in _POOL_ELIGIBLE_SEMANTICS:
        return False
    if field.type != SqlType.varchar:
        return False
    return True


def ensure_value_pools(
    fields: list[FieldSpec],
    profile: SampleProfile,
    settings: Settings | None = None,
    rule_store: RuleStore | None = None,
) -> int:
    """Fill empty value pools for eligible fields by calling the LLM once per field.

    Pools are persisted back to the rule store so subsequent runs reuse them
    without invoking the LLM. Returns the number of pools newly generated.
    """
    if settings is None:
        settings = get_settings()

    if not (settings.llm_enabled and settings.llm_value_pool_enabled):
        return 0

    targets = [f for f in fields if not f.value_pool and is_pool_eligible(f)]
    if not targets:
        return 0

    client = _build_client(settings)
    store = rule_store or RuleStore(settings.rules_file)
    generated = 0

    print(f"[value_pool] generating pools for {len(targets)} field(s) in parallel: "
          f"{[f.name for f in targets]}")
    start = time.perf_counter()

    def _task(field: FieldSpec) -> tuple[FieldSpec, list[str] | None, Exception | None]:
        try:
            pool = _generate_pool(
                client=client,
                model=settings.llm_model,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                field=field,
                samples=profile.samples.get(field.name, []),
                size=settings.llm_value_pool_size,
            )
            return field, pool, None
        except (TimeoutError, ConnectionError, ValueError, APIError) as exc:
            return field, None, exc

    max_workers = min(len(targets), 8)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_task, field) for field in targets]
        for future in as_completed(futures):
            field, pool, exc = future.result()
            if exc is not None:
                print(f"[value_pool]  - '{field.name}' failed: {exc}")
                continue
            if not pool:
                print(f"[value_pool]  - '{field.name}' returned empty pool")
                continue
            field.value_pool = pool
            if settings.rules_autosave:
                store.upsert_value_pool(field.name, pool)
            generated += 1
            print(f"[value_pool]  - '{field.name}' ok ({len(pool)} values)")

    print(f"[value_pool] done in {time.perf_counter() - start:.1f}s, generated={generated}")
    return generated


def _build_client(settings: Settings) -> OpenAI:
    if not settings.llm_api_key and not settings.llm_base_url:
        raise ValueError("Either llm_api_key or llm_base_url must be provided")
    if not settings.llm_model:
        raise ValueError("llm_model must be provided (set MOCKAGENT_LLM_MODEL env or pass --llm-model)")
    return OpenAI(
        api_key=settings.llm_api_key or "not-needed",
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout,
    )


def _generate_pool(
    client: OpenAI,
    model: str,
    temperature: float,
    max_tokens: int,
    field: FieldSpec,
    samples: list[str],
    size: int,
) -> list[str]:
    prompt = _build_pool_prompt(field, samples, size)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You generate realistic candidate values for a database column. Always return valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except APITimeoutError as exc:
        raise TimeoutError(f"LLM request timed out: {exc}") from exc
    except APIConnectionError as exc:
        raise ConnectionError(f"Failed to connect to LLM API: {exc}") from exc
    except APIError:
        raise

    content = response.choices[0].message.content if response.choices else ""
    if not content:
        raise ValueError("LLM returned empty response")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned invalid JSON: {exc}") from exc
    return _extract_pool(parsed, size)


def _build_pool_prompt(field: FieldSpec, samples: list[str], size: int) -> str:
    sample_preview = samples[:5]
    semantic_hint = field.semantic.value if field.semantic else "unknown"
    length_hint = f"<= {field.length} characters" if field.length else "concise"
    return (
        f"Generate {size} realistic candidate values for the database column below. "
        f"Values must be plausible, distinct, and culturally consistent with the samples.\n\n"
        f"Column name: {field.name}\n"
        f"Comment: {field.comment or field.name}\n"
        f"Semantic: {semantic_hint}\n"
        f"SQL type: {field.type.value}\n"
        f"Length constraint: {length_hint}\n"
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
