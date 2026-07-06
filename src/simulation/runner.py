from __future__ import annotations

import random
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.server.session import GameSession
from src.shared.actions import ActionSetGameSpeed
from src.shared.config import GameConfig
from src.simulation.actions import ActionScript
from src.simulation.artifacts import SimulationArtifactWriter
from src.simulation.diagnostics import DiagnosticIssue, SimulationDiagnostics
from src.simulation.serialization import to_plain_data
from src.simulation.snapshots import StateSnapshotBuilder


def _default_run_id() -> str:
    return datetime.now().strftime("sim-%Y%m%d-%H%M%S")


@dataclass(frozen=True)
class SimulationRunConfig:
    project_root: Path
    save_name: str | None = None
    player_tag: str | None = None
    output_dir: Path | None = None
    run_id: str = field(default_factory=_default_run_id)
    years: int = 0
    days: int = 30
    speed_level: int = 5
    day_delta_seconds: float = 0.6
    snapshot_interval_days: int = 30
    diagnostics_interval_days: int = 1
    table_sample_limit: int = 12
    action_script_path: Path | None = None
    random_seed: int | None = 1
    export_final_tables: bool = True
    export_checkpoint_tables: bool = False
    engine_dev_mode: bool = False
    fail_on_system_errors: bool = True
    fail_on_error_diagnostics: bool = False

    @property
    def total_days(self) -> int:
        return max(0, int(self.years) * 365 + int(self.days))

    @property
    def resolved_output_dir(self) -> Path:
        if self.output_dir is not None:
            return self.output_dir.resolve()
        return (self.project_root / "user_data" / "simulations" / self.run_id).resolve()

    def to_payload(self) -> dict[str, Any]:
        return to_plain_data({
            "project_root": self.project_root.resolve(),
            "save_name": self.save_name,
            "player_tag": self.player_tag,
            "output_dir": self.resolved_output_dir,
            "run_id": self.run_id,
            "years": self.years,
            "days": self.days,
            "total_days": self.total_days,
            "speed_level": self.speed_level,
            "day_delta_seconds": self.day_delta_seconds,
            "snapshot_interval_days": self.snapshot_interval_days,
            "diagnostics_interval_days": self.diagnostics_interval_days,
            "table_sample_limit": self.table_sample_limit,
            "action_script_path": self.action_script_path,
            "random_seed": self.random_seed,
            "export_final_tables": self.export_final_tables,
            "export_checkpoint_tables": self.export_checkpoint_tables,
            "engine_dev_mode": self.engine_dev_mode,
            "fail_on_system_errors": self.fail_on_system_errors,
            "fail_on_error_diagnostics": self.fail_on_error_diagnostics,
        })


@dataclass(frozen=True)
class SimulationRunReport:
    run_id: str
    output_dir: Path
    final_report_path: Path
    timeline_path: Path
    snapshots_written: list[Path]
    table_exports: list[Path]
    failed: bool
    failure_reasons: list[str]
    issue_counts: dict[str, int]
    final_snapshot: dict[str, Any]

