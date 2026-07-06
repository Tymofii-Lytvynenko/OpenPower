from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.simulation.runner import HeadlessSimulationRunner, SimulationRunConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run OpenPower without the graphical client.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--save-name", default=None)
    parser.add_argument("--player-tag", default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--years", type=int, default=0)
    parser.add_argument("--days", type=int, default=None)
    parser.add_argument("--speed-level", type=int, default=5)
    parser.add_argument("--day-delta-seconds", type=float, default=0.6)
    parser.add_argument("--snapshot-every-days", type=int, default=30)
    parser.add_argument("--diagnostics-every-days", type=int, default=1)
    parser.add_argument("--table-sample-limit", type=int, default=12)
    parser.add_argument("--actions", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--export-checkpoint-tables", action="store_true")
    parser.add_argument("--no-final-tables", action="store_true")
    parser.add_argument("--engine-dev-mode", action="store_true")
    parser.add_argument("--fail-on-diagnostics", action="store_true")
    parser.add_argument("--allow-system-errors", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    kwargs = {}
    if args.run_id:
        kwargs["run_id"] = args.run_id

    days = args.days if args.days is not None else (0 if args.years else 30)

    config = SimulationRunConfig(
        project_root=args.project_root,
        save_name=args.save_name,
        player_tag=args.player_tag,
        output_dir=args.output_dir,
        years=args.years,
        days=days,
        speed_level=args.speed_level,
        day_delta_seconds=args.day_delta_seconds,
        snapshot_interval_days=args.snapshot_every_days,
        diagnostics_interval_days=args.diagnostics_every_days,
        table_sample_limit=args.table_sample_limit,
        action_script_path=args.actions,
        random_seed=args.seed,
        export_final_tables=not args.no_final_tables,
        export_checkpoint_tables=args.export_checkpoint_tables,
        engine_dev_mode=args.engine_dev_mode,
        fail_on_system_errors=not args.allow_system_errors,
        fail_on_error_diagnostics=args.fail_on_diagnostics,
        **kwargs,
    )
    report = HeadlessSimulationRunner(config).run()

    print(f"Run: {report.run_id}")
    print(f"Output: {report.output_dir}")
    print(f"Timeline: {report.timeline_path}")
    print(f"Final report: {report.final_report_path}")
    print(f"Failed: {report.failed}")
    if report.failure_reasons:
        print("Failure reasons:")
        for reason in report.failure_reasons:
            print(f"- {reason}")
    if report.issue_counts:
        print(f"Issue counts: {report.issue_counts}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))