"""Load optional module presentation extensions at the application boundary."""

from __future__ import annotations

import importlib
import sys
from types import MappingProxyType
from typing import Any

from src.shared.config import GameConfig
from src.shared.mod_api import (
    CLIENT_PRESENTATION_API_VERSION,
    ClientPresentationContribution,
)
from src.shared.mods import discover_mods, resolve_mod_load_order


def load_client_presentation(config: GameConfig) -> MappingProxyType:
    """Load active modules' optional client APIs without importing them from UI code."""

    project_root = str(config.project_root)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    available = discover_mods(config.modules_dir)
    load_order = resolve_mod_load_order(config.active_mods, available)
    values: dict[str, Any] = {}
    owners: dict[str, str] = {}

    for manifest in load_order:
        if not (manifest.path / "client_presentation.py").is_file():
            continue
        package_name = manifest.path.name
        if not package_name.isidentifier():
            raise RuntimeError(
                f"Module directory '{package_name}' must be a valid Python identifier."
            )

        extension = importlib.import_module(
            f"modules.{package_name}.client_presentation"
        )
        contribute = getattr(extension, "contribute_client_presentation", None)
        if not callable(contribute):
            raise TypeError(
                f"Module '{manifest.id}' client_presentation.py must define "
                "contribute_client_presentation()."
            )
        contribution = contribute()
        if not isinstance(contribution, ClientPresentationContribution):
            raise TypeError(
                f"Module '{manifest.id}' returned an invalid client presentation contribution."
            )
        if contribution.api_version != CLIENT_PRESENTATION_API_VERSION:
            raise RuntimeError(
                f"Module '{manifest.id}' targets client presentation API "
                f"{contribution.api_version}; engine requires "
                f"{CLIENT_PRESENTATION_API_VERSION}."
            )

        for key, value in contribution.values.items():
            if not isinstance(key, str) or not key.strip():
                raise TypeError(
                    f"Module '{manifest.id}' provided an invalid presentation key."
                )
            previous_owner = owners.get(key)
            if previous_owner is not None:
                raise RuntimeError(
                    f"Modules '{previous_owner}' and '{manifest.id}' both provide "
                    f"client presentation key '{key}'."
                )
            owners[key] = manifest.id
            values[key] = value

    return MappingProxyType(values)
