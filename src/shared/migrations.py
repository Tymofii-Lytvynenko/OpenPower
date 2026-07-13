from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

import polars as pl


SAVE_FORMAT_VERSION = 2
MigrationFunc = Callable[[dict[str, Any], dict[str, pl.DataFrame]], None]


@dataclass(frozen=True)
class SaveMigration:
    from_version: int
    to_version: int
    migrate: MigrationFunc
    owner: str = "core"

    def __post_init__(self) -> None:
        if self.to_version != self.from_version + 1:
            raise ValueError("Save migrations must advance exactly one version.")


class MigrationRegistry:
    def __init__(self, migrations: Iterable[SaveMigration] = ()):
        self._migrations: dict[int, list[SaveMigration]] = {}
        for migration in migrations:
            self.register(migration)

    def register(self, migration: SaveMigration) -> None:
        migrations = self._migrations.setdefault(migration.from_version, [])
        if any(existing.owner == migration.owner for existing in migrations):
            raise RuntimeError(
                f"Duplicate save migration from version {migration.from_version} "
                f"for owner '{migration.owner}'."
            )
        migrations.append(migration)
        migrations.sort(key=lambda item: item.owner)

    def migrate(
        self,
        meta: dict[str, Any],
        tables: dict[str, pl.DataFrame],
        target_version: int = SAVE_FORMAT_VERSION,
    ) -> None:
        version = int(meta.get("version", 1))
        if version > target_version:
            raise RuntimeError(
                f"Save format {version} is newer than supported format {target_version}."
            )
        while version < target_version:
            migrations = self._migrations.get(version)
            if not migrations:
                raise RuntimeError(
                    f"No save migration registered from version {version} to {version + 1}."
                )
            for migration in migrations:
                migration.migrate(meta, tables)
            version += 1
            meta["version"] = version
