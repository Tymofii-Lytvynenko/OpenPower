from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openpower",
        description="OpenPower game launcher and development toolkit.",
    )
    command = parser.add_subparsers(dest="command", required=True)

    mod_parser = command.add_parser(
        "mod",
        help="Create and validate gameplay modules.",
    )
    mod_command = mod_parser.add_subparsers(dest="mod_command", required=True)

    create_parser = mod_command.add_parser(
        "create",
        help="Create a minimal valid module.",
    )
    create_parser.add_argument("mod_id")
    create_parser.add_argument("--name")
    create_parser.add_argument("--depends", nargs="+", default=["base"])
    _add_project_root(create_parser)
    create_parser.set_defaults(handler=_handle_mod_create)

    validate_parser = mod_command.add_parser(
        "validate",
        help="Validate a module through the real runtime.",
    )
    validate_parser.add_argument("mod_id")
    _add_project_root(validate_parser)
    validate_parser.set_defaults(handler=_handle_mod_validate)

    sim_parser = command.add_parser(
        "sim",
        help="Run deterministic headless simulations.",
    )
    sim_command = sim_parser.add_subparsers(dest="sim_command", required=True)

    run_parser = sim_command.add_parser(
        "run",
        help="Run one headless simulation.",
    )
    _add_simulation_arguments(run_parser)
    run_parser.set_defaults(handler=_handle_sim_run)

    compare_parser = sim_command.add_parser(
        "compare",
        help="Compare repeated deterministic runs.",
    )
    _add_simulation_arguments(compare_parser)
    compare_parser.add_argument("--runs", type=int, default=2)
    compare_parser.set_defaults(handler=_handle_sim_compare)

    ui_test_parser = command.add_parser(
        "ui-test",
        help="Run an automated Dear ImGui UI scenario.",
    )
    ui_test_command = ui_test_parser.add_subparsers(
        dest="ui_test_name",
        required=True,
    )
    budget_ui_test = ui_test_command.add_parser(
        "budget",
        help="Exercise the Budget panel and save UI artifacts.",
    )
    _add_project_root(budget_ui_test)
    budget_ui_test.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/ui/budget"),
        help="Directory for report.json and actual.png.",
    )
    budget_ui_test.add_argument("--width", type=int, default=1280)
    budget_ui_test.add_argument("--height", type=int, default=1000)
    budget_ui_test.set_defaults(handler=_handle_budget_ui_test)

    list_ui = ui_test_command.add_parser("list", help="List all registered UI test surfaces.")
    list_ui.set_defaults(handler=_handle_ui_list)
    live_smoke = ui_test_command.add_parser("live-smoke", help="Verify agent input in a real Arcade runtime.")
    _add_project_root(live_smoke)
    live_smoke.add_argument("--output", type=Path, default=Path("artifacts/ui/live-smoke"))
    live_smoke.set_defaults(handler=_handle_ui_live_smoke)
    for name in ("run", "all"):
        ui = ui_test_command.add_parser(name, help="Inspect a UI surface or every registered surface.")
        if name == "run":
            ui.add_argument("surface")
            ui.add_argument("--journey", type=Path, help="JSON interaction steps.")
            ui.add_argument("--baseline", type=Path, help="Expected screenshot PNG.")
            ui.add_argument("--tolerance", type=float, default=0.03)
        else:
            ui.add_argument("--rerun-failed", action="store_true", help="Repeat failed runs from the existing suite.json.")
        _add_project_root(ui)
        ui.add_argument("--output", type=Path)
        ui.add_argument("--fixture", type=Path, help="JSON tables, globals and time overrides.")
        ui.add_argument("--width", type=int, default=1920)
        ui.add_argument("--height", type=int, default=1080)
        ui.add_argument("--matrix", action="store_true", help="Run 800×600, 1024×768, 1280×720 and 1920×1080.")
        ui.set_defaults(handler=_handle_ui_run if name == "run" else _handle_ui_all)

    return parser


def _handle_ui_list(args) -> int:
    import json
    from src.client.ui.testing.catalog import list_surfaces
    print(json.dumps(list_surfaces(), ensure_ascii=False, indent=2))
    return 0


