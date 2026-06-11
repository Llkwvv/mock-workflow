"""PII anonymizer for generated mock data."""

from __future__ import annotations

import re


def anonymize_phone(value: str) -> str:
    """Mask phone number as 138****8888."""
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 11:
        return digits[:3] + "****" + digits[-4:]
    if len(digits) >= 7:
        return digits[:2] + "****" + digits[-4:]
    return digits[:2] + "****"


def anonymize_id_card(value: str) -> str:
    """Mask ID card as 110**********1234."""
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 18:
        return digits[:3] + "***********" + digits[-4:]
    if len(digits) >= 6:
        return digits[:3] + "****" + digits[-4:]
    return "****"


def anonymize_name(value: str) -> str:
    """Mask name as 张*."""
    text = str(value).strip()
    if len(text) <= 1:
        return "*"
    if len(text) == 2:
        return text[0] + "*"
    return text[0] + "*" + text[-1]


def anonymize_bank_card(value: str) -> str:
    """Mask bank card as **** **** **** 1234."""
    digits = re.sub(r"\D", "", str(value))
    if len(digits) >= 8:
        return "**** **** **** " + digits[-4:]
    return "****"


def anonymize_address(value: str) -> str:
    """Mask address: keep district/street, mask house number."""
    text = str(value)
    # Simple heuristic: remove trailing numbers and specific keywords
    text = re.sub(r"\d+[号室栋单元层]-?\d*", "***", text)
    text = re.sub(r"\d+号", "***", text)
    text = re.sub(r"\d+栋", "***", text)
    text = re.sub(r"\d+单元", "***", text)
    text = re.sub(r"\d+层", "***", text)
    text = re.sub(r"\d+室", "***", text)
    return text


def anonymize_email(value: str) -> str:
    """Mask email as a***@example.com."""
    text = str(value).strip()
    if "@" not in text:
        return text
    local, domain = text.split("@", 1)
    if len(local) <= 1:
        masked_local = "*"
    else:
        masked_local = local[0] + "*" * (len(local) - 1)
    return f"{masked_local}@{domain}"


def anonymize_passport(value: str) -> str:
    """Mask passport number."""
    text = re.sub(r"\D", "", str(value))
    if len(text) >= 6:
        return text[:2] + "****" + text[-2:]
    return "****"


def anonymize_driver_license(value: str) -> str:
    """Mask driver license number."""
    text = re.sub(r"\D", "", str(value))
    if len(text) >= 6:
        return text[:2] + "****" + text[-2:]
    return "****"


def anonymize_ssn(value: str) -> str:
    """Mask SSN / social security number."""
    text = re.sub(r"\D", "", str(value))
    if len(text) >= 6:
        return text[:2] + "****" + text[-2:]
    return "****"


_ANONYMIZERS: dict[str, callable] = {
    "phone": anonymize_phone,
    "id_card": anonymize_id_card,
    "name": anonymize_name,
    "bank_card": anonymize_bank_card,
    "address": anonymize_address,
    "email": anonymize_email,
    "passport": anonymize_passport,
    "driver_license": anonymize_driver_license,
    "ssn": anonymize_ssn,
}


def anonymize_value(value: object, pii_type: str) -> object:
    """Anonymize a single value according to its PII type."""
    fn = _ANONYMIZERS.get(pii_type)
    if not fn:
        return value
    return fn(value)
