from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from src.modding.scaffold import validate_mod_id
from src.server.session import GameSession
from src.shared.config import GameConfig
from src.shared.mods import discover_mods


@dataclass(frozen=True)
class ModValidationReport:
    mod_id: str
    load_order: tuple[str, ...]
    system_ids: tuple[str, ...]
    table_schemas: tuple[str, ...]
    state_tables: tuple[str, ...]
    action_types: tuple[str, ...]


def validate_mod(project_root: Path, mod_id: str) -> ModValidationReport:
    root = project_root.resolve()
    normalized_id = validate_mod_id(mod_id)
    available = discover_mods(root / "modules")
    manifest = available.get(normalized_id)
    if manifest is None:
        raise FileNotFoundError(
            f"Module '{normalized_id}' was not found under {root / 'modules'}."
        )
    if manifest.path.name != manifest.id:
        raise ValueError(
            f"Module directory '{manifest.path.name}' must match manifest id "
            f"'{manifest.id}'."
        )
    if not isinstance(manifest.dependencies, list) or any(
        not isinstance(dependency, str) or not dependency.strip()
        for dependency in manifest.dependencies
    ):
        raise TypeError(
            f"Module '{normalized_id}' dependencies must be non-empty strings."
        )

    config = GameConfig(root)
    config.requested_mods = [normalized_id]
    config.active_mods = [normalized_id]
    config.dev_mode = True

    with _project_import_path(root):
        session = GameSession.create_headless(config)
        session.tick(0.0)

    return ModValidationReport(
        mod_id=normalized_id,
        load_order=tuple(config.active_mods),
        system_ids=tuple(system.id for system in session.engine.execution_order),
        table_schemas=session.schemas.table_names,
        state_tables=tuple(sorted(session.state.tables)),
        action_types=tuple(
            sorted(
                f"{action_type.__module__}.{action_type.__qualname__}"
                for action_type in session.engine.handled_action_types
            )
        ),
    )


@contextmanager
def _project_import_path(project_root: Path) -> Iterator[None]:
    import_path = str(project_root)
    inserted = import_path not in sys.path
    if inserted:
        sys.path.insert(0, import_path)
    importlib.invalidate_caches()
    try:
        yield
    finally:
        if inserted:
            sys.path.remove(import_path)
