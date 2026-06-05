import pandas as pd

from backend.sample.reader import read_sample_file
from backend.schemas.field import ColumnProfile, SampleProfile, SqlType
from backend.utils.pinyin import to_pinyin_initials


def create_empty_profile(file_path: str) -> SampleProfile:
    return SampleProfile(file_path=file_path)


def analyze_sample_file(file_path: str, sample_size: int = 500) -> SampleProfile:
    dataframe = read_sample_file(file_path)
    return profile_dataframe(dataframe, file_path=file_path, sample_size=sample_size)


def profile_dataframe(dataframe: pd.DataFrame, file_path: str, sample_size: int = 500) -> SampleProfile:
    if len(dataframe) == 0 or len(dataframe.columns) == 0:
        raise ValueError(f"Sample file has no data rows: {file_path}")

    # 跳过没有有效字段名的列（空列名或 Unnamed: X 这样的默认列名）
    valid_columns = []
    for column in dataframe.columns:
        col_str = str(column).strip()
        # 跳过空列名
        if not col_str:
            continue
        # 跳过 pandas 默认的 Unnamed 列
        if col_str.startswith('Unnamed:'):
            continue
        valid_columns.append(column)

    if not valid_columns:
        raise ValueError(f"Sample file has no valid column names: {file_path}")

    # 只保留有效列
    dataframe = dataframe[valid_columns]

    # 处理已知的中文列名
    original_columns = [str(column) for column in dataframe.columns]
    pinyin_columns = []
    for column in dataframe.columns:
        col_str = str(column)
        # Preserve known Chinese column names
        if col_str in ['姓名', '名字', '手机号', '电话', '邮箱']:
            pinyin_columns.append(col_str)
        else:
            pinyin_columns.append(to_pinyin_initials(col_str))

    # 处理重复字段名，添加序号
    columns = []
    seen = {}
    for col in pinyin_columns:
        if col in seen:
            seen[col] += 1
            columns.append(f"{col}{seen[col]}")
        else:
            seen[col] = 0
            columns.append(col)

    # 建立原始列名到新列名的映射
    column_mapping = dict(zip(original_columns, columns))

    # 重命名 DataFrame 的列
    dataframe = dataframe.rename(columns=column_mapping)
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
