"""OpenAI-compatible LLM field parser implementation."""

import json
import logging
from typing import Any

from openai import APIConnectionError, APIError, APITimeoutError, BadRequestError, OpenAI

from backend.config import get_settings
from backend.llm.base import LLMFieldParser
from backend.llm.model_pool import get_model_pool
from backend.llm.model_rotator import ModelRotator
from backend.llm.prompt import build_field_analysis_prompt
from backend.schemas.field import FieldSpec, SampleProfile, SqlType, FieldSemantic


logger = logging.getLogger(__name__)


def _safe_dump(value: Any) -> str:
    try:
        if hasattr(value, "model_dump"):
            return json.dumps(value.model_dump(), ensure_ascii=False, default=str)[:4000]
        if hasattr(value, "response") and getattr(value, "response", None) is not None:
            response = getattr(value, "response")
            body = getattr(response, "text", None)
            if body:
                return str(body)[:4000]
        return str(value)[:4000]
    except Exception as exc:
        return f"<failed to dump object: {exc}>"


class OpenAIFieldParser(LLMFieldParser):
    """Parse uncertain fields using OpenAI-compatible API with model rotation."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        enable_rotation: bool = True,
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
            raise ValueError("llm_model must be provided (set MOCKWORKFLOW_LLM_MODEL env or pass --llm-model)")

        # For local models (Ollama, etc.), api_key can be any string
        effective_key = self.api_key or "not-needed"

        self.client = OpenAI(
            api_key=effective_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

        # Model rotation support
        self.enable_rotation = enable_rotation
        self.rotator: ModelRotator | None = None
        if enable_rotation:
            pool = get_model_pool()
            self.rotator = ModelRotator(pool)
            # If a specific model is forced, tell the rotator
            if self.model:
                self.rotator.set_forced_model(self.model)

    def parse_fields(
        self,
        profile: SampleProfile,
        target_columns: list[str] | None = None,
        rag_rules: list[dict] | None = None,
        rag_samples: list[dict] | None = None,
    ) -> list[FieldSpec]:
        """Parse columns using LLM.

        Args:
            profile: Sample profile with column information
            target_columns: Optional list of column names to parse. If omitted, parse all columns.
            rag_rules: Retrieved similar rules for RAG context injection
            rag_samples: Retrieved similar sample profiles for RAG context injection

        Returns:
            List of FieldSpec for parsed columns
        """
        columns = target_columns or profile.columns
        if not columns:
            return []

        prompt = build_field_analysis_prompt(profile, columns, rag_rules=rag_rules, rag_samples=rag_samples)

        max_retries = 3
        excluded: set[str] = set()
        last_error: Exception | None = None

        for attempt in range(max_retries):
            model_name = self._select_model(excluded)
            if not model_name:
                logger.error("No available model to try after %d attempts", attempt)
                break

            excluded.add(model_name)

            try:
                response = self.client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a database schema expert. Always return valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                )

                if response is None:
                    raise ValueError("LLM returned no response")
                if not response.choices:
                    raise ValueError("LLM returned no choices")

                choice = response.choices[0]
                message = getattr(choice, "message", None)
                if message is None:
                    finish_reason = getattr(choice, "finish_reason", None)
                    raise ValueError(f"LLM returned no message (finish_reason={finish_reason})")

                content = message.content
                if not content:
                    raise ValueError("LLM returned empty response")

                # Success – record and return
                if self.rotator:
                    self.rotator.record_success(model_name)
                self.model = model_name  # Update current model

                parsed = json.loads(content)
                return self._parse_response(parsed, columns)

            except (APITimeoutError, APIConnectionError, BadRequestError, APIError) as e:
                error_msg = _safe_dump(e)
                logger.warning(
                    "Attempt %d: model=%s failed - %s",
                    attempt + 1,
                    model_name,
                    error_msg,
                )
                if self.rotator:
                    self.rotator.record_failure(model_name, error_msg)
                last_error = e
                continue
            except (ValueError, json.JSONDecodeError) as e:
                # These are response-format errors; also retry
                logger.warning(
                    "Attempt %d: model=%s response error - %s",
                    attempt + 1,
                    model_name,
                    str(e),
                )
                if self.rotator:
                    self.rotator.record_failure(model_name, str(e))
                last_error = e
                continue

        # All retries exhausted
        if isinstance(last_error, APITimeoutError):
            raise TimeoutError(f"LLM request timed out after {self.timeout}s: {last_error}") from last_error
        if isinstance(last_error, APIConnectionError):
            raise ConnectionError(f"Failed to connect to LLM API: {last_error}") from last_error
        if isinstance(last_error, BadRequestError):
            raise ValueError(f"LLM bad request: {last_error}") from last_error
        if isinstance(last_error, APIError):
            raise ValueError(f"LLM API error: {last_error}") from last_error
        if isinstance(last_error, json.JSONDecodeError):
            raise ValueError(f"LLM returned invalid JSON: {last_error}") from last_error
        raise ValueError(f"All models failed after {len(excluded)} attempts. Last error: {last_error}")

    def _select_model(self, excluded: set[str]) -> str | None:
        """Pick the next model to try (with rotation if enabled)."""
        if self.rotator:
            return self.rotator.select_model(requested_model=self.model, excluded=excluded)
        if self.model not in excluded:
            return self.model
        return None

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
