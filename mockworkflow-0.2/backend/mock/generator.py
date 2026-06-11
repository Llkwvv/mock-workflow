import random
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable

import numpy as np
from faker import Faker

from backend.mock import cn_identifiers as cn
from backend.mock.entity_faker import build_entity_generator
from backend.mock.frequency_sampler import build_frequency_sampler
from backend.mock.markov_generator import build_markov_generator
from backend.mock.template_engine import build_template_generator, looks_structured
from backend.schemas.field import DistributionInfo, FieldSemantic, FieldSpec, SqlType

DEFAULT_PREVIEW_ROWS = 5

fake = Faker("zh_CN")

# Semantics for which a Faker generator is preferred over learning from the
# sample values.  Note: company_name and text are intentionally excluded so
# that organisation names, descriptions, etc. are learned from real data.
_FAKER_PRIORITY_SEMANTICS = {
    FieldSemantic.license_plate,
    FieldSemantic.phone_number,
    FieldSemantic.email,
    FieldSemantic.url,
    FieldSemantic.vehicle_model,
    FieldSemantic.direction,
}


def _resolve_column_distribution(field: FieldSpec) -> DistributionInfo | None:
    """Look for distribution info stored in field.comment or external source.

    Currently checks if the field itself carries a ``distribution`` attribute
    injected by the profiler (future enhancement).  For now we rely on the
    column profile being attached to the generation context outside this module.
    """
    # Placeholder: distribution will be injected via field-level metadata
    # when profiler + generation pipeline are fully wired.
    return None


def _sample_from_distribution(dist: DistributionInfo) -> float:
    """Sample a single value from a fitted distribution."""
    dtype = dist.type
    params = dist.params
    if dtype == "normal":
        return float(np.random.normal(params.get("mu", 0), params.get("sigma", 1)))
    if dtype == "lognormal":
        return float(np.random.lognormal(params.get("mu", 0), params.get("sigma", 1)))
    if dtype == "exponential":
        return float(np.random.exponential(1.0 / params.get("lambda", 1)))
    if dtype == "uniform":
        return float(np.random.uniform(params.get("min", 0), params.get("max", 1)))
    return float(np.random.uniform(params.get("min", 0), params.get("max", 1)))


def generate_mock_rows(fields: list[FieldSpec], rows: int) -> list[dict[str, object]]:
    # Build each field's value generator ONCE (compiling Markov/template models
    # a single time) then reuse it across all rows for efficiency.
    generators: dict[str, Callable[[int], object]] = {
        field.name: _build_field_generator(field) for field in fields
    }
    rows_data = [
        {field.name: generators[field.name](index) for field in fields}
        for index in range(1, rows + 1)
    ]
    # Cross-field coherence: make derived fields (id_card -> birth/gender/age,
    # province/city/district hierarchy, postal/credit code by region) agree.
    from backend.mock.coherence import apply_coherence
    rows_data = apply_coherence(rows_data, fields)

    # Apply cross-field comparison constraints (start < end, subtotal <= total).
    if any(field.constraints for field in fields):
        from backend.mock.constraint_engine import apply_constraints
        rows_data = apply_constraints(rows_data, fields)
    return rows_data


def preview_mock_rows(fields: list[FieldSpec], rows: int = 5) -> list[dict[str, object]]:
    return generate_mock_rows(fields, min(rows, 5))


