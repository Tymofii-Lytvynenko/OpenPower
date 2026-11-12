"""Enforce OpenPower-specific architecture rules not covered by import graphs."""

from __future__ import annotations

import argparse
import ast
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import rtoml

EXPECTED_SRC_PACKAGES = frozenset(
    {"client", "core", "engine", "modding", "server", "shared", "simulation"}
)
EXPECTED_IMPORT_LINTER_ROOTS = frozenset({"src", "modules"})
REQUIRED_FORBIDDEN_CONTRACTS = {
    "shared-is-leaf": frozenset(
        {"src.core", "src.engine", "src.server", "src.client", "src.simulation", "src.modding", "modules"}
    ),
    "core-isolation": frozenset(
        {"src.engine", "src.server", "src.client", "src.simulation", "src.modding", "modules"}
    ),
    "engine-isolation": frozenset(
        {"src.server", "src.client", "src.simulation", "src.modding", "modules"}
    ),
    "server-isolation": frozenset(
        {"src.client", "src.simulation", "src.modding", "modules"}
    ),
    "client-isolation": frozenset(
        {"src.engine", "src.server", "src.simulation", "src.modding", "modules"}
    ),
    "modules-isolation": frozenset(
        {"src.engine", "src.server", "src.client", "src.simulation", "src.modding"}
    ),
}
REQUIRED_FORBIDDEN_SOURCES = {
    "shared-is-leaf": frozenset({"src.shared"}),
    "core-isolation": frozenset({"src.core"}),
    "engine-isolation": frozenset({"src.engine"}),
    "server-isolation": frozenset({"src.server"}),
    "client-isolation": frozenset({"src.client"}),
    "modules-isolation": frozenset({"modules"}),
}
REQUIRED_LAYER_CONTRACTS = {
    "server-engine-core-shared-layers": ["src.server", "src.engine", "src.core", "src.shared"],
    "client-core-shared-layers": ["src.client", "src.core", "src.shared"],
    "modules-core-shared-layers": ["modules", "src.core", "src.shared"],
}
REQUIRED_INDEPENDENCE_CONTRACTS = {
    "client-server-independence": frozenset({"src.client", "src.server"}),
}
REQUIRED_PROTECTED_CONTRACT = {
    "id": "engine-internals-protected",
    "protected_modules": frozenset(
        {"src.engine.simulator", "src.engine.mod_manager", "src.engine.command_pipeline"}
    ),
    "allowed_importers": frozenset(
        {"src.engine", "src.server.session", "src.simulation.ui_testing.fixtures"}
    ),
}
ALLOWED_DYNAMIC_IMPORTS = {
    "src.engine.mod_manager": ("load_runtime", "modules.", ".registration", "package_name"),
    "src.modding.client_extensions": (
        "load_client_presentation",
        "modules.",
        ".client_presentation",
        "package_name",
    ),
}
INTERNAL_LAYER_ALLOWLISTS = {
    "shared": frozenset({"shared"}),
    "core": frozenset({"shared", "core"}),
    "engine": frozenset({"shared", "core", "engine"}),
    "server": frozenset({"shared", "core", "engine", "server"}),
    "client": frozenset({"shared", "core", "client"}),
}
MUTATING_TABLE_METHODS = frozenset({"update_table", "remove_table"})
MUTATING_CONTAINER_METHODS = frozenset(
    {"append", "clear", "extend", "insert", "pop", "remove", "setdefault", "update"}
)


@dataclass(frozen=True, slots=True)
class Finding:
    path: Path
    line: int
    message: str

    def format(self, root: Path) -> str:
        return f"{self.path.relative_to(root).as_posix()}:{self.line}: {self.message}"


def _source_files(root: Path) -> list[Path]:
    return sorted(
        path
        for package_root in (root / "src", root / "modules")
        if package_root.is_dir()
        for path in package_root.rglob("*.py")
        if not any(part.startswith((".", "__pycache__")) for part in path.relative_to(root).parts)
    )


