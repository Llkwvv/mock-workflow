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
    boolean = "boolean"
    text = "text"
    license_plate = "license_plate"
    company_name = "company_name"
    vehicle_model = "vehicle_model"
    direction = "direction"
    phone_number = "phone_number"
    email = "email"
    url = "url"
    unknown = "unknown"


class DistributionInfo(BaseModel):
    """Statistical distribution fitted to a numeric column."""

    type: str = Field(default="uniform", description="uniform | normal | lognormal | exponential | poisson")
    params: dict[str, float] = Field(default_factory=dict, description="Distribution parameters (mu, sigma, lambda, etc.)")
    goodness_of_fit: float = Field(default=0.0, ge=0, le=1, description="KS test p-value or similar score")


class TemporalTrendInfo(BaseModel):
    """Detected temporal trend for time-series columns."""

    slope: float = 0.0
    has_seasonality: bool = False
    period_seconds: float | None = None
    direction: str = "flat"  # up | down | flat


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
    distribution: DistributionInfo | None = None
    temporal_trend: TemporalTrendInfo | None = None


class ConstraintSpec(BaseModel):
    """Cross-field constraint expressed as a DSL string."""

    expression: str = Field(min_length=1, description="DSL expression, e.g. 'start_time < end_time'")
    fields: list[str] = Field(default_factory=list, description="Field names involved in this constraint")
    confidence: float = Field(default=0.5, ge=0, le=1, description="Confidence that this constraint holds")


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
    constraints: list[ConstraintSpec] = Field(default_factory=list)
    distribution: DistributionInfo | None = None
    temporal_trend: TemporalTrendInfo | None = None

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
