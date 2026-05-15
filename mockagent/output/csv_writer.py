from pathlib import Path
import csv


def normalize_csv_path(csv_path: str) -> Path:
    return Path(csv_path)


def write_csv(rows: list[dict[str, object]], csv_path: str) -> Path:
    path = normalize_csv_path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path
