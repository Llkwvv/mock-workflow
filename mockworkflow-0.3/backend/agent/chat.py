"""Conversational entry for mock data generation via LLM polling."""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from backend.config import Settings


SYSTEM_PROMPT = """You are Mockworkflow Agent, an expert in mock data generation.
You help users configure generation tasks through natural language.
Available parameters:
- sample_file: path to sample file
- table_name: target table name
- rows: number of rows to generate (1-100000)
- output: preview, csv, json, excel, mysql
- enable_db_export: true/false
- cron: cron expression for scheduled tasks

When the user wants to generate data, return a JSON object with:
{"action": "generate", "params": {...}}
For schedules, return:
{"action": "schedule", "params": {...}}
For general chat, return:
{"action": "chat", "message": "..."}
"""


def chat_message(history: list[dict[str, str]], user_message: str, settings: Settings) -> dict[str, Any]:
    """Process a chat message and return an action or response."""
    if not settings.llm_enabled:
        return {"action": "chat", "message": "LLM is disabled. Please configure LLM settings first."}

    client = get_client(settings)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [{"role": "user", "content": user_message}]

    try:
        response = client.chat.completions.create(
            model=settings.llm_model or "gpt-3.5-turbo",
            messages=messages,
            max_tokens=1000,
            temperature=0.3,
        )
        content = response.choices[0].message.content or "{}"
        # Try to parse JSON first
        try:
            parsed = json.loads(content)
            return parsed
        except json.JSONDecodeError:
            return {"action": "chat", "message": content}
    except Exception as e:
        return {"action": "chat", "message": f"Error: {e}"}