def _build_field_generator(field: FieldSpec) -> Callable[[int], object]:
    """Return a closure ``(index) -> value`` implementing the layered strategy.

    Strict mode: the ONLY path that reuses real sample values is the enum path
    (domain vocabulary such as status codes / fixed phrases).  Every other field
    is fabricated, so no real entity or free-text value is ever reproduced.

    Layer order:
      0. All-empty column               -> reproduce blanks
      1. Identity / auto-increment      -> row index
      2. Datetime                       -> randomised within learned date range
      3. Boolean / flag                 -> 0 / 1
      4. Numeric / coordinate           -> fabricated within learned bounds
      5. High-value Faker semantics     -> plate / phone / email / url / ...
      6. Entity fabrication             -> person / company / institution / addr
      7. Structured identifiers         -> template with random digits
      8. ENUM values (only reuse path)  -> domain vocabulary, frequency-weighted
      9. Non-enum free text             -> Markov fabrication (never a copy)
     10. Column-name heuristics         -> faker by column name
     11. Last resort                    -> synthetic short sentence
    """
    # 0. All-empty column in the sample -> faithfully reproduce blanks.
    if field.value_frequency and not [v for v in field.value_pool if v != ""]:
        if all(k == "" for k in field.value_frequency):
            return lambda index: ""

    # 1. Identity
    if field.auto_increment or field.semantic == FieldSemantic.id:
        return lambda index: index

    # 1b. Chinese domain identifiers with real checksums.  These also work
    #     standalone; when grouped with related fields the coherence pass
    #     overwrites them to keep the whole row consistent.
    cn_gen = _build_cn_identifier_generator(field)
    if cn_gen is not None:
        return cn_gen

    # 2. Datetime / birthdate -> randomised within the learned date range.
    if (
        field.semantic in (FieldSemantic.time, FieldSemantic.birthdate)
        or field.type == SqlType.datetime
    ):
        return _build_datetime_generator(field)

    # 3. Boolean / flag
    if field.type == SqlType.boolean or field.semantic in (FieldSemantic.boolean, FieldSemantic.flag):
        return lambda index: random.choice([0, 1])

    # 4. Numeric / coordinate -> fabricated within learned bounds.
    if field.semantic == FieldSemantic.coordinate:
        return _build_coordinate_generator(field)
    if field.type == SqlType.int or field.type == SqlType.decimal:
        return _build_numeric_generator(field)

    # 5. High-value Faker semantics (plate / phone / email / url / ...).
    if field.semantic in _FAKER_PRIORITY_SEMANTICS:
        return _build_faker_semantic_generator(field)

    # 6. ENTITY FABRICATION (takes priority over reuse!).  Person names,
    #    companies, institutions and addresses are regenerated with Faker so no
    #    real entity from the sample is ever reproduced -- even if the column has
    #    only a few distinct values.
    entity_gen = build_entity_generator(field)
    if entity_gen is not None:
        return entity_gen

    pool = [v for v in field.value_pool if v != ""]

    # 7. Structured identifiers (case numbers, codes) -> format-preserving
    #    fabrication with fully random digits.
    if pool and looks_structured(pool):
        tmpl = build_template_generator(pool)
        if tmpl:
            return lambda index: tmpl()

    # 8. Enum values (domain vocabulary: status / category / fixed phrases).
    #    This is the ONLY path permitted to reuse real sample values, weighted
    #    by their real frequency.  It is restricted strictly to the detected
    #    enum set (plus blanks) and NEVER reuses arbitrary pool values, so no
    #    non-enum real value can ever be emitted.
    if field.enum_values:
        enum_set = set(field.enum_values)
        freq = {
            k: v for k, v in field.value_frequency.items()
            if k in enum_set or k == ""
        }
        sampler = build_frequency_sampler(
            freq, fallback_values=field.enum_values, keep_empty=True
        )
        if sampler:
            return lambda index: sampler()
        return lambda index: random.choice(field.enum_values)

    # 9. Non-enum free text -> Markov-fabricated lookalikes that are NEVER exact
    #    copies of any sample; if fabrication fails, emit a synthetic sentence.
    #    No real value is ever reused here.
    if pool:
        markov = build_markov_generator(pool)
        if markov:
            return lambda index: markov() or fake.sentence(nb_words=4)

    # 10. Column-name heuristics when no usable sample values.
    name_lower = field.name.lower()
    if field.semantic == FieldSemantic.company_name:
        return lambda index: fake.company()
    if any(keyword in name_lower for keyword in ("phone", "mobile")) or "手机" in field.name:
        return lambda index: fake.phone_number()
    if any(keyword in name_lower for keyword in ("email", "mail")) or "邮箱" in field.name:
        return lambda index: fake.email()
    if "姓名" in field.name or "name" in name_lower or name_lower.endswith("xm"):
        return lambda index: fake.name()
    if "地址" in field.name or "address" in name_lower:
        return lambda index: fake.address()

    # 11. Last resort: a synthetic short sentence (never a real sample value).
    return lambda index: fake.sentence(nb_words=4)