class HeadlessSimulationRunner:
    def __init__(self, config: SimulationRunConfig):
        self.config = config
        self.diagnostics = SimulationDiagnostics()
        self.snapshot_builder = StateSnapshotBuilder(config.table_sample_limit)

    def run(self) -> SimulationRunReport:
        if self.config.random_seed is not None:
            random.seed(self.config.random_seed)

        game_config = GameConfig(self.config.project_root)
        game_config.dev_mode = self.config.engine_dev_mode
        session = GameSession.create_headless(
            game_config,
            save_name=self.config.save_name,
            player_tag=self.config.player_tag,
        )
        session.state.time.speed_level = self.config.speed_level
        session.state.globals["game_speed"] = self.config.speed_level

        expected_player_tag = self.config.player_tag or session.state.globals.get("player_tag")
        action_script = ActionScript.from_path(self.config.action_script_path) if self.config.action_script_path else ActionScript.empty()
        writer = SimulationArtifactWriter(self.config.resolved_output_dir)
        writer.write_run_config(self.config.to_payload())

        start = time.perf_counter()
        snapshots_written: list[Path] = []
        table_exports: list[Path] = []
        issue_totals: Counter[str] = Counter()
        failure_reasons: list[str] = []
        issue_examples: dict[str, DiagnosticIssue] = {}

        initial_issues = self._inspect(session, expected_player_tag, issue_totals, issue_examples)
        initial_snapshot = self.snapshot_builder.build_snapshot(session.state, 0, 0.0, initial_issues)
        snapshots_written.append(writer.write_snapshot(initial_snapshot, "day_00000"))
        writer.append_timeline(self.snapshot_builder.build_timeline_record(session.state, 0, 0.0, initial_issues))

        for day in range(1, self.config.total_days + 1):
            if day == 1:
                session.receive_action(ActionSetGameSpeed("simulation", self.config.speed_level))

            next_tick = int(session.state.globals.get("tick", 0)) + 1
            next_minute = int(session.state.time.total_minutes + self._minutes_per_step())
            for action in action_script.actions_for(day=day, tick=next_tick, minute=next_minute):
                session.receive_action(action)

            session.tick(self.config.day_delta_seconds)
            elapsed = time.perf_counter() - start

            issues = self._inspect_if_due(session, expected_player_tag, day, issue_totals, issue_examples)
            timeline_record = self.snapshot_builder.build_timeline_record(session.state, day, elapsed, issues)
            writer.append_timeline(timeline_record)

            if self._should_write_snapshot(day):
                if not issues:
                    issues = self._inspect(session, expected_player_tag, issue_totals, issue_examples)
                snapshot = self.snapshot_builder.build_snapshot(session.state, day, elapsed, issues)
                label = f"day_{day:05d}"
                snapshots_written.append(writer.write_snapshot(snapshot, label))
                if self.config.export_checkpoint_tables:
                    table_exports.append(writer.write_state_tables(session.state, label))
        final_issues = self._inspect(session, expected_player_tag, issue_totals, issue_examples)
        final_snapshot = self.snapshot_builder.build_snapshot(
            session.state,
            self.config.total_days,
            time.perf_counter() - start,
            final_issues,
        )
        snapshots_written.append(writer.write_snapshot(final_snapshot, "final"))
        if self.config.export_final_tables:
            table_exports.append(writer.write_state_tables(session.state, "final"))

        failure_reasons.extend(self._failure_reasons(issue_totals))
        final_report_payload = {
            "run_id": self.config.run_id,
            "output_dir": self.config.resolved_output_dir,
            "failed": bool(failure_reasons),
            "failure_reasons": failure_reasons,
            "issue_counts": dict(issue_totals),
            "issue_examples": {code: to_plain_data(issue) for code, issue in issue_examples.items()},
            "snapshots_written": snapshots_written,
            "table_exports": table_exports,
            "timeline_path": writer.timeline_path,
            "final_snapshot": final_snapshot,
        }
        final_report_path = writer.write_final_report(final_report_payload)

        return SimulationRunReport(
            run_id=self.config.run_id,
            output_dir=self.config.resolved_output_dir,
            final_report_path=final_report_path,
            timeline_path=writer.timeline_path,
            snapshots_written=snapshots_written,
            table_exports=table_exports,
            failed=bool(failure_reasons),
            failure_reasons=failure_reasons,
            issue_counts=dict(issue_totals),
            final_snapshot=final_snapshot,
        )
    def _inspect_if_due(
        self,
        session: GameSession,
        expected_player_tag: str | None,
        day: int,
        issue_totals: Counter[str],
        issue_examples: dict[str, DiagnosticIssue],
    ) -> list[DiagnosticIssue]:
        interval = max(1, self.config.diagnostics_interval_days)
        has_system_error = any(type(event).__name__ == "EventSystemError" for event in session.state.events)
        if day % interval != 0 and not has_system_error:
            return []
        return self._inspect(session, expected_player_tag, issue_totals, issue_examples)

    def _inspect(
        self,
        session: GameSession,
        expected_player_tag: str | None,
        issue_totals: Counter[str],
        issue_examples: dict[str, DiagnosticIssue],
    ) -> list[DiagnosticIssue]:
        issues = self.diagnostics.inspect(session.state, expected_player_tag=expected_player_tag)
        for issue in issues:
            issue_totals[issue.severity] += 1
            issue_totals[f"{issue.severity}:{issue.code}"] += 1
            issue_examples.setdefault(issue.code, issue)
        return issues

    def _failure_reasons(self, issue_totals: Counter[str]) -> list[str]:
        reasons: list[str] = []
        if self.config.fail_on_system_errors and issue_totals.get("error:system_error", 0):
            reasons.append("At least one simulation system raised an error.")
        if self.config.fail_on_error_diagnostics and issue_totals.get("error", 0):
            reasons.append("Diagnostics reported at least one error.")
        return reasons

    def _should_write_snapshot(self, day: int) -> bool:
        if day == self.config.total_days:
            return True
        interval = max(1, self.config.snapshot_interval_days)
        return day % interval == 0

    def _minutes_per_step(self) -> int:
        minutes_per_second = {
            1: 30.0,
            2: 60.0,
            3: 120.0,
            4: 600.0,
            5: 2400.0,
        }.get(self.config.speed_level, 2400.0)
        return int(self.config.day_delta_seconds * minutes_per_second)