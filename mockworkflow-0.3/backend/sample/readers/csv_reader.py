"""CSV sample reader (auto-registered)."""

from pathlib import Path

import pandas as pd

from backend.sample.registry import register_reader
from backend.sample.utils import detect_encoding


@register_reader("csv")
def read_csv(path: Path) -> pd.DataFrame:
    encoding = detect_encoding(path)
    return pd.read_csv(path, encoding=encoding)