def _handle_ui_live_smoke(args) -> int:
    from src.client.ui.testing.live_smoke import run_live_smoke
    output = args.output if args.output.is_absolute() else args.project_root.resolve() / args.output
    return run_live_smoke(output)


def _handle_ui_run(args) -> int:
    import json
    from src.client.ui.testing.surface import run_surface
    if args.width <= 0 or args.height <= 0:
        raise ValueError("Viewport dimensions must be positive.")
    if not 0 <= args.tolerance <= 1:
        raise ValueError("Visual tolerance must be between 0 and 1.")
    if args.matrix:
        return _run_ui_batch(args, [args.surface])
    root = args.project_root.resolve()
    def read(path):
        if path is None:
            return None
        resolved = path if path.is_absolute() else root / path
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("UI journey and fixture files must contain JSON objects.")
        return payload
    requested_output = args.output or Path("artifacts/ui") / args.surface
    output = requested_output if requested_output.is_absolute() else root / requested_output
    baseline = args.baseline
    if baseline is not None and not baseline.is_absolute():
        baseline = root / baseline
    return run_surface(args.surface, output, root, (args.width, args.height),
                       read(args.journey), read(args.fixture), baseline, args.tolerance)


def _handle_ui_all(args) -> int:
    from src.client.ui.testing.catalog import list_surfaces
    return _run_ui_batch(args, [s["id"] for s in list_surfaces()])


