"""Cross-field coherence: make derived fields mutually consistent per row.

The per-field generators in ``generator.py`` are independent, so on their own
they happily emit an impossible row such as::

    身份证号 = 370811199003074219   出生日期 = 1975-08-02   性别 = 女   年龄 = 12

This module runs a *post-generation* pass that detects related field groups by
their semantic and rewrites them so each row is internally consistent:

  - 身份证号 encodes 出生日期 / 性别 / 籍贯 -> derive those fields from it
  - 年龄 = 当前年 - 出生年
  - 省 / 市 / 区县 come from one real administrative region (no impossible mix)
  - 统一社会信用代码 / 邮政编码 share the same region when present

It is intentionally separate from ``constraint_engine`` (which handles ordering
comparisons like ``start < end``); both passes compose.
"""

from __future__ import annotations

import random
from datetime import date, datetime

from backend.mock import cn_identifiers as cn
from backend.mock.region_data import Region, random_region, region_by_code_prefix
from backend.schemas.field import FieldSemantic, FieldSpec


# --------------------------------------------------------------------------- #
# Role detection
# --------------------------------------------------------------------------- #

class _Roles:
    """Field names grouped by the coherence role they play."""

    def __init__(self) -> None:
        self.id_card: list[FieldSpec] = []
        self.credit_code: list[FieldSpec] = []
        self.bank_card: list[FieldSpec] = []
        self.birthdate: list[FieldSpec] = []
        self.gender: list[FieldSpec] = []
        self.age: list[FieldSpec] = []
        self.postal: list[FieldSpec] = []
        self.region: list[FieldSpec] = []

    @property
    def has_identity(self) -> bool:
        return bool(self.id_card or (self.birthdate and (self.gender or self.age)))

    @property
    def active(self) -> bool:
        return bool(
            self.id_card or self.credit_code or self.bank_card or self.birthdate
            or self.gender or self.age or self.postal or self.region
        )


def detect_roles(fields: list[FieldSpec]) -> _Roles:
    roles = _Roles()
    for field in fields:
        sem = field.semantic
        if sem == FieldSemantic.id_card:
            roles.id_card.append(field)
        elif sem == FieldSemantic.credit_code:
            roles.credit_code.append(field)
        elif sem == FieldSemantic.bank_card:
            roles.bank_card.append(field)
        elif sem == FieldSemantic.birthdate:
            roles.birthdate.append(field)
        elif sem == FieldSemantic.gender:
            roles.gender.append(field)
        elif sem == FieldSemantic.age:
            roles.age.append(field)
        elif sem == FieldSemantic.postal_code:
            roles.postal.append(field)
        elif sem == FieldSemantic.region:
            roles.region.append(field)
    return roles


# --------------------------------------------------------------------------- #
# Format detection helpers (match the look of the real sample)
# --------------------------------------------------------------------------- #

def _detect_gender_format(field: FieldSpec) -> tuple[str, str]:
    """Return (male_label, female_label) inferred from the sample values."""
    values = {str(v).strip() for v in (field.value_pool or []) if str(v).strip()}
    values |= {str(v).strip() for v in (field.enum_values or [])}
    if values & {"M", "F"}:
        return "M", "F"
    if values & {"m", "f"}:
        return "m", "f"
    if values & {"1", "2"}:
        return "1", "2"          # convention: 1=男, 2=女
    if values & {"male", "female", "Male", "Female"}:
        return "男", "女"
    return "男", "女"


def _detect_birth_format(field: FieldSpec) -> str:
    """Return a strftime format matching the sample's birthdate look."""
    for v in field.value_pool or []:
        text = str(v).strip()
        if not text:
            continue
        if "-" in text:
            return "%Y-%m-%d" if text.count("-") >= 2 else "%Y-%m"
        if "/" in text:
            return "%Y/%m/%d"
        if text.isdigit():
            return "%Y%m%d" if len(text) >= 8 else "%Y"
    return "%Y-%m-%d"


def _years_since(birth: date) -> int:
    today = date.today()
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def _row_region(row: dict, roles: _Roles) -> Region:
    """Pick a region for the row, reusing an existing valid id-card region."""
    for f in roles.id_card:
        info = cn.parse_id_card(str(row.get(f.name, "")))
        if info is not None:
            return info.region
    return random_region()


def _assign_region_field(field: FieldSpec, region: Region) -> str:
    """Decide province/city/district level for a region field by its name."""
    name = field.name.lower()
    comment = (field.comment or "")
    blob = name + comment
    if any(k in blob for k in ("province", "sheng", "省")) or name in ("sf", "sfen"):
        return region.province
    if any(k in blob for k in ("district", "county", "区", "县")) or name in ("qx", "qux"):
        return region.district
    if any(k in blob for k in ("city", "shi", "市")) or name in ("cs", "csh"):
        return region.city
    # Unknown level: default to the most specific so it still reads like a place.
    return region.district


# --------------------------------------------------------------------------- #
# Main pass
# --------------------------------------------------------------------------- #

def apply_coherence(rows: list[dict[str, object]], fields: list[FieldSpec]) -> list[dict[str, object]]:
    """Rewrite related fields in-place so each row is internally consistent."""
    roles = detect_roles(fields)
    if not roles.active:
        return rows

    gender_fmt = {f.name: _detect_gender_format(f) for f in roles.gender}
    birth_fmt = {f.name: _detect_birth_format(f) for f in roles.birthdate}

    for row in rows:
        region = _row_region(row, roles)

        # 1. Identity bundle: id_card drives birth / gender / age.
        identity = None
        if roles.has_identity:
            # Seed gender/birth from any pre-generated values when reasonable,
            # otherwise let the generator choose; then make everything agree.
            identity = cn.generate_id_card(region=region)
            for f in roles.id_card:
                row[f.name] = identity.id_card
            for f in roles.birthdate:
                row[f.name] = identity.birthdate.strftime(birth_fmt[f.name])
            for f in roles.gender:
                male, female = gender_fmt[f.name]
                row[f.name] = male if identity.gender == "男" else female
            for f in roles.age:
                row[f.name] = _years_since(identity.birthdate)
            region = identity.region
        else:
            # No id card, but maybe age + birth still need to agree.
            if roles.birthdate and roles.age:
                start = date(1950, 1, 1).toordinal()
                end = date(2006, 12, 31).toordinal()
                birth = date.fromordinal(random.randint(start, end))
                for f in roles.birthdate:
                    row[f.name] = birth.strftime(birth_fmt[f.name])
                for f in roles.age:
                    row[f.name] = _years_since(birth)

        # 2. Region hierarchy: all region fields come from one real place.
        for f in roles.region:
            row[f.name] = _assign_region_field(f, region)

        # 3. Postal code follows the region.
        for f in roles.postal:
            row[f.name] = cn.generate_postal_code(region)

        # 4. Credit code shares the region; bank card is standalone Luhn.
        for f in roles.credit_code:
            row[f.name] = cn.generate_credit_code(region)
        for f in roles.bank_card:
            row[f.name] = cn.generate_bank_card()

    return rows
