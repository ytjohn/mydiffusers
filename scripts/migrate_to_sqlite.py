#!/usr/bin/env python3
"""Migrate existing runs to SQLite database."""
from pathlib import Path
from mydiffuser.client import database
from mydiffuser.utils.paths import read_json


def migrate():
    """Scan outputs/run directory and index all meta.json files to SQLite."""
    database.init_database()
    run_dir = Path("outputs/run")

    if not run_dir.exists():
        print("No runs directory found at outputs/run")
        return

    count = 0
    failed = 0

    print(f"Scanning {run_dir} for runs...")
    for run_path in run_dir.iterdir():
        if not run_path.is_dir():
            continue

        meta_file = run_path / "meta.json"
        if not meta_file.exists():
            print(f"  Skipping {run_path.name} (no meta.json)")
            failed += 1
            continue

        try:
            meta = read_json(meta_file)
            database.index_run(run_path.name, meta)
            count += 1
            print(f"  ✓ Indexed: {run_path.name}")
        except Exception as e:
            print(f"  ✗ Failed to index {run_path.name}: {e}")
            failed += 1

    print(f"\nMigration complete:")
    print(f"  Successfully indexed: {count} runs")
    if failed:
        print(f"  Failed/skipped: {failed} runs")


if __name__ == "__main__":
    migrate()
