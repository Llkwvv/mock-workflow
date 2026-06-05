from pathlib import Path
import xml.etree.ElementTree as ET

import pandas as pd
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


def read_rdf_file(path: Path, sample_size: int = 500) -> pd.DataFrame:
    """Read RDF/XML file and convert to DataFrame using streaming parse.

    Each rdf:Description becomes a row, dt:XXX properties become columns.
    Uses stratified sampling to improve schema detection from large files.

    Args:
        path: Path to the RDF file
        sample_size: Number of records to sample for analysis
    """
    records = []
    total_count = 0

    try:
        # Estimate sampling step based on file size
        with open(path, 'rb') as f:
            file_size = f.seek(0, 2)  # Get file size
            # For very large files, we'll sample less frequently
            if file_size > 100_000_000:  # 100MB
                sample_step = max(1, file_size // (sample_size * 100))
            else:
                sample_step = None
    except Exception as e:
        print(f"Error getting file size: {e}")
        sample_step = None

    # Use string path for iterparse to avoid potential Path issues
    path_str = str(path)

    # Stream parse with sampling
    for event, elem in ET.iterparse(path_str, events=("end",)):
        if elem.tag == "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description":
            # Sample based on record count for large files
            if sample_step is None or total_count % sample_step == 0:
                record = {}
                for child in elem:
                    # Extract field name from tag (handle namespace)
                    tag = child.tag
                    if "}" in tag:
                        tag = tag.split("}")[1]  # Remove namespace
                    if "#" in tag:
                        tag = tag.split("#")[1]

                    # Only include data fields (skip rdf:about, etc.)
                    if not tag.startswith("rdf"):
                        record[tag] = child.text or ""

                if record:
                    records.append(record)
                    if len(records) >= sample_size:
                        break

            total_count += 1
            elem.clear()  # Free memory

    if not records:
        raise ValueError("No valid records found in RDF file")

    return pd.DataFrame.from_records(records)


def read_sample_file(file_path: str) -> pd.DataFrame:
    path = ensure_sample_file_exists(file_path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        encoding = detect_encoding(path)
        return pd.read_csv(path, encoding=encoding)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".json":
        return pd.read_json(path)
    if suffix == ".rdf":
        return read_rdf_file(path)
    raise ValueError(f"Unsupported sample file format: {suffix}")