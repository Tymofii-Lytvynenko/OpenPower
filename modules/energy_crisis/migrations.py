from __future__ import annotations

from typing import Any

import polars as pl

from modules.energy_crisis.schema import ENERGY_CRISIS_SCHEMA
from src.shared.migrations import SaveMigration


def _migrate_v1_to_v2(
    meta: dict[str, Any],
    tables: dict[str, pl.DataFrame],
) -> None:
    frame = tables.get("energy_crises", pl.DataFrame())
    for column_name, column in ENERGY_CRISIS_SCHEMA.columns.items():
        if column_name not in frame.columns:
            frame = frame.with_columns(
                pl.lit(column.default, dtype=column.dtype).alias(column_name)
            )
    tables["energy_crises"] = frame.select(list(ENERGY_CRISIS_SCHEMA.columns))
    meta.setdefault("schema_versions", {})["energy_crisis"] = 1


ENERGY_CRISIS_SAVE_MIGRATIONS = (
    SaveMigration(
        from_version=1,
        to_version=2,
        migrate=_migrate_v1_to_v2,
        owner="energy_crisis",
    ),
)
