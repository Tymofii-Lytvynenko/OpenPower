from __future__ import annotations

import dataclasses
from typing import Any

import polars as pl

from src.shared.determinism import DeterminismState
from src.shared.events import JournalState
from src.shared.migrations import SaveMigration


def _migrate_v1_to_v2(
    meta: dict[str, Any],
    tables: dict[str, pl.DataFrame],
) -> None:
    # Version 2 makes deterministic runtime state and the durable journal
    # explicit. Existing saves receive deterministic defaults.
    meta.setdefault("determinism", dataclasses.asdict(DeterminismState()))
    meta.setdefault("journal", dataclasses.asdict(JournalState()))
    meta.setdefault("schema_versions", {})


CORE_SAVE_MIGRATIONS = (
    SaveMigration(
        from_version=1,
        to_version=2,
        migrate=_migrate_v1_to_v2,
        owner="core",
    ),
)
