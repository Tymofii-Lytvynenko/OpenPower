from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Dict, List

from src.server.io.migrations import CORE_SAVE_MIGRATIONS
from src.shared.config import GameConfig
from src.shared.migrations import MigrationRegistry
from src.shared.mod_api import ENGINE_MOD_API_VERSION, ModContribution
from src.shared.mods import ModManifest, discover_mods, resolve_mod_load_order
from src.shared.schema import WorldSchemaRegistry
from src.shared.system_interfaces import ISystem


@dataclass(frozen=True)
class ModRuntime:
    systems: tuple[ISystem, ...]
    schemas: WorldSchemaRegistry
    migrations: MigrationRegistry


class ModManager:
    """Resolves modules and aggregates their versioned runtime contributions."""

    def __init__(self, config: GameConfig):
        self.config = config
        self.modules_dir = config.project_root / "modules"
        self.loaded_mods: List[ModManifest] = []
        self._runtime: ModRuntime | None = None

    def resolve_load_order(self) -> List[ModManifest]:
        print("[ModManager] Scanning for modules...")
        available_mods = self._discover_mods()
        if not available_mods:
            raise RuntimeError(f"No modules found in {self.modules_dir}.")
        sorted_mods = self._sort_mods(available_mods)
        self.loaded_mods = sorted_mods
        self.config.active_mods = [manifest.id for manifest in sorted_mods]
        print(f"[ModManager] Resolved Load Order: {self.config.active_mods}")
        return sorted_mods

    def load_runtime(self) -> ModRuntime:
        if self._runtime is not None:
            return self._runtime
        if not self.loaded_mods:
            raise RuntimeError("resolve_load_order() must run before loading mod contributions.")

        systems: list[ISystem] = []
        schemas = WorldSchemaRegistry()
        migrations = MigrationRegistry(CORE_SAVE_MIGRATIONS)

        for manifest in self.loaded_mods:
            if manifest.api_version != ENGINE_MOD_API_VERSION:
                raise RuntimeError(
                    f"Module '{manifest.id}' targets API {manifest.api_version}; "
                    f"engine requires {ENGINE_MOD_API_VERSION}."
                )
            registration_path = manifest.path / "registration.py"
            if not registration_path.exists():
                continue

            registration_module = importlib.import_module(f"modules.{manifest.id}.registration")
            contributor = getattr(registration_module, "contribute", None)
            if not callable(contributor):
                raise RuntimeError(
                    f"Module '{manifest.id}' must expose contribute(). "
                    "The simplest form is: return mod(MySystem)."
                )
            contribution = contributor()
            if not isinstance(contribution, ModContribution):
                raise TypeError(
                    f"Module '{manifest.id}' contribute() returned "
                    f"{type(contribution).__name__}. Return mod(...) or "
                    "an advanced ModContribution."
                )

            systems.extend(contribution.systems)
            for schema in contribution.table_schemas:
                schemas.register(schema)
            for migration in contribution.save_migrations:
                migrations.register(migration)

        self._runtime = ModRuntime(tuple(systems), schemas, migrations)
        return self._runtime

    def _discover_mods(self) -> Dict[str, ModManifest]:
        return discover_mods(self.modules_dir)

    def _sort_mods(self, available: Dict[str, ModManifest]) -> List[ModManifest]:
        return resolve_mod_load_order(self.config.active_mods, available)
