import pandas as pd

from mockagent.sample.reader import read_sample_file
from mockagent.schemas.field import ColumnProfile, SampleProfile, SqlType


def create_empty_profile(file_path: str) -> SampleProfile:
    return SampleProfile(file_path=file_path)


def analyze_sample_file(file_path: str, sample_size: int = 500) -> SampleProfile:
    dataframe = read_sample_file(file_path)
    return profile_dataframe(dataframe, file_path=file_path, sample_size=sample_size)


def profile_dataframe(dataframe: pd.DataFrame, file_path: str, sample_size: int = 500) -> SampleProfile:
    columns = [str(column) for column in dataframe.columns]
    samples: dict[str, list[str]] = {}
    confidence: dict[str, float] = {}
    column_profiles: dict[str, ColumnProfile] = {}

    for column in columns:
        series = dataframe[column]
        non_null = series.dropna()
        sample_values = [str(value) for value in non_null.head(sample_size).tolist()]
        inferred_type, min_value, max_value, datetime_format, type_confidence = _infer_column_profile(series)
        unique_ratio = float(non_null.nunique() / len(non_null)) if len(non_null) else 0
        null_ratio = float(series.isna().mean()) if len(series) else 0
        samples[column] = sample_values
        confidence[column] = type_confidence
        column_profiles[column] = ColumnProfile(
            name=column,
            samples=sample_values,
            null_ratio=null_ratio,
            unique_ratio=unique_ratio,
            inferred_type=inferred_type,
            min_value=min_value,
            max_value=max_value,
            datetime_format=datetime_format,
            confidence=type_confidence,
        )

    return SampleProfile(
        file_path=file_path,
        columns=columns,
        samples=samples,
        row_count=len(dataframe),
        confidence=confidence,
        column_profiles=column_profiles,
    )


def _infer_column_profile(series: pd.Series) -> tuple[SqlType, float | None, float | None, str | None, float]:
    non_null = series.dropna()
    if non_null.empty:
        return SqlType.varchar, None, None, None, 0.2

    numeric = pd.to_numeric(non_null, errors="coerce")
    numeric_ratio = float(numeric.notna().mean())
    if numeric_ratio >= 0.9:
        valid_numeric = numeric.dropna()
        min_value = float(valid_numeric.min()) if not valid_numeric.empty else None
        max_value = float(valid_numeric.max()) if not valid_numeric.empty else None
        is_integer_like = bool((valid_numeric % 1 == 0).all()) if not valid_numeric.empty else False
        if is_integer_like:
            return SqlType.int, min_value, max_value, None, numeric_ratio
        return SqlType.decimal, min_value, max_value, None, numeric_ratio

    datetime_values = pd.to_datetime(non_null, errors="coerce", format="mixed")
    datetime_ratio = float(datetime_values.notna().mean())
    if datetime_ratio >= 0.8:
        return SqlType.datetime, None, None, "auto", datetime_ratio

    average_length = non_null.astype(str).map(len).mean()
    if average_length > 255:
        return SqlType.text, None, None, None, 0.8
    return SqlType.varchar, None, None, None, 0.7
