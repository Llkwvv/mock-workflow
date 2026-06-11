import random
from datetime import datetime, timedelta
from decimal import Decimal

import numpy as np
from faker import Faker

from backend.schemas.field import DistributionInfo, FieldSemantic, FieldSpec, SqlType

fake = Faker("zh_CN")


def _resolve_column_distribution(field: FieldSpec) -> DistributionInfo | None:
    """Look for distribution info attached to the field by the profiler."""
    return field.distribution


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


def generate_mock_rows(
    fields: list[FieldSpec],
    rows: int,
    pii_map: dict[str, str] | None = None,
    seed: int | None = None,
) -> list[dict[str, object]]:
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)
        fake.seed_instance(seed)
    # Phase 2 #5: pre-generate trend-driven datetime columns in batch
    from backend.mock.trend_sampler import sample_trend_datetime
    trend_cache: dict[str, list[str]] = {}
    for field in fields:
        if field.temporal_trend and (field.semantic == FieldSemantic.time or field.type == SqlType.datetime):
            trend_cache[field.name] = sample_trend_datetime(rows, field.temporal_trend)

    rows_data = [
        {field.name: _generate_value(field, index, trend_cache.get(field.name)) for field in fields}
        for index in range(1, rows + 1)
    ]
    # Apply cross-field constraints if any field has them
    if any(field.constraints for field in fields):
        from backend.mock.constraint_engine import apply_constraints
        rows_data = apply_constraints(rows_data, fields)
    # Phase 2 #6: apply PII anonymization if requested
    if pii_map:
        from backend.mock.anonymizer import anonymize_value
        for row in rows_data:
            for col_name, pii_type in pii_map.items():
                if col_name in row:
                    row[col_name] = anonymize_value(row[col_name], pii_type)
    return rows_data


def preview_mock_rows(fields: list[FieldSpec], rows: int = 5, seed: int | None = None) -> list[dict[str, object]]:
    return generate_mock_rows(fields, min(rows, 5), seed=seed)


def _generate_value(field: FieldSpec, index: int, trend_values: list[str] | None = None) -> object:
    # Phase 3 #18: check custom generators first
    from backend.agent.tools.code_gen import load_custom_generators
    custom_generators = load_custom_generators()
    safe_name = field.name.replace(" ", "_").replace("-", "_")
    custom_fn = custom_generators.get(f"generate_{safe_name}")
    if not custom_fn:
        # Try normalized name
        custom_fn = custom_generators.get(f"generate_{field.name.lower()}")
    if custom_fn:
        try:
            return custom_fn(index)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Custom generator for %s failed: %s, falling back", field.name, e)

    if field.auto_increment or field.semantic == FieldSemantic.id:
        return index
    if field.enum_values:
        return random.choice(field.enum_values)
    if field.value_pool:
        return random.choice(field.value_pool)
    if field.semantic == FieldSemantic.license_plate:
        return fake.license_plate()
    if field.semantic == FieldSemantic.company_name:
        return fake.company()
    if field.semantic == FieldSemantic.vehicle_model:
        return random.choice(["新桑塔纳", "新捷达", "悦动", "凯美瑞", "轩逸"])
    if field.semantic == FieldSemantic.direction:
        return random.randint(0, 360)
    if field.semantic == FieldSemantic.phone_number:
        return fake.phone_number()
    if field.semantic == FieldSemantic.email:
        return fake.email()
    if field.semantic == FieldSemantic.url:
        return fake.url()
    if field.semantic == FieldSemantic.time or field.type == SqlType.datetime:
        if trend_values and index <= len(trend_values):
            return trend_values[index - 1]
        start = datetime.now() - timedelta(days=365)
        return fake.date_time_between(start_date=start, end_date="now").strftime("%Y-%m-%d %H:%M:%S")
    if field.semantic == FieldSemantic.coordinate:
        lower, upper = (-90, 90) if "lat" in field.name.lower() or "纬度" in field.name else (-180, 180)
        return float(Decimal(str(random.uniform(lower, upper))).quantize(Decimal("0.000001")))
    if field.semantic == FieldSemantic.status:
        return random.choice(["active", "inactive", "pending"])
    if field.semantic == FieldSemantic.flag:
        return random.choice([0, 1])
    if field.semantic == FieldSemantic.boolean:
        return random.choice([0, 1])
    if field.type == SqlType.boolean:
        return random.choice([0, 1])
    if field.type == SqlType.int:
        dist = _resolve_column_distribution(field)
        if dist:
            return int(_sample_from_distribution(dist))
        return random.randint(1, 10000)
    if field.type == SqlType.decimal:
        dist = _resolve_column_distribution(field)
        if dist:
            raw = _sample_from_distribution(dist)
            return float(Decimal(str(raw)).quantize(Decimal("0.01")))
        return float(Decimal(str(random.uniform(1, 10000))).quantize(Decimal("0.01")))
    if field.type == SqlType.text:
        return fake.text(max_nb_chars=200)
    if any(keyword in field.name.lower() for keyword in ("phone", "mobile")) or "手机" in field.name:
        return fake.phone_number()
    if any(keyword in field.name.lower() for keyword in ("email", "mail")) or "邮箱" in field.name:
        return fake.email()
    if "姓名" in field.name or "name" in field.name.lower():
        return fake.name()
    if "地址" in field.name or "address" in field.name.lower():
        return fake.address()
    return fake.word()
