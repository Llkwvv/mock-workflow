"""Agent tool: detect PII (personally identifiable information) fields."""

from __future__ import annotations

from backend.schemas.field import FieldSemantic, FieldSpec


_PII_KEYWORDS: dict[str, str] = {
    "phone": "phone",
    "mobile": "phone",
    "tel": "phone",
    "手机": "phone",
    "电话": "phone",
    "身份证": "id_card",
    "id_card": "id_card",
    "idcard": "id_card",
    "identity": "id_card",
    "姓名": "name",
    "name": "name",
    "fullname": "name",
    "full_name": "name",
    "银行卡": "bank_card",
    "bank": "bank_card",
    "credit_card": "bank_card",
    "address": "address",
    "addr": "address",
    "地址": "address",
    "location": "address",
    "邮箱": "email",
    "email": "email",
    "mail": "email",
    "护照": "passport",
    "passport": "passport",
    "驾照": "driver_license",
    "license": "driver_license",
    "社保": "ssn",
    "social_security": "ssn",
    "ssn": "ssn",
}

_PII_SEMANTICS: dict[FieldSemantic, str] = {
    FieldSemantic.phone_number: "phone",
    FieldSemantic.email: "email",
}


def detect_pii_fields(fields: list[FieldSpec]) -> dict[str, str]:
    """Scan fields and return a mapping {field_name: pii_type}.

    Types: phone, id_card, name, bank_card, address, email.
    """
    result: dict[str, str] = {}
    for field in fields:
        # Check semantic first
        if field.semantic in _PII_SEMANTICS:
            result[field.name] = _PII_SEMANTICS[field.semantic]
            continue
        # Check column name keywords
        lower_name = field.name.lower()
        for keyword, pii_type in _PII_KEYWORDS.items():
            if keyword in lower_name:
                result[field.name] = pii_type
                break
    return result
