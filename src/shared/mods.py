import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Sequence

import rtoml


_ENGINE_VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_DEFAULT_ENGINE_VERSION = "0.1.0"


@dataclass
class ModManifest:
    id: str
    name: str
    version: str
    api_version: int = 1
    dependencies: List[str] = field(default_factory=list)
    path: Path = field(default_factory=Path)
    min_engine_version: str = ""
    max_engine_version: str = ""


def load_requested_mods(project_root: Path) -> List[str]:
    """
    Reads the user-selected mod stack from mods.json.

    The file intentionally stays lightweight: dependency expansion happens in
    resolve_mod_load_order so every caller can share the same resolution path.
    """
    mods_json_path = project_root / "mods.json"
    if not mods_json_path.exists():
        return ["base"]

    with open(mods_json_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    active_mods = data.get("active_mods", ["base"])
    if not isinstance(active_mods, list) or not active_mods:
        return ["base"]

    # Preserve the user-declared order while dropping duplicates and empty items.
    unique_mods: List[str] = []
    seen = set()
    for mod_id in active_mods:
        normalized = str(mod_id).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_mods.append(normalized)

    return unique_mods or ["base"]


def discover_mods(modules_dir: Path) -> Dict[str, ModManifest]:
    """
    Scans modules/ and returns every discovered module manifest.

    We keep this free of higher-level config/session dependencies so the same
    discovery logic can be reused by the client, server, and tests.
    """
    found: Dict[str, ModManifest] = {}
    if not modules_dir.exists():
        return found

    for mod_dir in sorted(modules_dir.iterdir(), key=lambda path: path.name):
        if not mod_dir.is_dir():
            continue

        manifest_path = mod_dir / "mod.toml"
        registration_path = mod_dir / "registration.py"

        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as handle:
                data = rtoml.load(handle)

            dependencies = data.get("dependencies", [])
            if not isinstance(dependencies, list) or any(
                not isinstance(dependency, str) or not dependency.strip()
                for dependency in dependencies
            ):
                raise RuntimeError(
                    f"Module '{mod_dir.name}' has an invalid dependencies list in {manifest_path}."
                )
            manifest = ModManifest(
                id=data.get("id", mod_dir.name),
                name=data.get("name", mod_dir.name),
                version=data.get("version", "0.0.1"),
                api_version=int(data.get("api_version", 1)),
                dependencies=dependencies,
                path=mod_dir,
                min_engine_version=str(data.get("min_engine_version", "")).strip(),
                max_engine_version=str(data.get("max_engine_version", "")).strip(),
            )
            found[manifest.id] = manifest
            continue

        if registration_path.exists():
            found[mod_dir.name] = ModManifest(
                id=mod_dir.name,
                name=mod_dir.name,
                version="0.0.1",
                api_version=1,
                dependencies=[],
                path=mod_dir,
            )

    return found


def resolve_mod_load_order(
    requested_mods: Sequence[str],
    available_mods: Mapping[str, ModManifest],
) -> List[ModManifest]:
    """
    Resolves the active mod stack, including transitive dependencies.

    The topological sort keeps dependency order stable and deterministic, which
    avoids "random" load order changes caused by set iteration.
    """
    requested = list(requested_mods) or ["base"]

    required_ids = set()
    queue = list(requested)
    while queue:
        mod_id = queue.pop(0)
        if mod_id in required_ids:
            continue

        required_ids.add(mod_id)
        manifest = available_mods.get(mod_id)
        if manifest is not None:
            queue.extend(manifest.dependencies)

    sorted_mods: List[ModManifest] = []
    visited = set()
    temp_mark = set()

    def visit(mod_id: str) -> None:
        if mod_id in temp_mark:
            raise RuntimeError(f"Circular dependency: {mod_id}")
        if mod_id in visited:
            return
        if mod_id not in available_mods:
            raise RuntimeError(f"Missing dependency: '{mod_id}'")

        temp_mark.add(mod_id)
        for dependency_id in available_mods[mod_id].dependencies:
            visit(dependency_id)
        temp_mark.remove(mod_id)

        visited.add(mod_id)
        sorted_mods.append(available_mods[mod_id])

    # Requested mods remain the primary roots, while discovered dependencies are
    # still visited deterministically if they were pulled in transitively.
    root_ids = [mod_id for mod_id in requested if mod_id in available_mods]
    root_ids.extend(
        mod_id
        for mod_id in available_mods
        if mod_id in required_ids and mod_id not in root_ids
    )

    for mod_id in root_ids:
        visit(mod_id)

    return sorted_mods


def read_engine_version(project_root: Path) -> str:
    """Read the source checkout's declared version with a packaged fallback."""

    metadata_path = project_root / "pyproject.toml"
    if not metadata_path.exists():
        return _DEFAULT_ENGINE_VERSION
    try:
        with metadata_path.open("r", encoding="utf-8") as handle:
            project = rtoml.load(handle).get("project", {})
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Unable to read engine version from {metadata_path}.") from exc
    version = project.get("version") if isinstance(project, dict) else None
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError(f"Engine version is missing from {metadata_path}.")
    return version.strip()


def validate_engine_compatibility(manifest: ModManifest, engine_version: str) -> None:
    """Reject malformed or incompatible engine-version bounds before state loading."""

    current = _parse_engine_version(engine_version, "engine")
    minimum = _parse_engine_version(manifest.min_engine_version, "min_engine_version", optional=True)
    maximum = _parse_engine_version(manifest.max_engine_version, "max_engine_version", optional=True)
    if minimum is not None and maximum is not None and minimum > maximum:
        raise RuntimeError(
            f"Module '{manifest.id}' declares min_engine_version greater than max_engine_version."
        )
    if minimum is not None and current < minimum:
        raise RuntimeError(
            f"Module '{manifest.id}' requires engine >= {manifest.min_engine_version}; "
            f"current engine is {engine_version}."
        )
    if maximum is not None and current > maximum:
        raise RuntimeError(
            f"Module '{manifest.id}' supports engine <= {manifest.max_engine_version}; "
            f"current engine is {engine_version}."
        )


def _parse_engine_version(value: str, field_name: str, optional: bool = False) -> tuple[int, int, int] | None:
    normalized = str(value or "").strip()
    if optional and not normalized:
        return None
    match = _ENGINE_VERSION_PATTERN.fullmatch(normalized)
    if match is None:
        raise RuntimeError(
            f"Invalid {field_name} '{normalized}'; expected a numeric MAJOR.MINOR.PATCH version."
        )
    return tuple(int(part) for part in match.groups())


def resolve_project_mods(project_root: Path) -> List[ModManifest]:
    """Convenience wrapper for callers that only know the project root."""
    requested_mods = load_requested_mods(project_root)
    available_mods = discover_mods(project_root / "modules")
    return resolve_mod_load_order(requested_mods, available_mods)
