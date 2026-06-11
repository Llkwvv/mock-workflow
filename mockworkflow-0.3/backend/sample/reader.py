import pandas as pd

from backend.sample.registry import get_reader, list_supported_formats
from backend.sample.utils import ensure_sample_file_exists


def read_sample_file(file_path: str) -> pd.DataFrame:
    """Read a sample file by looking up its suffix in the reader registry.

    The registry is populated automatically when ``backend.sample`` is imported,
    because all modules under ``backend.sample.readers`` are auto-discovered.
    """
    path = ensure_sample_file_exists(file_path)
    suffix = path.suffix.lower().lstrip(".")
    reader = get_reader(suffix)
    if reader is None:
        supported = ", ".join(list_supported_formats())
        raise ValueError(
            f"Unsupported sample file format: .{suffix}. Supported: {supported}"
        )
    return reader(path)