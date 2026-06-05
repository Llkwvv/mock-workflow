"""Tests for LLM value pool generation and persistence."""

import json
from unittest.mock import Mock, patch

from mockworkflow.config import Settings
from mockworkflow.llm import resolve_fields
from mockworkflow.llm.value_pool import is_pool_eligible
from mockworkflow.mock.generator import generate_mock_rows
from mockworkflow.rules.store import RuleStore
from mockworkflow.schemas.field import FieldSemantic, FieldSpec, SampleProfile, SqlType


def _write_rules_file(path, rules: list[dict]) -> None:
    path.write_text(json.dumps({"rules": rules}, ensure_ascii=False, indent=2), encoding="utf-8")


def test_value_pool_used_in_generation() -> None:
    """Generator should sample from value_pool when present."""
    pool = ["新桑塔纳", "卡罗拉", "宝来"]
    field = FieldSpec(
        name="车型",
        type=SqlType.varchar,
        length=20,
        semantic=FieldSemantic.vehicle_model,
        value_pool=pool,
    )

    rows = generate_mock_rows([field], rows=20)

    assert all(row["车型"] in pool for row in rows)


def test_enum_values_take_precedence_over_value_pool() -> None:
    """Enum values must win over value_pool to preserve closed-set semantics."""
    field = FieldSpec(
        name="status",
        type=SqlType.varchar,
        length=10,
        semantic=FieldSemantic.status,
        enum_values=["active", "inactive"],
        value_pool=["bogus"],
    )

    rows = generate_mock_rows([field], rows=10)

    assert all(row["status"] in {"active", "inactive"} for row in rows)


def test_is_pool_eligible_filters_correctly() -> None:
    eligible = FieldSpec(name="车型", type=SqlType.varchar, length=20, semantic=FieldSemantic.vehicle_model)
    long_varchar = FieldSpec(name="备注", type=SqlType.varchar, length=255, semantic=FieldSemantic.unknown)
    has_enum = FieldSpec(
        name="status",
        type=SqlType.varchar,
        length=10,
        semantic=FieldSemantic.unknown,
        enum_values=["a", "b"],
    )
    text_type = FieldSpec(name="描述", type=SqlType.text, semantic=FieldSemantic.text)
    skip_phone = FieldSpec(name="phone", type=SqlType.varchar, length=20, semantic=FieldSemantic.phone_number)

    assert is_pool_eligible(eligible) is True
    assert is_pool_eligible(long_varchar) is True  # length no longer filters
    assert is_pool_eligible(has_enum) is False
    assert is_pool_eligible(text_type) is False  # SqlType.text skipped
    assert is_pool_eligible(skip_phone) is False


@patch("mockworkflow.llm.value_pool.OpenAI")
def test_resolve_fields_generates_and_persists_value_pool(mock_openai_class, tmp_path):
    """When pool generation is enabled, LLM is called once and the pool is persisted."""
    rules_file = tmp_path / "rules.json"
    _write_rules_file(
        rules_file,
        [
            {
                "name": "车型",
                "type": "VARCHAR",
                "length": 20,
                "nullable": False,
                "semantic": "vehicle_model",
                "confidence": 0.95,
            }
        ],
    )

    profile = SampleProfile(
        file_path="test.csv",
        columns=["车型"],
        samples={"车型": ["凯美瑞", "轩逸"]},
    )
    settings = Settings(
        llm_enabled=True,
        llm_value_pool_enabled=True,
        llm_value_pool_size=3,
        llm_base_url="http://localhost:11434/v1",
        llm_api_key="test-key",
        rules_file=str(rules_file),
        rules_autosave=True,
    )

    mock_client = Mock()
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = json.dumps(
        {"values": ["凯美瑞", "轩逸", "卡罗拉"]}
    )
    mock_client.chat.completions.create.return_value = mock_response
    mock_openai_class.return_value = mock_client

    result = resolve_fields(profile, settings)

    assert result.value_pools_generated == 1
    field = next(f for f in result.fields if f.name == "车型")
    assert field.value_pool == ["凯美瑞", "轩逸", "卡罗拉"]

    # Persisted to rule store
    saved = json.loads(rules_file.read_text(encoding="utf-8"))
    saved_rule = next(r for r in saved["rules"] if r["name"] == "车型")
    assert saved_rule["value_pool"] == ["凯美瑞", "轩逸", "卡罗拉"]


@patch("mockworkflow.llm.value_pool.OpenAI")
def test_existing_pool_skips_llm_call(mock_openai_class, tmp_path):
    """If a rule already has a value_pool, no LLM call should occur."""
    rules_file = tmp_path / "rules.json"
    _write_rules_file(
        rules_file,
        [
            {
                "name": "车型",
                "type": "VARCHAR",
                "length": 20,
                "nullable": False,
                "semantic": "vehicle_model",
                "confidence": 0.95,
                "value_pool": ["A", "B", "C"],
            }
        ],
    )

    profile = SampleProfile(file_path="test.csv", columns=["车型"], samples={"车型": ["X"]})
    settings = Settings(
        llm_enabled=True,
        llm_value_pool_enabled=True,
        llm_base_url="http://localhost:11434/v1",
        llm_api_key="test-key",
        rules_file=str(rules_file),
    )

    result = resolve_fields(profile, settings)

    assert result.value_pools_generated == 0
    mock_openai_class.assert_not_called()
    field = next(f for f in result.fields if f.name == "车型")
    assert field.value_pool == ["A", "B", "C"]


def test_value_pool_disabled_by_default(tmp_path):
    """Without llm_value_pool_enabled, no LLM call is made even if llm_enabled=True."""
    rules_file = tmp_path / "rules.json"
    _write_rules_file(
        rules_file,
        [
            {
                "name": "车型",
                "type": "VARCHAR",
                "length": 20,
                "nullable": False,
                "semantic": "vehicle_model",
                "confidence": 0.95,
            }
        ],
    )

    profile = SampleProfile(file_path="test.csv", columns=["车型"], samples={"车型": ["X"]})
    settings = Settings(
        llm_enabled=False,
        llm_value_pool_enabled=False,
        rules_file=str(rules_file),
    )

    result = resolve_fields(profile, settings)

    assert result.value_pools_generated == 0
    field = next(f for f in result.fields if f.name == "车型")
    assert field.value_pool == []
