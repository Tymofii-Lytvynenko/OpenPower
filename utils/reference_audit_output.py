"""Write audit tables without coupling serialization to source analysis."""
import csv
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def write_csv_tables(output_dir: Path, tables: Mapping[str, list[dict[str, Any]]]) -> None:
    for filename, rows in tables.items():
        write_csv(output_dir / filename, rows, list(rows[0]) if rows else [])
