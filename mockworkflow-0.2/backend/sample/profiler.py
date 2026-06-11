import pandas as pd

import numpy as np

from backend.sample.reader import read_sample_file
from backend.schemas.field import ColumnProfile, DistributionInfo, SampleProfile, SqlType
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

    # 直接按位置重命名列，避免 dict 去重导致重复列名映射丢失
    dataframe.columns = columns

    samples: dict[str, list[str]] = {}
    confidence: dict[str, float] = {}
    column_profiles: dict[str, ColumnProfile] = {}

    for column in columns:
        try:
            series = dataframe[column]
        except KeyError:
            # Column may have been dropped or renamed unexpectedly; skip it.
            continue
        # Guard: if duplicate column names remain, dataframe[column] returns DataFrame.
        if isinstance(series, pd.DataFrame):
            series = series.iloc[:, 0]
        non_null = series.dropna()
        sample_values = [str(value) for value in non_null.head(sample_size).tolist()]
        inferred_type, min_value, max_value, datetime_format, type_confidence = _infer_column_profile(series)
        unique_ratio = float(non_null.nunique() / len(non_null)) if len(non_null) else 0
        null_ratio = float(series.isna().mean()) if len(series) else 0
        samples[column] = sample_values
        confidence[column] = type_confidence

        # Distinct value -> count, capped to keep the profile lightweight
        value_frequency: dict[str, int] = {}
        for value in sample_values:
            value_frequency[value] = value_frequency.get(value, 0) + 1
        if len(value_frequency) > 500:
            top = sorted(value_frequency.items(), key=lambda kv: kv[1], reverse=True)[:500]
            value_frequency = dict(top)

        distribution = None
        if inferred_type in (SqlType.int, SqlType.decimal) and min_value is not None and max_value is not None:
            distribution = _infer_distribution(series)

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
            distribution=distribution,
            value_frequency=value_frequency,
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

    try:
        datetime_values = pd.to_datetime(non_null, errors="coerce", format="mixed")
        datetime_ratio = float(datetime_values.notna().mean())
        if datetime_ratio >= 0.8:
            return SqlType.datetime, None, None, "auto", datetime_ratio
    except ValueError:
        # e.g. "Mixed timezones detected" – treat as non-datetime
        pass

    average_length = non_null.astype(str).map(len).mean()
    if average_length > 255:
        return SqlType.text, None, None, None, 0.8
    return SqlType.varchar, None, None, None, 0.7


def _infer_distribution(series: pd.Series) -> DistributionInfo | None:
    """Fit common distributions to a numeric series and return the best match."""
    non_null = series.dropna()
    if len(non_null) < 10:
        return None

    numeric = pd.to_numeric(non_null, errors="coerce").dropna()
    if len(numeric) < 10:
        return None

    values = numeric.values.astype(float)
    if np.any(np.isinf(values)) or np.any(np.isnan(values)):
        return None

    # Normalize for comparison
    min_v, max_v = float(np.min(values)), float(np.max(values))
    if max_v == min_v:
        return None

    normalized = (values - min_v) / (max_v - min_v)

    distributions = {
        "uniform": _fit_uniform,
        "normal": _fit_normal,
        "lognormal": _fit_lognormal,
        "exponential": _fit_exponential,
    }

    best = DistributionInfo(type="uniform", params={"min": min_v, "max": max_v}, goodness_of_fit=0.0)
    best_score = 0.0

    for name, fitter in distributions.items():
        try:
            info = fitter(values, normalized)
            if info and info.goodness_of_fit > best_score:
                best = info
                best_score = info.goodness_of_fit
        except Exception:
            continue

    return best if best_score > 0.1 else None


def _ks_score(samples: np.ndarray, cdf_func) -> float:
    """Simple KS-like score: fraction of samples within expected CDF bins."""
    try:
        sorted_vals = np.sort(samples)
        expected = np.linspace(0, 1, len(sorted_vals))
        actual = np.array([cdf_func(v) for v in sorted_vals])
        # Use mean absolute difference as a proxy; lower is better, so invert
        mae = np.mean(np.abs(expected - actual))
        return max(0.0, 1.0 - mae * 2)
    except Exception:
        return 0.0


def _fit_uniform(values: np.ndarray, normalized: np.ndarray) -> DistributionInfo:
    min_v, max_v = float(np.min(values)), float(np.max(values))
    score = _ks_score(normalized, lambda x: x)
    return DistributionInfo(type="uniform", params={"min": min_v, "max": max_v}, goodness_of_fit=score)


def _fit_normal(values: np.ndarray, normalized: np.ndarray) -> DistributionInfo:
    mu, sigma = float(np.mean(values)), float(np.std(values))
    if sigma == 0:
        return DistributionInfo(type="normal", params={"mu": mu, "sigma": 0.001}, goodness_of_fit=0.0)
    score = _ks_score(normalized, lambda x: 0.5 * (1 + np.sign(x - 0.5) * np.sqrt(abs(x - 0.5) * 2)))
    return DistributionInfo(type="normal", params={"mu": mu, "sigma": sigma}, goodness_of_fit=score)


def _fit_lognormal(values: np.ndarray, normalized: np.ndarray) -> DistributionInfo:
    if np.any(values <= 0):
        return DistributionInfo(type="lognormal", params={}, goodness_of_fit=0.0)
    log_vals = np.log(values)
    mu, sigma = float(np.mean(log_vals)), float(np.std(log_vals))
    if sigma == 0:
        return DistributionInfo(type="lognormal", params={"mu": mu, "sigma": 0.001}, goodness_of_fit=0.0)
    score = _ks_score(normalized, lambda x: x)  # Simplified proxy
    return DistributionInfo(type="lognormal", params={"mu": mu, "sigma": sigma}, goodness_of_fit=score)


def _fit_exponential(values: np.ndarray, normalized: np.ndarray) -> DistributionInfo:
    if np.any(values <= 0):
        return DistributionInfo(type="exponential", params={}, goodness_of_fit=0.0)
    lam = 1.0 / float(np.mean(values))
    score = _ks_score(normalized, lambda x: 1 - np.exp(-lam * x))
    return DistributionInfo(type="exponential", params={"lambda": lam}, goodness_of_fit=score)
