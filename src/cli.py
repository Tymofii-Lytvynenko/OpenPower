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

    return parser


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
