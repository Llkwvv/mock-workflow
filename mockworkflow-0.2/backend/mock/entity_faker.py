"""Entity fabrication: produce realistic-but-fake entity values.

For "test data" (not "fake/forged real data"), entity-like fields -- person
names, company names, institution names, addresses -- must **not** reuse the
real values from the sample.  Instead we detect the entity type from the column
name and the *shape* of the sample values, then generate brand-new values with
Faker that only preserve the recognisable format.

This is deliberately separate from frequency sampling (which is reserved for
non-sensitive domain vocabulary such as status codes and fixed template
phrases).
"""

from __future__ import annotations

import random
from typing import Callable

from faker import Faker

from backend.schemas.field import FieldSemantic, FieldSpec

fake = Faker("zh_CN")

# Suffixes that mark an organisation as a *company* -> use Faker company names.
_COMPANY_SUFFIXES = (
    "有限公司", "股份有限公司", "公司", "厂", "店", "中心", "集团",
    "事务所", "工作室", "合作社", "商行", "超市", "门市部", "经营部",
)

# Suffixes that mark a public/institutional organisation -> build a plausible
# institution name from fake geography + the learned suffix.
_INSTITUTION_SUFFIXES = (
    "人民法院", "法院", "人民检察院", "检察院", "公安局", "管理委员会",
    "委员会", "人民政府", "政府", "大学", "学院", "学校", "医院", "银行",
    "协会", "派出所", "办公室", "管理局", "税务局", "财政局", "教育局", "局",
)


def _is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def _matching_suffix(values: list[str], suffixes: tuple[str, ...]) -> str | None:
    """Return a suffix that the majority of values end with, longest first."""
    if not values:
        return None
    for suffix in sorted(suffixes, key=len, reverse=True):
        hits = sum(1 for v in values if v.endswith(suffix))
        if hits >= max(1, len(values) // 2):
            return suffix
    return None


def _looks_like_person_names(values: list[str]) -> bool:
    """All values are short (2-4 char) pure-CJK strings -> likely person names."""
    if not values:
        return False
    return all(2 <= len(v) <= 4 and all(_is_cjk(c) for c in v) for v in values)


def _build_institution_generator(values: list[str], suffix: str) -> Callable[[], str]:
    """Fabricate institution names: fake geography + learned suffix."""
    use_qu = any("区" in v for v in values)
    use_xian = any("县" in v for v in values)

    def generate() -> str:
        city = fake.city_name()
        if use_qu:
            return f"{city}市{fake.district()}区{suffix}"
        if use_xian:
            return f"{city}市{fake.city_name()}县{suffix}"
        return f"{city}市{suffix}"

    return generate


def build_entity_generator(field: FieldSpec) -> Callable[[int], object] | None:
    """Return a fabricating generator for entity-like fields, else ``None``.

    Detection is now config-driven via semantics.yaml.  Value-suffix inference
    (company vs institution vs person) is used as a secondary signal when the
    column name alone is ambiguous.
    """
    from backend.rules.semantics import SemanticRegistry

    name_lower = field.name.lower()
    values = [v for v in field.value_pool if v]
    registry = SemanticRegistry.get()
    matched = registry.match(field.name)
    semantic_name = matched.name if matched else None

    # --- Config-driven faker strategies (from semantics.yaml) --------------
    faker_strategy = matched.faker if matched else None

    if faker_strategy == "city_name":
        def _fabricate_region() -> str:
            return fake.city_name().replace("市", "").replace("区", "")
        return lambda index: _fabricate_region()

    if faker_strategy == "address":
        return lambda index: fake.address()

    if faker_strategy == "phone_number":
        return lambda index: fake.phone_number()

    if faker_strategy == "email":
        return lambda index: fake.email()

    if faker_strategy == "url":
        return lambda index: fake.url()

    if faker_strategy == "license_plate":
        return lambda index: fake.license_plate()

    # --- Person name --------------------------------------------------------
    is_person = semantic_name == "person_name"
    if is_person or name_lower.endswith("xm"):
        if values:
            has_org_suffix = (
                _matching_suffix(values, _COMPANY_SUFFIXES) is not None
                or _matching_suffix(values, _INSTITUTION_SUFFIXES) is not None
            )
            if not has_org_suffix and _looks_like_person_names(values):
                return lambda index: fake.name()
        if not values or _looks_like_person_names(values):
            return lambda index: fake.name()

    # --- Company / institution (from config or suffix inference) -----------
    is_company = semantic_name == "company_name"
    if is_company or faker_strategy == "company_name":
        if values:
            if _matching_suffix(values, _INSTITUTION_SUFFIXES) is not None:
                inst_suffix = _matching_suffix(values, _INSTITUTION_SUFFIXES)
                gen = _build_institution_generator(values, inst_suffix)
                return lambda index: gen()
            if _matching_suffix(values, _COMPANY_SUFFIXES) is not None:
                return lambda index: fake.company()
        return lambda index: fake.company()

    # --- Fallback: suffix-only detection when no semantic matched ----------
    if not semantic_name and values:
        has_org_suffix = (
            _matching_suffix(values, _COMPANY_SUFFIXES) is not None
            or _matching_suffix(values, _INSTITUTION_SUFFIXES) is not None
        )
        if not has_org_suffix and _looks_like_person_names(values):
            return lambda index: fake.name()
        if _matching_suffix(values, _INSTITUTION_SUFFIXES) is not None:
            inst_suffix = _matching_suffix(values, _INSTITUTION_SUFFIXES)
            gen = _build_institution_generator(values, inst_suffix)
            return lambda index: gen()
        if _matching_suffix(values, _COMPANY_SUFFIXES) is not None:
            return lambda index: fake.company()

    return None
