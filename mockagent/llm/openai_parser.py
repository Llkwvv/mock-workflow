"""OpenAI-compatible LLM field parser implementation."""

import json
from typing import Any

from openai import OpenAI, APITimeoutError, APIConnectionError

from mockagent.config import get_settings
from mockagent.llm.base import LLMFieldParser
from mockagent.llm.prompt import build_field_analysis_prompt
from mockagent.schemas.field import FieldSpec, SampleProfile, SqlType, FieldSemantic


class OpenAIFieldParser(LLMFieldParser):
    """Parse uncertain fields using OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ):
        settings = get_settings()

        self.api_key = api_key or settings.llm_api_key
        self.base_url = base_url or settings.llm_base_url
        self.model = model or settings.llm_model
        self.timeout = timeout or settings.llm_timeout
        self.max_tokens = max_tokens or settings.llm_max_tokens
        self.temperature = temperature or settings.llm_temperature

        if not self.api_key and not self.base_url:
            raise ValueError("Either llm_api_key or llm_base_url must be provided")
        if not self.model:
            raise ValueError("llm_model must be provided (set MOCKAGENT_LLM_MODEL env or pass --llm-model)")

        # For local models (Ollama, etc.), api_key can be any string
        effective_key = self.api_key or "not-needed"

        self.client = OpenAI(
            api_key=effective_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

    def parse_fields(
        self,
        profile: SampleProfile,
        target_columns: list[str] | None = None,
    ) -> list[FieldSpec]:
        """Parse columns using LLM.

        Args:
            profile: Sample profile with column information
            target_columns: Optional list of column names to parse. If omitted, parse all columns.

        Returns:
            List of FieldSpec for parsed columns
        """
        columns = target_columns or profile.columns
        if not columns:
            return []

        prompt = build_field_analysis_prompt(profile, columns)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a database schema expert. Always return valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )

            content = response.choices[0].message.content
            if not content:
                raise ValueError("LLM returned empty response")

            parsed = json.loads(content)
            return self._parse_response(parsed, columns)

        except APITimeoutError as e:
            raise TimeoutError(f"LLM request timed out after {self.timeout}s: {e}") from e
        except APIConnectionError as e:
            raise ConnectionError(f"Failed to connect to LLM API: {e}") from e
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {e}") from e

    def _parse_response(
        self,
        data: dict[str, Any],
        expected_columns: list[str],
    ) -> list[FieldSpec]:
        """Parse LLM JSON response into FieldSpec objects."""
        fields_data = data.get("fields", [])

        if not isinstance(fields_data, list):
            raise ValueError(f"Expected 'fields' to be a list, got {type(fields_data)}")

        result: list[FieldSpec] = []
        expected_set = set(expected_columns)

        for field_data in fields_data:
            name = field_data.get("name")
            if not name:
                continue

            # Skip columns we didn't ask for
            if name not in expected_set:
                continue

            try:
                field = self._create_field_spec(field_data)
                result.append(field)
            except (ValueError, KeyError) as e:
                # Log warning but continue with other fields
                print(f"Warning: Failed to parse field '{name}': {e}")
                continue

        return result

    def _create_field_spec(self, data: dict[str, Any]) -> FieldSpec:
        """Create FieldSpec from parsed JSON data."""
        type_str = data.get("type", "VARCHAR").upper()
        try:
            sql_type = SqlType[type_str.lower()]
        except ValueError:
            sql_type = SqlType.varchar

        semantic_str = data.get("semantic", "unknown").lower()
        try:
            semantic = FieldSemantic(semantic_str)
        except ValueError:
            semantic = FieldSemantic.unknown

        # Build enum values
        enum_values = data.get("enum_values", [])
        if not isinstance(enum_values, list):
            enum_values = []

        return FieldSpec(
            name=data["name"],
            type=sql_type,
            length=data.get("length"),
            precision=data.get("precision"),
            scale=data.get("scale"),
            nullable=data.get("nullable", True),
            primary_key=False,  # LLM doesn't determine PK
            auto_increment=False,  # LLM doesn't determine auto_increment
            comment=data.get("name"),
            semantic=semantic,
            enum_values=enum_values,
            uncertain=False,  # LLM has processed this
            confidence=data.get("confidence", 0.7),
        )
