"""Agent tool: parse natural language schedule descriptions into cron expressions."""

from __future__ import annotations

import json
import os

from backend.config import Settings
from backend.llm.client import get_client


def parse_schedule_nlp(text: str, settings: Settings) -> dict[str, str]:
    """Convert a natural language schedule description into a cron string.

    Returns {"cron": "0 3 * * *", "description": "...", "confidence": "high"}.
    Falls back to simple keyword matching if LLM is disabled or fails.
    """
    text_lower = text.strip().lower()

    # Quick keyword fallback patterns (Chinese / English)
    if any(k in text_lower for k in ("每小时", "每小时", "every hour")):
        return {"cron": "0 * * * *", "description": "每小时整点", "confidence": "high"}
    if any(k in text_lower for k in ("每天凌晨3点", "每天凌晨三点", "every day at 3am")):
        return {"cron": "0 3 * * *", "description": "每天凌晨3点", "confidence": "high"}
    if any(k in text_lower for k in ("每天中午12点", "每天中午十二点", "every day at noon")):
        return {"cron": "0 12 * * *", "description": "每天中午12点", "confidence": "high"}
    if any(k in text_lower for k in ("每分钟", "every minute")):
        return {"cron": "* * * * *", "description": "每分钟", "confidence": "high"}
    if any(k in text_lower for k in ("每周一", "every monday")):
        return {"cron": "0 0 * * 1", "description": "每周一零点", "confidence": "high"}
    if any(k in text_lower for k in ("每月1号", "每月一号", "1st of month")):
        return {"cron": "0 0 1 * *", "description": "每月1号零点", "confidence": "high"}

    if not settings.llm_enabled:
        return {"cron": "", "description": "无法解析", "confidence": "low", "error": "LLM disabled and no keyword match"}

    try:
        client = get_client(settings)
        response = client.chat.completions.create(
            model=settings.llm_model or "gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a cron expression parser. "
                        "Given a natural language schedule description, return ONLY a JSON object with:\n"
                        '{"cron": "valid cron string", "description": "short Chinese description"}\n'
                        "Rules:\n"
                        "- Use standard 5-field cron format (minute hour day month weekday).\n"
                        "- Description must be in Chinese.\n"
                    ),
                },
                {"role": "user", "content": f"Schedule description: {text}"},
            ],
            response_format={"type": "json_object"},
            max_tokens=200,
            temperature=0.1,
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        cron = parsed.get("cron", "")
        description = parsed.get("description", text)
        return {"cron": cron, "description": description, "confidence": "medium"}
    except Exception as e:
        return {"cron": "", "description": "", "confidence": "low", "error": str(e)}