def _module_name(root: Path, path: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _import_targets(node: ast.AST, module_name: str) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    if not isinstance(node, ast.ImportFrom):
        return ()

    base = node.module or ""
    if node.level:
        current_parts = module_name.split(".")
        if current_parts[-1] == "__init__":
            current_parts.pop()
        package_parts = current_parts[:-1]
        remove_count = max(node.level - 1, 0)
        if remove_count:
            package_parts = package_parts[:-remove_count]
        base = ".".join(package_parts + ([base] if base else []))

    if not base:
        return ()
    targets = [base]
    if base in {"src", "modules"}:
        targets.extend(f"{base}.{alias.name}" for alias in node.names if alias.name != "*")
    return tuple(dict.fromkeys(targets))


def _load_project_config(root: Path) -> dict:
    project_file = root / "pyproject.toml"
    if not project_file.is_file():
        return {}
    return rtoml.loads(project_file.read_text(encoding="utf-8"))


def _coverage_findings(root: Path, config: dict, source_files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    src_root = root / "src"
    modules_root = root / "modules"
    if not src_root.is_dir() or not modules_root.is_dir():
        missing = [name for name, path in (("src", src_root), ("modules", modules_root)) if not path.is_dir()]
        return [Finding(root, 1, f"Architecture roots missing: {', '.join(missing)}.")]

    src_packages = {
        path.name for path in src_root.iterdir() if path.is_dir() and not path.name.startswith("__")
    }
    unexpected = sorted(src_packages - EXPECTED_SRC_PACKAGES)
    missing = sorted(EXPECTED_SRC_PACKAGES - src_packages)
    if unexpected:
        findings.append(Finding(src_root, 1, f"Uncontracted src package(s): {', '.join(unexpected)}; add explicit architecture rules."))
    if missing:
        findings.append(Finding(src_root, 1, f"Expected src package(s) missing from the graph: {', '.join(missing)}."))

    package_counts = {name: 0 for name in EXPECTED_SRC_PACKAGES}
    for path in source_files:
        relative = path.relative_to(src_root) if path.is_relative_to(src_root) else None
        if relative is not None and relative.parts:
            package_counts[relative.parts[0]] = package_counts.get(relative.parts[0], 0) + 1
    empty_packages = sorted(name for name, count in package_counts.items() if count == 0)
    if empty_packages:
        findings.append(Finding(src_root, 1, f"Package(s) have no Python modules in the analyzed graph: {', '.join(empty_packages)}."))

    import_linter = config.get("tool", {}).get("importlinter", {})
    configured_roots = frozenset(import_linter.get("root_packages", ()))
    if configured_roots != EXPECTED_IMPORT_LINTER_ROOTS:
        findings.append(
            Finding(
                root / "pyproject.toml",
                1,
                "Import Linter root_packages must be exactly ['src', 'modules']; "
                f"found {sorted(configured_roots)}.",
            )
        )

    if import_linter.get("exclude_type_checking_imports") is not False:
        findings.append(
            Finding(
                root / "pyproject.toml",
                1,
                "Import Linter must include TYPE_CHECKING imports in the architecture graph.",
            )
        )

    contracts = import_linter.get("contracts", ())
    contracts_by_id = {
        contract.get("id"): contract
        for contract in contracts
        if isinstance(contract, dict) and contract.get("id")
    }
    required_ids = (
        set(REQUIRED_FORBIDDEN_CONTRACTS)
        | set(REQUIRED_LAYER_CONTRACTS)
        | set(REQUIRED_INDEPENDENCE_CONTRACTS)
        | {REQUIRED_PROTECTED_CONTRACT["id"]}
    )
    missing_contracts = sorted(required_ids - set(contracts_by_id))
    if missing_contracts:
        findings.append(
            Finding(
                root / "pyproject.toml",
                1,
                f"Required Import Linter contract(s) missing: {', '.join(missing_contracts)}.",
            )
        )
    for contract_id, forbidden in REQUIRED_FORBIDDEN_CONTRACTS.items():
        contract = contracts_by_id.get(contract_id, {})
        actual = frozenset(contract.get("forbidden_modules", ()))
        sources = frozenset(contract.get("source_modules", ()))
        if (
            contract.get("type") != "forbidden"
            or not forbidden.issubset(actual)
            or sources != REQUIRED_FORBIDDEN_SOURCES[contract_id]
        ):
            findings.append(
                Finding(
                    root / "pyproject.toml",
                    1,
                    f"Contract '{contract_id}' must forbid {sorted(forbidden)}.",
                )
            )
    for contract_id, layers in REQUIRED_LAYER_CONTRACTS.items():
        contract = contracts_by_id.get(contract_id, {})
        if contract.get("type") != "layers" or contract.get("layers") != layers:
            findings.append(
                Finding(
                    root / "pyproject.toml",
                    1,
                    f"Contract '{contract_id}' must keep layer order {layers}.",
                )
            )
    for contract_id, modules in REQUIRED_INDEPENDENCE_CONTRACTS.items():
        contract = contracts_by_id.get(contract_id, {})
        if contract.get("type") != "independence" or frozenset(contract.get("modules", ())) != modules:
            findings.append(
                Finding(
                    root / "pyproject.toml",
                    1,
                    f"Contract '{contract_id}' must enforce independence between {sorted(modules)}.",
                )
            )
    protected_contract = contracts_by_id.get(REQUIRED_PROTECTED_CONTRACT["id"], {})
    if (
        protected_contract.get("type") != "protected"
        or frozenset(protected_contract.get("protected_modules", ()))
        != REQUIRED_PROTECTED_CONTRACT["protected_modules"]
        or frozenset(protected_contract.get("allowed_importers", ()))
        != REQUIRED_PROTECTED_CONTRACT["allowed_importers"]
    ):
        findings.append(
            Finding(
                root / "pyproject.toml",
                1,
                "Engine protected imports must use only the audited engine, server-session, and UI-fixture importers.",
            )
        )

    for mod_dir in sorted(path for path in modules_root.iterdir() if path.is_dir() and not path.name.startswith("__")):
        manifest = mod_dir / "mod.toml"
        if not manifest.is_file():
            findings.append(Finding(mod_dir, 1, "Every gameplay module needs a mod.toml manifest."))
            continue
        if not mod_dir.name.isidentifier():
            findings.append(Finding(manifest, 1, f"Module package directory '{mod_dir.name}' is not a Python identifier."))
    if not source_files:
        findings.append(Finding(root, 1, "No Python files were found under src/ or modules/; refusing an empty graph."))
    return findings


def _manifest_data(path: Path) -> tuple[str, tuple[str, ...]]:
    try:
        data = rtoml.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot parse module manifest: {exc}") from exc
    module_id = str(data.get("id") or path.parent.name)
    dependencies = data.get("dependencies", [])
    if not isinstance(dependencies, list) or any(not isinstance(item, str) for item in dependencies):
        raise ValueError("'dependencies' must be an array of module IDs.")
    return module_id, tuple(dependencies)


def _cycle_path(graph: dict[str, set[str]]) -> tuple[str, ...] | None:
    visited: set[str] = set()
    active: list[str] = []

    def visit(node: str) -> tuple[str, ...] | None:
        if node in active:
            start = active.index(node)
            return tuple(active[start:] + [node])
        if node in visited:
            return None
        visited.add(node)
        active.append(node)
        for target in sorted(graph.get(node, ())):
            cycle = visit(target)
            if cycle:
                return cycle
        active.pop()
        return None

    for node in sorted(graph):
        cycle = visit(node)
        if cycle:
            return cycle
    return None


def _manifest_findings(root: Path, modules: dict[str, Path]) -> list[Finding]:
    findings: list[Finding] = []
    dependencies: dict[str, set[str]] = {}
    paths_by_id: dict[str, Path] = {}
    for _package_name, mod_dir in modules.items():
        manifest = mod_dir / "mod.toml"
        if not manifest.is_file():
            continue
        try:
            module_id, declared = _manifest_data(manifest)
        except ValueError as exc:
            findings.append(Finding(manifest, 1, str(exc)))
            continue
        if module_id in paths_by_id:
            findings.append(Finding(manifest, 1, f"Duplicate module ID '{module_id}' also declared by {paths_by_id[module_id].relative_to(root).as_posix()}."))
        paths_by_id[module_id] = manifest
        dependencies[module_id] = set(declared)
        for dependency in declared:
            if dependency not in modules:
                findings.append(Finding(manifest, 1, f"Module '{module_id}' declares missing dependency '{dependency}'."))

    cycle = _cycle_path(dependencies)
    if cycle:
        findings.append(Finding(root / "modules", 1, f"Circular mod dependency: {' -> '.join(cycle)}."))

    package_to_id = {}
    for package_name, mod_dir in modules.items():
        manifest = mod_dir / "mod.toml"
        try:
            module_id, _ = _manifest_data(manifest)
        except (ValueError, OSError):
            continue
        package_to_id[package_name] = module_id

    for source_file in _source_files(root):
        relative = source_file.relative_to(root / "modules") if source_file.is_relative_to(root / "modules") else None
        if relative is None or len(relative.parts) < 2:
            continue
        source_package = relative.parts[0]
        source_id = package_to_id.get(source_package)
        if source_id is None:
            continue
        try:
            tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        except (OSError, SyntaxError) as exc:
            findings.append(Finding(source_file, getattr(exc, "lineno", 1) or 1, f"Cannot parse Python source: {exc}."))
            continue
        source_module = _module_name(root, source_file)
        for node in ast.walk(tree):
            for target in _import_targets(node, source_module):
                target_parts = target.split(".")
                if len(target_parts) < 2 or target_parts[0] != "modules":
                    continue
                target_package = target_parts[1]
                target_id = package_to_id.get(target_package)
                if target_id is None or target_id == source_id:
                    continue
                if target_id not in dependencies.get(source_id, set()):
                    findings.append(
                        Finding(
                            source_file,
                            getattr(node, "lineno", 1),
                            f"Module '{source_id}' imports '{target_id}' without declaring it in mod.toml dependencies.",
                        )
                    )

    imported_graph: dict[str, set[str]] = {module_id: set() for module_id in dependencies}
    for source_file in _source_files(root):
        relative = source_file.relative_to(root / "modules") if source_file.is_relative_to(root / "modules") else None
        if relative is None or len(relative.parts) < 2:
            continue
        source_id = package_to_id.get(relative.parts[0])
        if source_id is None:
            continue
        try:
            tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        except (OSError, SyntaxError):
            continue
        source_module = _module_name(root, source_file)
        for node in ast.walk(tree):
            for target in _import_targets(node, source_module):
                parts = target.split(".")
                if len(parts) >= 2 and parts[0] == "modules":
                    target_id = package_to_id.get(parts[1])
                    if target_id and target_id != source_id:
                        imported_graph[source_id].add(target_id)
    cycle = _cycle_path(imported_graph)
    if cycle:
        findings.append(Finding(root / "modules", 1, f"Circular cross-module imports: {' -> '.join(cycle)}."))
    return findings


def _import_aliases(tree: ast.Module) -> tuple[set[str], set[str], set[str], set[str]]:
    importlib_names: set[str] = set()
    import_module_names: set[str] = set()
    builtin_import_names = {"__import__"}
    builtins_names = {"builtins"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    importlib_names.add(alias.asname or "importlib")
                if alias.name == "builtins":
                    builtins_names.add(alias.asname or "builtins")
        elif isinstance(node, ast.ImportFrom):
            if node.module == "importlib":
                import_module_names.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name == "import_module"
                )
            if node.module == "builtins":
                builtin_import_names.update(
                    alias.asname or alias.name
                    for alias in node.names
                    if alias.name == "__import__"
                )
    return importlib_names, import_module_names, builtin_import_names, builtins_names


def _is_import_call(
    call: ast.Call,
    aliases: tuple[set[str], set[str], set[str], set[str]],
) -> bool:
    importlib_names, import_module_names, builtin_import_names, builtins_names = aliases
    function = call.func
    if isinstance(function, ast.Name):
        return function.id in import_module_names | builtin_import_names
    return (
        isinstance(function, ast.Attribute)
        and function.attr == "import_module"
        and isinstance(function.value, ast.Name)
        and function.value.id in importlib_names
    ) or (
        isinstance(function, ast.Attribute)
        and function.attr == "__import__"
        and isinstance(function.value, ast.Name)
        and function.value.id in builtins_names
    )


def _is_importlib_import_module_call(
    call: ast.Call,
    aliases: tuple[set[str], set[str], set[str], set[str]],
) -> bool:
    importlib_names, import_module_names, _, _ = aliases
    function = call.func
    return (
        isinstance(function, ast.Name) and function.id in import_module_names
    ) or (
        isinstance(function, ast.Attribute)
        and function.attr == "import_module"
        and isinstance(function.value, ast.Name)
        and function.value.id in importlib_names
    )


def _literal_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_expected_loader_expression(node: ast.AST, module_name: str) -> bool:
    expected = ALLOWED_DYNAMIC_IMPORTS.get(module_name)
    if expected is None or not isinstance(node, ast.JoinedStr):
        return False
    _, prefix, suffix, variable = expected
    values = node.values
    return (
        len(values) == 3
        and isinstance(values[0], ast.Constant)
        and values[0].value == prefix
        and isinstance(values[1], ast.FormattedValue)
        and values[1].conversion == -1
        and values[1].format_spec is None
        and isinstance(values[1].value, ast.Name)
        and values[1].value.id == variable
        and isinstance(values[2], ast.Constant)
        and values[2].value == suffix
    )


class _DynamicImportVisitor(ast.NodeVisitor):
    def __init__(
        self,
        path: Path,
        module_name: str,
        aliases: tuple[set[str], set[str], set[str], set[str]],
    ) -> None:
        self.path = path
        self.module_name = module_name
        self.aliases = aliases
        self.findings: list[Finding] = []
        self.function_stack: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        if _is_import_call(node, self.aliases):
            call_target = node.args[0] if node.args else None
            literal = _literal_string(call_target) if call_target is not None else None
            expected = ALLOWED_DYNAMIC_IMPORTS.get(self.module_name)
            expected_site = bool(
                expected
                and self.function_stack
                and self.function_stack[-1] == expected[0]
                and call_target is not None
                and _is_importlib_import_module_call(node, self.aliases)
                and _is_expected_loader_expression(call_target, self.module_name)
            )
            if not expected_site:
                target_description = repr(literal) if literal is not None else "a computed module name"
                self.findings.append(
                    Finding(
                        self.path,
                        node.lineno,
                        f"Unapproved dynamic import of {target_description}; use a declared composition point.",
                    )
                )
        self.generic_visit(node)


def _dynamic_import_findings(root: Path, source_files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in source_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            findings.append(Finding(path, getattr(exc, "lineno", 1) or 1, f"Cannot parse Python source: {exc}."))
            continue
        module_name = _module_name(root, path)
        visitor = _DynamicImportVisitor(path, module_name, _import_aliases(tree))
        visitor.visit(tree)
        findings.extend(visitor.findings)
    return findings


def _is_state_expression(node: ast.AST, tainted: set[str], session_names: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in tainted
    if isinstance(node, ast.Attribute):
        if (
            node.attr in {"state", "_state"}
            and isinstance(node.value, ast.Name)
            and (node.value.id in session_names or node.value.id == "self")
        ):
            return True
        return _is_state_expression(node.value, tainted, session_names)
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get_state_snapshot":
            return _is_session_expression(node.func.value, session_names)
        return _is_state_expression(node.func, tainted, session_names)
    return False


def _is_session_expression(node: ast.AST, session_names: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in session_names
    if isinstance(node, ast.Attribute):
        return _is_session_expression(node.value, session_names)
    return False


def _is_authoritative_container_expression(
    node: ast.AST,
    state_names: set[str],
    session_names: set[str],
    container_names: set[str] | None = None,
) -> bool:
    if isinstance(node, ast.Attribute) and node.attr in {"tables", "globals"}:
        return _is_state_expression(node.value, state_names, session_names)
    if isinstance(node, ast.Subscript):
        if isinstance(node.value, ast.Attribute) and node.value.attr == "tables":
            return False
        return _is_authoritative_container_expression(
            node.value, state_names, session_names, container_names,
        )
    if isinstance(node, ast.Name):
        return node.id in (container_names or set())
    return False


def _is_authoritative_container_target(
    node: ast.AST,
    state_names: set[str],
    session_names: set[str],
    container_names: set[str],
) -> bool:
    if isinstance(node, ast.Name):
        return node.id in container_names
    if isinstance(node, ast.Subscript):
        return _is_authoritative_container_expression(
            node.value, state_names, session_names, container_names,
        )
    if isinstance(node, ast.Attribute):
        return _is_state_expression(node.value, state_names, session_names)
    return False


class _ClientMutationVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.findings: list[Finding] = []
        self.state_stack: list[set[str]] = []
        self.session_stack: list[set[str]] = []
        self.container_stack: list[set[str]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def _visit_function(self, node: ast.FunctionDef) -> None:
        state_names = {
            arg.arg
            for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
            if arg.arg in {"state", "game_state", "state_view", "snapshot", "authoritative_state"}
        }
        session_names = {
            arg.arg
            for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
            if "session" in arg.arg or arg.arg in {"client", "net_client"}
        }
        self.state_stack.append(state_names)
        self.session_stack.append(session_names)
        self.container_stack.append(set())
        for statement in node.body:
            self.visit(statement)
        self.container_stack.pop()
        self.session_stack.pop()
        self.state_stack.pop()

    def _state_names(self) -> set[str]:
        return self.state_stack[-1]

    def _session_names(self) -> set[str]:
        return self.session_stack[-1]

    def _container_names(self) -> set[str]:
        return self.container_stack[-1]

    def visit_Assign(self, node: ast.Assign) -> None:
        if not self.state_stack:
            self.generic_visit(node)
            return
        self._check_assignment(node.targets, node.value, node.lineno)
        self.generic_visit(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                if _is_state_expression(node.value, self._state_names(), self._session_names()):
                    self._state_names().add(target.id)
                if _is_authoritative_container_expression(
                    node.value,
                    self._state_names(),
                    self._session_names(),
                    self._container_names(),
                ):
                    self._container_names().add(target.id)
            self.visit(target)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if not self.state_stack:
            self.generic_visit(node)
            return
        if node.value is not None:
            self._check_assignment([node.target], node.value, node.lineno)
            self.visit(node.value)
            if isinstance(node.target, ast.Name):
                if _is_state_expression(node.value, self._state_names(), self._session_names()):
                    self._state_names().add(node.target.id)
                if _is_authoritative_container_expression(
                    node.value,
                    self._state_names(),
                    self._session_names(),
                    self._container_names(),
                ):
                    self._container_names().add(node.target.id)
        self.visit(node.target)

    def _check_assignment(self, targets: Iterable[ast.AST], value: ast.AST, line: int) -> None:
        for target in targets:
            if _is_authoritative_container_target(
                target,
                self._state_names(),
                self._session_names(),
                self._container_names(),
            ):
                self._report(line, "Client code must not assign directly into authoritative state tables or globals.")

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if not self.state_stack:
            self.generic_visit(node)
            return
        self._check_assignment([node.target], node.value, node.lineno)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if not self.state_stack:
            self.generic_visit(node)
            return
        function = node.func
        if isinstance(function, ast.Attribute):
            if function.attr in MUTATING_TABLE_METHODS and _is_state_expression(
                function.value, self._state_names(), self._session_names(),
            ):
                self._report(node.lineno, f"Client code must not call GameState.{function.attr}().")
            elif function.attr in MUTATING_CONTAINER_METHODS and (
                _is_authoritative_container_expression(
                    function.value,
                    self._state_names(),
                    self._session_names(),
                    self._container_names(),
                )
                or isinstance(function.value, ast.Name) and function.value.id in self._container_names()
            ):
                self._report(node.lineno, "Client code must not mutate a container owned by authoritative state.")
        self.generic_visit(node)

    def _report(self, line: int, message: str) -> None:
        if not any(finding.line == line and finding.message == message for finding in self.findings):
            self.findings.append(Finding(self.path, line, message))


def _client_mutation_findings(root: Path, source_files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    client_root = root / "src" / "client"
    for path in source_files:
        if not path.is_relative_to(client_root):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            findings.append(Finding(path, getattr(exc, "lineno", 1) or 1, f"Cannot parse Python source: {exc}."))
            continue
        visitor = _ClientMutationVisitor(path)
        visitor.visit(tree)
        findings.extend(visitor.findings)
    return findings


def run_custom_checks(root: Path) -> list[Finding]:
    root = root.resolve()
    source_files = _source_files(root)
    config = _load_project_config(root)
    findings = _coverage_findings(root, config, source_files)
    modules_root = root / "modules"
    modules = {
        path.name: path
        for path in modules_root.iterdir()
        if path.is_dir() and not path.name.startswith("__")
    } if modules_root.is_dir() else {}
    findings.extend(_manifest_findings(root, modules))
    findings.extend(_dynamic_import_findings(root, source_files))
    findings.extend(_client_mutation_findings(root, source_files))
    return sorted(findings, key=lambda finding: (finding.path.as_posix(), finding.line, finding.message))


def _run_import_linter(root: Path) -> tuple[int, str]:
    executable = shutil.which("lint-imports")
    if executable is None:
        return 2, "Import Linter executable 'lint-imports' is not available on PATH. Install project dev dependencies."
    try:
        result = subprocess.run(
            [executable, "--no-cache"],
            cwd=root,
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError as exc:
        return 2, f"Could not start Import Linter: {exc}"
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    return result.returncode, output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate OpenPower architecture contracts.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    exit_code = 0

    print("== Import Linter ==")
    linter_code, output = _run_import_linter(root)
    print(output)
    if linter_code:
        exit_code = linter_code

    print("== OpenPower AST and coverage checks ==")
    findings = run_custom_checks(root)
    if findings:
        for finding in findings:
            print(f"ERROR {finding.format(root)}")
        exit_code = exit_code or 1
    else:
        print("All custom architecture checks passed.")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
