"""Excel sample reader (auto-registered)."""

from pathlib import Path

import pandas as pd

from backend.sample.registry import register_reader


@register_reader("xlsx")
@register_reader("xls")
def read_excel(path: Path) -> pd.DataFrame:
    return pd.read_excel(path)
