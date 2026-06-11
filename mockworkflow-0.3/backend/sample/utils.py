"""Shared utilities for sample file handling."""

from pathlib import Path

import chardet


def ensure_sample_file_exists(file_path: str) -> Path:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Sample file not found: {file_path}")
    return path


def detect_encoding(file_path: Path) -> str:
    """Detect file encoding, prioritizing Chinese encodings."""
    with open(file_path, "rb") as f:
        raw_data = f.read(1024)  # Read first 1KB for detection

    result = chardet.detect(raw_data)
    encoding = result.get("encoding", "utf-8")
    confidence = result.get("confidence", 0)

    # For Chinese files, try common encodings first
    chinese_encodings = ["gbk", "gb2312", "gb18030", "utf-8"]

    if confidence < 0.7:
        # Try to read with common Chinese encodings
        for enc in chinese_encodings:
            try:
                raw_data.decode(enc)
                return enc
            except (UnicodeDecodeError, LookupError):
                continue

    return encoding
