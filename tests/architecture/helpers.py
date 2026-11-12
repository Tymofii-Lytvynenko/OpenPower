from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import rtoml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ARCHITECTURE_TOOL = REPOSITORY_ROOT / "tools" / "architecture_check.py"


def write_file(root: Path, relative_path: str, content: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def import_fixture(
    root: Path,
    *,
    source: str,
    forbidden: str,
    source_path: str,
    source_code: str,
    target_code: str = "\n",
    contract_type: str = "forbidden",
    extra_contract: str = "",
) -> None:
    write_file(root, "src/__init__.py", "")
    write_file(root, "modules/__init__.py", "")
    write_file(root, f"{source.replace('.', '/')}/__init__.py", "")
    write_file(root, f"{source_path}/__init__.py", "")
    write_file(root, f"{source_path}/bad.py", source_code)
    if forbidden.startswith("src."):
        target_parts = forbidden.split(".")
        for size in range(2, len(target_parts) + 1):
            target_package = "/".join(target_parts[:size])
            write_file(root, f"{target_package}/__init__.py", target_code if size == len(target_parts) else "\n")
    elif forbidden.startswith("modules."):
        target_parts = forbidden.split(".")
        for size in range(2, len(target_parts) + 1):
            target_package = "/".join(target_parts[:size])
            write_file(root, f"{target_package}/__init__.py", target_code if size == len(target_parts) else "\n")

    if contract_type == "independence":
        contract = f'''[[tool.importlinter.contracts]]
name = "fixture contract"
id = "fixture"
type = "independence"
modules = ["{source}", "{forbidden}"]
'''
    elif contract_type == "protected":
        contract = f'''[[tool.importlinter.contracts]]
name = "fixture contract"
id = "fixture"
type = "protected"
protected_modules = ["{forbidden}"]
allowed_importers = ["src.engine"]
'''
    else:
        contract = f'''[[tool.importlinter.contracts]]
name = "fixture contract"
id = "fixture"
type = "forbidden"
source_modules = ["{source}"]
forbidden_modules = ["{forbidden}"]
'''
    write_file(
        root,
        "pyproject.toml",
        '''[tool.importlinter]
root_packages = ["src", "modules"]
exclude_type_checking_imports = false

'''
        + contract
        + extra_contract,
    )


def run_import_linter(root: Path) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("lint-imports")
    if executable is None:
        raise RuntimeError("Install project dev dependencies before running architecture tests.")
    return subprocess.run(
        [executable, "--no-cache"],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )


def custom_fixture_root(root: Path) -> None:
    project_config = rtoml.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    import_linter_config = project_config["tool"]["importlinter"]
    write_file(
        root,
        "pyproject.toml",
        rtoml.dumps({"tool": {"importlinter": import_linter_config}}),
    )
    for package in ("client", "core", "engine", "modding", "server", "shared", "simulation"):
        write_file(root, f"src/{package}/__init__.py", "\n")
    for protected_module in ("simulator", "mod_manager", "command_pipeline"):
        write_file(root, f"src/engine/{protected_module}.py", "\n")
    write_file(root, "src/server/session.py", "\n")
    write_file(root, "src/simulation/ui_testing/__init__.py", "\n")
    write_file(root, "src/simulation/ui_testing/fixtures.py", "\n")
    write_file(root, "src/__init__.py", "\n")
    write_file(root, "modules/__init__.py", "\n")
    write_file(root, "modules/base/__init__.py", "\n")
    write_file(root, "modules/base/mod.toml", 'id = "base"\ndependencies = []\n')
    write_file(root, "modules/alpha/__init__.py", "\n")
    write_file(root, "modules/alpha/mod.toml", 'id = "alpha"\ndependencies = []\n')


def run_architecture_tool(root: Path) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(ARCHITECTURE_TOOL), "--root", str(root)]
    return subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
