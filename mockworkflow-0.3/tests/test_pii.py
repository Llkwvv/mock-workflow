"""Tests for PII detection and anonymization."""

import pytest

from backend.agent.tools.pii import detect_pii_fields
from backend.mock.anonymizer import anonymize_value
from backend.schemas.field import FieldSpec, SqlType


def _field(name: str, semantic: str | None = None) -> FieldSpec:
    return FieldSpec(
        name=name,
        type=SqlType.varchar,
        nullable=True,
        semantic=semantic,
    )


def test_detect_phone():
    fields = [_field("mobile_phone"), _field("phone_num")]
    result = detect_pii_fields(fields)
    assert result["mobile_phone"] == "phone"
    assert result["phone_num"] == "phone"


def test_detect_id_card():
    fields = [_field("id_card"), _field("identity_number")]
    result = detect_pii_fields(fields)
    assert result["id_card"] == "id_card"
    assert result["identity_number"] == "id_card"


def test_detect_name():
    fields = [_field("full_name"), _field("user_name")]
    result = detect_pii_fields(fields)
    assert result["full_name"] == "name"
    assert "user_name" not in result


def test_detect_passport():
    fields = [_field("passport_no")]
    result = detect_pii_fields(fields)
    assert result["passport_no"] == "passport"


def test_anonymize_phone():
    assert anonymize_value("13800138000", "phone") == "138****8000"


def test_anonymize_passport():
    assert anonymize_value("AB123456", "passport") == "AB****56"


def test_anonymize_ssn():
    assert anonymize_value("123456789", "ssn") == "12****89"


def test_anonymize_driver_license():
    assert anonymize_value("京A12345", "driver_license") == "****45"
