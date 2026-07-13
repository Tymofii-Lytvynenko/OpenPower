from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


MOD_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class ModScaffoldResult:
    mod_id: str
    path: Path
    files: tuple[Path, ...]


def validate_mod_id(mod_id: str) -> str:
    normalized = str(mod_id).strip()
    if not MOD_ID_PATTERN.fullmatch(normalized):
        raise ValueError(
            "Mod id must use lower_snake_case and start with a letter."
        )
    return normalized


def scaffold_mod(
    project_root: Path,
    mod_id: str,
    *,
    display_name: str | None = None,
    dependencies: Iterable[str] = ("base",),
) -> ModScaffoldResult:
    normalized_id = validate_mod_id(mod_id)
    dependency_ids = tuple(dict.fromkeys(validate_mod_id(item) for item in dependencies))
    target = project_root.resolve() / "modules" / normalized_id
    if target.exists():
        raise FileExistsError(f"Module directory already exists: {target}")

    class_name = "".join(part.capitalize() for part in normalized_id.split("_")) + "System"
    title = (display_name or normalized_id.replace("_", " ").title()).strip()
    dependency_literal = ", ".join(json.dumps(item) for item in dependency_ids)
    system_dependencies = '["base.time"]' if "base" in dependency_ids else "[]"

    files = {
        "__init__.py": "",
        "mod.toml": (
            f"id = {json.dumps(normalized_id)}\n"
            f"name = {json.dumps(title, ensure_ascii=False)}\n"
            'version = "0.1.0"\n'
            "api_version = 1\n"
            f"dependencies = [{dependency_literal}]\n"
        ),
        "registration.py": (
            "from src.shared.mod_api import mod\n\n"
            f"from modules.{normalized_id}.systems import {class_name}\n\n\n"
            "def contribute():\n"
            f"    return mod({class_name})\n"
        ),
        "systems.py": (
            "from src.shared.state import GameState\n"
            "from src.shared.system_interfaces import SystemAccess, SystemPhase\n\n\n"
            f"class {class_name}:\n"
            "    access = SystemAccess(phase=SystemPhase.POST_PROCESS)\n\n"
            "    @property\n"
            "    def id(self) -> str:\n"
            f"        return \"{normalized_id}.main\"\n\n"
            "    @property\n"
            "    def dependencies(self) -> list[str]:\n"
            f"        return {system_dependencies}\n\n"
            "    def update(self, state: GameState, delta_time: float) -> None:\n"
            "        _ = state, delta_time\n"
        ),
        "README.md": (
            f"# {title}\n\n"
            "Generated with openpower mod create.\n\n"
            "Validate it with:\n\n"
            f"openpower mod validate {normalized_id}\n"
        ),
    }

    target.mkdir(parents=True)
    written: list[Path] = []
    for relative_path, content in files.items():
        path = target / relative_path
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        written.append(path)

    return ModScaffoldResult(
        mod_id=normalized_id,
        path=target,
        files=tuple(written),
    )
