from __future__ import annotations

import importlib
import logging
import sys
from dataclasses import dataclass
from typing import Dict, List

from src.server.io.migrations import CORE_SAVE_MIGRATIONS
from src.shared.config import GameConfig
from src.shared.migrations import MigrationRegistry
from src.shared.mod_api import ENGINE_MOD_API_VERSION, ModContribution, mod
from src.shared.mods import (
    ModManifest,
    discover_mods,
    read_engine_version,
    resolve_mod_load_order,
    validate_engine_compatibility,
)
from src.shared.schema import WorldSchemaRegistry
from src.shared.system_interfaces import ISystem

LOGGER = logging.getLogger(__name__)


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
        self._runtime = None
        print(f"[ModManager] Resolved Load Order: {self.config.active_mods}")
        return sorted_mods

    def load_runtime(self) -> ModRuntime:
        if self._runtime is not None:
            return self._runtime
        if not self.loaded_mods:
            raise RuntimeError("resolve_load_order() must run before loading mod contributions.")

        engine_version = read_engine_version(self.config.project_root)
        systems: list[ISystem] = []
        system_positions: dict[str, int] = {}
        system_owners: dict[str, str] = {}
        schemas = WorldSchemaRegistry()
        migrations = MigrationRegistry(CORE_SAVE_MIGRATIONS)

        for manifest in self.loaded_mods:
            validate_engine_compatibility(manifest, engine_version)
            if manifest.api_version != ENGINE_MOD_API_VERSION:
                raise RuntimeError(
                    f"Module '{manifest.id}' targets API {manifest.api_version}; "
                    f"engine requires {ENGINE_MOD_API_VERSION}."
                )
            registration_path = manifest.path / "registration.py"
            if not registration_path.exists():
                LOGGER.warning(
                    "Module '%s' has no registration.py; skipping its runtime contributions.",
                    manifest.id,
                )
                continue

            project_root = str(self.config.project_root)
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
            package_name = manifest.path.name
            if not package_name.isidentifier():
                raise RuntimeError(
                    f"Module directory '{package_name}' must be a valid Python identifier."
                )
            registration_module = importlib.import_module(
                f"modules.{package_name}.registration"
            )
            contributor = getattr(registration_module, "contribute", None)
            register = getattr(registration_module, "register", None)
            if callable(contributor):
                contribution = contributor()
                if not isinstance(contribution, ModContribution):
                    raise TypeError(
                        f"Module '{manifest.id}' contribute() returned "
                        f"{type(contribution).__name__}. Return mod(...) or "
                        "an advanced ModContribution."
                    )
            elif callable(register):
                registered = register()
                if isinstance(registered, ModContribution):
                    contribution = registered
                else:
                    if registered is None:
                        raise TypeError(
                            f"Module '{manifest.id}' register() must return a system or iterable of systems."
                        )
                    elif isinstance(registered, (str, bytes, dict)):
                        legacy_systems = (registered,)
                    else:
                        try:
                            legacy_systems = tuple(registered)
                        except TypeError:
                            legacy_systems = (registered,)
                    contribution = mod(*legacy_systems)
            else:
                LOGGER.warning(
                    "Module '%s' registration.py has no contribute() or register() entry point; skipping it.",
                    manifest.id,
                )
                continue

            for system in contribution.systems:
                system_id = str(system.id).strip()
                existing_index = system_positions.get(system_id)
                if existing_index is not None:
                    previous_owner = system_owners[system_id]
                    if previous_owner == manifest.id:
                        raise RuntimeError(
                            f"Module '{manifest.id}' registers system id '{system_id}' more than once."
                        )
                    LOGGER.warning(
                        "Module '%s' overrides system '%s' contributed by '%s'.",
                        manifest.id,
                        system_id,
                        previous_owner,
                    )
                    systems[existing_index] = system
                else:
                    system_positions[system_id] = len(systems)
                    systems.append(system)
                system_owners[system_id] = manifest.id

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
