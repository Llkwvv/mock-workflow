from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class SqlType(StrEnum):
    varchar = "VARCHAR"
    int = "INT"
    decimal = "DECIMAL"
    datetime = "DATETIME"
    text = "TEXT"
    boolean = "BOOLEAN"


class FieldSemantic(StrEnum):
    id = "id"
    time = "time"
    coordinate = "coordinate"
    status = "status"
    flag = "flag"
    text = "text"
    license_plate = "license_plate"
    company_name = "company_name"
    vehicle_model = "vehicle_model"
    direction = "direction"
    phone_number = "phone_number"
    email = "email"
    url = "url"
    unknown = "unknown"


class ColumnProfile(BaseModel):
    name: str
    samples: list[str] = Field(default_factory=list)
    null_ratio: float = Field(default=0, ge=0, le=1)
    unique_ratio: float = Field(default=0, ge=0, le=1)
    inferred_type: SqlType | None = None
    min_value: float | None = None
    max_value: float | None = None
    datetime_format: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)


class FieldSpec(BaseModel):
    name: str = Field(min_length=1)
    type: SqlType
    length: int | None = Field(default=None, gt=0)
    precision: int | None = Field(default=None, gt=0)
    scale: int | None = Field(default=None, ge=0)
    nullable: bool = True
    primary_key: bool = False
    auto_increment: bool = False
    comment: str | None = None
    semantic: FieldSemantic = FieldSemantic.unknown
    enum_values: list[str] = Field(default_factory=list)
    value_pool: list[str] = Field(default_factory=list)
    uncertain: bool = False
    confidence: float | None = Field(default=None, ge=0, le=1)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class SampleProfile(BaseModel):
    file_path: str
    columns: list[str] = Field(default_factory=list)
    samples: dict[str, list[str]] = Field(default_factory=dict)
    row_count: int = Field(default=0, ge=0)
    confidence: dict[str, float] = Field(default_factory=dict)
    column_profiles: dict[str, ColumnProfile] = Field(default_factory=dict)


class TableSpec(BaseModel):
    table_name: str = Field(default="auto_table", min_length=1)
    fields: list[FieldSpec] = Field(default_factory=list)
    dialect: str = "mysql"

    @field_validator("dialect")
    @classmethod
    def only_mysql(cls, value: str) -> str:
        normalized = value.lower()
        if normalized != "mysql":
            raise ValueError("Only mysql dialect is supported in MVP")
        return normalized
