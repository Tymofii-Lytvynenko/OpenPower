from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from src.simulation.runner import (
    HeadlessSimulationRunner,
    SimulationRunConfig,
    SimulationRunReport,
)
from src.simulation.serialization import write_json


@dataclass(frozen=True)
class SimulationComparisonReport:
    output_dir: Path
    report_path: Path
    matched: bool
    fingerprints: tuple[str, ...]
    runs: tuple[SimulationRunReport, ...]


class DeterminismComparisonRunner:
    def __init__(
        self,
        config: SimulationRunConfig,
        *,
        runs: int = 2,
        output_dir: Path | None = None,
    ):
        if runs < 2:
            raise ValueError("Determinism comparison requires at least two runs.")
        self.config = config
        self.runs = int(runs)
        self.output_dir = (
            output_dir.resolve()
            if output_dir is not None
            else (
                config.project_root
                / "user_data"
                / "simulations"
                / f"compare-{config.run_id}"
            ).resolve()
        )

    def run(self) -> SimulationComparisonReport:
        run_reports: list[SimulationRunReport] = []
        for index in range(1, self.runs + 1):
            run_id = f"{self.config.run_id}-run-{index:02d}"
            run_config = replace(
                self.config,
                run_id=run_id,
                output_dir=self.output_dir / "runs" / run_id,
            )
            run_reports.append(HeadlessSimulationRunner(run_config).run())

        fingerprints = tuple(report.state_fingerprint for report in run_reports)
        matched = (
            not any(report.failed for report in run_reports)
            and len(set(fingerprints)) == 1
        )
        report_path = self.output_dir / "comparison.json"
        write_json(
            report_path,
            {
                "matched": matched,
                "fingerprints": fingerprints,
                "runs": [
                    {
                        "run_id": report.run_id,
                        "failed": report.failed,
                        "failure_reasons": report.failure_reasons,
                        "final_report_path": report.final_report_path,
                        "state_fingerprint": report.state_fingerprint,
                    }
                    for report in run_reports
                ],
            },
        )
        return SimulationComparisonReport(
            output_dir=self.output_dir,
            report_path=report_path,
            matched=matched,
            fingerprints=fingerprints,
            runs=tuple(run_reports),
        )
