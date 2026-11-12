"""Engine-owned default migrations for persisted simulation state."""

from __future__ import annotations

import dataclasses
from typing import Any

from src.shared.determinism import DeterminismState
from src.shared.events import JournalState
from src.shared.migrations import SaveMigration


def _migrate_v1_to_v2(meta: dict[str, Any], _tables: dict[str, Any]) -> None:
    """Add deterministic runtime state and the durable journal to legacy saves."""

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
