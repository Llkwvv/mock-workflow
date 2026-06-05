"""Tests for LLM module."""

import json
from unittest.mock import Mock, patch

import pytest

from mockworkflow.config import Settings
from mockworkflow.llm import OpenAIFieldParser, resolve_fields, resolve_uncertain_fields
from mockworkflow.schemas.field import FieldSemantic, FieldSpec, SampleProfile, SqlType


def _write_rules_file(path, rules: list[dict]) -> None:
    path.write_text(json.dumps({"rules": rules}, ensure_ascii=False, indent=2), encoding="utf-8")


def test_rule_store_is_used_before_llm(tmp_path):
    """Rules already in the store should be used before any LLM call."""
    rules_file = tmp_path / "rules.json"
    _write_rules_file(
        rules_file,
        [
            {
                "name": "company",
                "type": "VARCHAR",
                "length": 50,
                "nullable": False,
                "semantic": "company_name",
                "confidence": 0.96,
            }
        ],
    )

    profile = SampleProfile(file_path="test.csv", columns=["company", "unknown_field"])
    settings = Settings(llm_enabled=False, rules_file=str(rules_file))

    result = resolve_fields(profile, settings)

    assert result.rules_resolved_count == 1
    assert result.llm_used is False
    by_name = {field.name: field for field in result.fields}
    assert by_name["company"].semantic == FieldSemantic.company_name
    assert by_name["company"].length == 50
    assert "unknown_field" in by_name


@patch("mockworkflow.llm.uncertain_field_parser.OpenAIFieldParser")
def test_llm_fills_missing_fields_and_autosaves(mock_parser_class, tmp_path):
    """Missing rules should be filled by LLM and persisted back to the rule store."""
    rules_file = tmp_path / "rules.json"
    _write_rules_file(rules_file, [])

    profile = SampleProfile(file_path="test.csv", columns=["company", "phone"])
    settings = Settings(
        llm_enabled=True,
        rules_file=str(rules_file),
        rules_autosave=True,
        rules_min_confidence=0.85,
        llm_model="test-model",
    )

    mock_parser = Mock()
    mock_parser.parse_fields.return_value = [
        FieldSpec(
            name="company",
            type=SqlType.varchar,
            length=50,
            nullable=False,
            semantic=FieldSemantic.company_name,
            confidence=0.93,
        ),
        FieldSpec(
            name="phone",
            type=SqlType.varchar,
            length=20,
            nullable=False,
            semantic=FieldSemantic.phone_number,
            confidence=0.91,
        ),
    ]
    mock_parser_class.return_value = mock_parser

    result = resolve_fields(profile, settings)

    assert result.llm_used is True
    assert result.llm_resolved_count == 2
    assert result.rules_resolved_count == 0
    assert result.fallback_resolved_count == 0
    mock_parser.parse_fields.assert_called_once_with(profile, ["company", "phone"])

    saved = json.loads(rules_file.read_text(encoding="utf-8"))
    saved_names = {item["name"] for item in saved["rules"]}
    assert {"company", "phone"}.issubset(saved_names)


@patch("mockworkflow.llm.uncertain_field_parser.OpenAIFieldParser")
def test_resolve_uncertain_fields_handles_llm_failure(mock_parser_class):
    """When LLM fails, should return a minimal fallback result instead of crashing."""
    profile = SampleProfile(file_path="test.csv", columns=["col1"])
    settings = Settings(llm_enabled=True)

    mock_parser = Mock()
    mock_parser.parse_fields.side_effect = TimeoutError("Connection timeout")
    mock_parser_class.return_value = mock_parser

    result = resolve_uncertain_fields(profile, None, settings)

    assert len(result) == 1
    assert result[0].name == "col1"
    assert result[0].uncertain is True


def test_openai_field_parser_validates_mysql_url(monkeypatch):
    """OpenAIFieldParser should require API key or base URL."""
    from mockworkflow.config import Settings

    monkeypatch.setattr("mockworkflow.llm.openai_parser.get_settings", lambda: Settings(
        llm_api_key=None, llm_base_url=None, llm_model="test",
    ))
    with pytest.raises(ValueError, match="Either llm_api_key or llm_base_url"):
        OpenAIFieldParser(api_key=None, base_url=None)


def test_openai_field_parser_accepts_local_model():
    """OpenAIFieldParser should accept local model without API key."""
    parser = OpenAIFieldParser(
        api_key=None,
        base_url="http://localhost:11434/v1",
        model="local-test-model",
    )
    assert parser.base_url == "http://localhost:11434/v1"
    assert parser.model == "local-test-model"


def test_openai_field_parser_uses_settings_defaults():
    """OpenAIFieldParser should use settings as defaults."""
    settings = Settings(
        llm_api_key="test-key",
        llm_base_url="http://api.example.com/v1",
        llm_model="test-model",
        llm_timeout=60,
        llm_max_tokens=4000,
        llm_temperature=0.5,
    )
    parser = OpenAIFieldParser(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        timeout=settings.llm_timeout,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
    )
    assert parser.api_key == "test-key"
    assert parser.base_url == "http://api.example.com/v1"
    assert parser.model == "test-model"
    assert parser.timeout == 60
    assert parser.max_tokens == 4000
    assert parser.temperature == 0.5


def test_openai_field_parser_parses_sql_types_correctly():
    """The parser should map type names to SqlType enum members correctly."""
    parser = OpenAIFieldParser(
        api_key=None,
        base_url="http://localhost:11434/v1",
        model="local-test-model",
    )

    field = parser._create_field_spec(
        {
            "name": "phone",
            "type": "BOOLEAN",
            "nullable": False,
            "semantic": "phone_number",
            "confidence": 0.9,
        }
    )

    assert field.type == SqlType.boolean
    assert field.semantic == FieldSemantic.phone_number
