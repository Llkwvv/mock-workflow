#!/usr/bin/env python3
"""Batch-generate table configs for all non-empty SQL files in tzsz directory."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import get_settings
from backend.sample.profiler import analyze_sample_file
from backend.rules.engine import RuleEngine
from backend.rules import RuleStore
from backend.schemas.field import FieldSemantic


def main() -> None:
    base_dir = Path("samples/tzsz/tzsz")
    sql_files = sorted(
        f for f in base_dir.glob("*.sql")
        if f.stat().st_size > 0 and f.stat().st_size < 5 * 1024 * 1024
    )

    settings = get_settings()
    store = RuleStore(settings.rules_file)

    total = len(sql_files)
    success = 0
    skipped_numeric = 0
    failed = 0
    unknown_cols = []
    updated_rules = 0

    print(f"Processing {total} SQL files (skipping empty and >5MB)...")

    for i, fpath in enumerate(sql_files, 1):
        try:
            profile = analyze_sample_file(str(fpath))
            fields = RuleEngine().infer_fields(profile)
            # Persist all inferred fields to rule store (bypass min-confidence gate)
            for field in fields:
                store.upsert_fields([field], min_confidence=0.0, source="rule_engine")
                updated_rules += 1
                if field.semantic == FieldSemantic.unknown:
                    unknown_cols.append((fpath.name, field.name))
            success += 1
        except Exception as exc:
            failed += 1
            print(f"  [{i}/{total}] FAIL {fpath.name}: {exc}")
            continue

        if i % 100 == 0:
            print(f"  [{i}/{total}] processed...")

    print(f"\nBatch generation complete:")
    print(f"  Total files: {total}")
    print(f"  Success: {success}")
    print(f"  Skipped (numeric columns): {skipped_numeric}")
    print(f"  Failed: {failed}")
    print(f"  Rules updated: {updated_rules}")
    print(f"  Unknown semantic columns: {len(unknown_cols)}")
    if unknown_cols:
        print("  Sample unknown columns (add keywords to semantics.yaml to improve):")
        for fname, colname in unknown_cols[:30]:
            print(f"    {fname}: {colname}")


if __name__ == "__main__":
    main()