def _run_ui_batch(args, surfaces) -> int:
    import json
    import os
    import subprocess
    root = args.project_root.resolve()
    requested_output = args.output or Path("artifacts/ui")
    output = (requested_output if requested_output.is_absolute() else root / requested_output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    sizes = [(800, 600), (1024, 768), (1280, 720), (1920, 1080)] if args.matrix else [(args.width, args.height)]
    prior = []
    jobs = {(surface, w, h) for surface in surfaces for w, h in sizes}
    if getattr(args, "rerun_failed", False):
        prior = json.loads((output / "suite.json").read_text(encoding="utf-8"))["runs"]
        jobs = {(r["surface"], r["width"], r["height"]) for r in prior if not r["passed"] and r["surface"] in surfaces}
        sizes = sorted({(w, h) for _, w, h in jobs})
        if any(w <= 0 or h <= 0 for w, h in sizes):
            raise ValueError("Suite viewport dimensions must be positive.")
    results = []
    for surface in surfaces:
        for width, height in sizes:
            if (surface, width, height) not in jobs:
                continue
            directory = output / surface / f"{width}x{height}"
            command = [sys.executable, str(Path(__file__).resolve().parents[1] / "main.py"),
                       "ui-test", "run", surface, "--project-root", str(root),
                       "--output", str(directory), "--width", str(width), "--height", str(height)]
            for flag in ("fixture", "journey", "baseline", "tolerance"):
                value = getattr(args, flag, None)
                if value is not None:
                    command.extend([f"--{flag}", str(value)])
            try:
                process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=90,
                                         env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                code, log = process.returncode, process.stdout + process.stderr
            except subprocess.TimeoutExpired:
                code, log = 1, "UI subprocess exceeded 90 seconds."
            results.append({"surface": surface, "width": width, "height": height,
                            "passed": code == 0, "exit_code": code,
                            "report": str(directory / "report.json"), "log": log})
            print(f"{'PASS' if code == 0 else 'FAIL'} {surface} {width}x{height}", flush=True)
    summary = output / "suite.json"
    if prior:
        replaced = {(r["surface"], r["width"], r["height"]) for r in results}
        results = [r for r in prior if (r["surface"], r["width"], r["height"]) not in replaced] + results
    summary.write_text(json.dumps({"schema_version": 1, "passed": all(r["passed"] for r in results),
                                   "runs": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Suite report: {summary}")
    return 0 if all(r["passed"] for r in results) else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return int(args.handler(args))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _add_project_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="OpenPower project root; defaults to the current directory.",
    )


def _add_simulation_arguments(parser: argparse.ArgumentParser) -> None:
    _add_project_root(parser)
    parser.add_argument("--mods", default="base")
    parser.add_argument("--years", type=int, default=0)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--player")
    parser.add_argument("--save")
    parser.add_argument("--actions", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--snapshot-interval", type=int, default=30)
    parser.add_argument("--diagnostics-interval", type=int, default=1)
    parser.add_argument("--no-export-tables", action="store_true")
    parser.add_argument("--fail-on-diagnostics", action="store_true")


def _handle_mod_create(args: argparse.Namespace) -> int:
    from src.modding.scaffold import scaffold_mod

    result = scaffold_mod(
        args.project_root,
        args.mod_id,
        display_name=args.name,
        dependencies=_split_names(args.depends),
    )
    print(f"Created module '{result.mod_id}' at {result.path}")
    print(f"Validate with: openpower mod validate {result.mod_id}")
    return 0


def _handle_mod_validate(args: argparse.Namespace) -> int:
    from src.modding.validation import validate_mod

    report = validate_mod(args.project_root, args.mod_id)
    print(f"Module '{report.mod_id}' is valid.")
    print(f"Load order: {', '.join(report.load_order)}")
    print(f"Systems: {len(report.system_ids)}")
    print(f"Schemas: {len(report.table_schemas)}")
    print(f"State tables: {len(report.state_tables)}")
    print(f"Actions: {len(report.action_types)}")
    return 0


def _handle_sim_run(args: argparse.Namespace) -> int:
    from src.simulation.runner import HeadlessSimulationRunner

    config = _simulation_config(args)
    report = HeadlessSimulationRunner(config).run()
    print(f"Run: {report.run_id}")
    print(f"Fingerprint: {report.state_fingerprint}")
    print(f"Report: {report.final_report_path}")
    if report.failed:
        for reason in report.failure_reasons:
            print(f"Failure: {reason}", file=sys.stderr)
        return 1
    return 0


def _handle_sim_compare(args: argparse.Namespace) -> int:
    from src.simulation.comparison import DeterminismComparisonRunner

    config = _simulation_config(args)
    output_dir = (
        _resolved_path(args.project_root, args.output)
        if args.output
        else None
    )
    report = DeterminismComparisonRunner(
        config,
        runs=args.runs,
        output_dir=output_dir,
    ).run()
    print(f"Matched: {report.matched}")
    print(f"Fingerprint: {report.fingerprints[0]}")
    print(f"Report: {report.report_path}")
    return 0 if report.matched else 1


def _handle_budget_ui_test(args: argparse.Namespace) -> int:
    if args.width <= 0 or args.height <= 0:
        raise ValueError("UI test viewport width and height must be positive.")

    from src.client.ui.testing.budget import run_budget_ui_test

    output_dir = _resolved_path(args.project_root.resolve(), args.output)
    return run_budget_ui_test(output_dir, (args.width, args.height))


def _simulation_config(args: argparse.Namespace):
    from src.simulation.runner import SimulationRunConfig

    project_root = args.project_root.resolve()
    run_id = args.run_id or datetime.now().strftime("sim-%Y%m%d-%H%M%S")
    output_dir = (
        _resolved_path(project_root, args.output)
        if args.output
        else None
    )
    action_script = (
        _resolved_path(project_root, args.actions)
        if args.actions
        else None
    )
    return SimulationRunConfig(
        project_root=project_root,
        active_mods=_split_names([args.mods]),
        save_name=args.save,
        player_tag=args.player,
        output_dir=output_dir,
        run_id=run_id,
        years=args.years,
        days=args.days,
        snapshot_interval_days=args.snapshot_interval,
        diagnostics_interval_days=args.diagnostics_interval,
        action_script_path=action_script,
        random_seed=args.seed,
        export_final_tables=not args.no_export_tables,
        fail_on_error_diagnostics=args.fail_on_diagnostics,
    )


def _split_names(values: Sequence[str]) -> tuple[str, ...]:
    names: list[str] = []
    for value in values:
        names.extend(
            part.strip()
            for part in str(value).split(",")
            if part.strip()
        )
    return tuple(dict.fromkeys(names))


def _resolved_path(project_root: Path, path: Path) -> Path:
    return (
        path.resolve()
        if path.is_absolute()
        else (project_root / path).resolve()
    )
