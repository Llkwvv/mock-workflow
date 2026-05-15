import random
from datetime import datetime, timedelta
from decimal import Decimal

from faker import Faker

from mockagent.schemas.field import FieldSemantic, FieldSpec, SqlType

fake = Faker("zh_CN")


def generate_mock_rows(fields: list[FieldSpec], rows: int) -> list[dict[str, object]]:
    return [{field.name: _generate_value(field, index) for field in fields} for index in range(1, rows + 1)]


def preview_mock_rows(fields: list[FieldSpec], rows: int = 5) -> list[dict[str, object]]:
    return generate_mock_rows(fields, min(rows, 5))


def _generate_value(field: FieldSpec, index: int) -> object:
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
        start = datetime.now() - timedelta(days=365)
        return fake.date_time_between(start_date=start, end_date="now").strftime("%Y-%m-%d %H:%M:%S")
    if field.semantic == FieldSemantic.coordinate:
        lower, upper = (-90, 90) if "lat" in field.name.lower() or "纬度" in field.name else (-180, 180)
        return float(Decimal(str(random.uniform(lower, upper))).quantize(Decimal("0.000001")))
    if field.semantic == FieldSemantic.status:
        return random.choice(["active", "inactive", "pending"])
    if field.semantic == FieldSemantic.flag:
        return random.choice([0, 1])
    if field.type == SqlType.boolean:
        return random.choice([0, 1])
    if field.type == SqlType.int:
        return random.randint(1, 10000)
    if field.type == SqlType.decimal:
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
