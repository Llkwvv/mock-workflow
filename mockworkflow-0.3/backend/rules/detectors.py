def is_probable_id_column(column_name: str) -> bool:
    normalized = column_name.lower()
    return normalized == "id" or normalized.endswith("_id")