def _build_cn_identifier_generator(field: FieldSpec) -> Callable[[int], object] | None:
    """Return a checksum-valid generator for Chinese domain identifiers, else None."""
    semantic = field.semantic
    if semantic == FieldSemantic.id_card:
        return lambda index: cn.generate_id_card().id_card
    if semantic == FieldSemantic.credit_code:
        return lambda index: cn.generate_credit_code()
    if semantic == FieldSemantic.bank_card:
        return lambda index: cn.generate_bank_card()
    if semantic == FieldSemantic.postal_code:
        return lambda index: cn.generate_postal_code()
    if semantic == FieldSemantic.gender:
        from backend.mock.coherence import _detect_gender_format
        male, female = _detect_gender_format(field)
        return lambda index: random.choice([male, female])
    return None


def _build_faker_semantic_generator(field: FieldSpec) -> Callable[[int], object]:
    semantic = field.semantic
    if semantic == FieldSemantic.license_plate:
        return lambda index: fake.license_plate()
    if semantic == FieldSemantic.vehicle_model:
        return lambda index: random.choice(["新桑塔纳", "新捷达", "悦动", "凯美瑞", "轩逸"])
    if semantic == FieldSemantic.direction:
        return lambda index: random.randint(0, 360)
    if semantic == FieldSemantic.phone_number:
        return lambda index: fake.phone_number()
    if semantic == FieldSemantic.email:
        return lambda index: fake.email()
    if semantic == FieldSemantic.url:
        return lambda index: fake.url()
    return lambda index: fake.word()


def _build_coordinate_generator(field: FieldSpec) -> Callable[[int], object]:
    is_lat = "lat" in field.name.lower() or "纬度" in field.name
    lower, upper = (-90, 90) if is_lat else (-180, 180)
    if field.min_value is not None and field.max_value is not None and field.max_value > field.min_value:
        lower, upper = field.min_value, field.max_value

    def generate(index: int) -> object:
        return float(Decimal(str(random.uniform(lower, upper))).quantize(Decimal("0.000001")))

    return generate


def _infer_decimal_places(values: list[str], default: int = 2, cap: int = 10) -> int:
    """Infer the number of decimal places to keep from the real sample values.

    e.g. coordinates like "116.346186" -> 6 dp, temperatures like "36.5" -> 1.
    Falls back to ``default`` when no fractional sample value is available.
    """
    places = 0
    found = False
    for value in values:
        text = str(value).strip()
        if "." not in text:
            continue
        frac = text.rsplit(".", 1)[1]
        if frac.isdigit():
            found = True
            places = max(places, len(frac.rstrip("0")) or 1)
    if not found:
        return default
    return min(places, cap)


def _build_numeric_generator(field: FieldSpec) -> Callable[[int], object]:
    dist = field.distribution or _resolve_column_distribution(field)
    is_int = field.type == SqlType.int
    has_range = (
        field.min_value is not None
        and field.max_value is not None
        and field.max_value >= field.min_value
    )
    # Preserve the real decimal precision of the column (e.g. 6 dp for
    # coordinates) instead of always truncating to 2 dp.
    quant = Decimal(1).scaleb(-_infer_decimal_places(field.value_pool)) if not is_int else None

    def _round(raw: float) -> float:
        return float(Decimal(str(raw)).quantize(quant))

    def generate(index: int) -> object:
        if dist:
            raw = _sample_from_distribution(dist)
            return int(raw) if is_int else _round(raw)
        if has_range:
            if is_int:
                return random.randint(int(field.min_value), int(field.max_value))
            return _round(random.uniform(field.min_value, field.max_value))
        if is_int:
            return random.randint(1, 10000)
        return _round(random.uniform(1, 10000))

    return generate


def _build_datetime_generator(field: FieldSpec) -> Callable[[int], object]:
    """Generate datetimes within the date range observed in the sample."""
    parsed: list[datetime] = []
    has_time_component = False
    for value in field.value_pool:
        dt = _try_parse_datetime(value)
        if dt is not None:
            parsed.append(dt)
            if ":" in value:
                has_time_component = True

    fmt = "%Y-%m-%d %H:%M:%S" if has_time_component else "%Y-%m-%d"

    if len(parsed) >= 2:
        start = min(parsed)
        end = max(parsed)
        if end <= start:
            end = start + timedelta(days=1)

        def generate(index: int) -> object:
            return fake.date_time_between(start_date=start, end_date=end).strftime(fmt)

        return generate

    # Fallback: last 365 days.
    default_start = datetime.now() - timedelta(days=365)

    def generate_default(index: int) -> object:
        return fake.date_time_between(start_date=default_start, end_date="now").strftime(fmt)

    return generate_default


def _try_parse_datetime(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None
