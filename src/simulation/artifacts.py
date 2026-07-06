from __future__ import annotations

from pathlib import Path
from typing import Any

from src.shared.state import GameState
from src.simulation.serialization import dumps_line, write_json


class SimulationArtifactWriter:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.snapshots_dir = run_dir / "snapshots"
        self.tables_dir = run_dir / "tables"
        self.timeline_path = run_dir / "timeline.jsonl"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

    def write_run_config(self, config_payload: dict[str, Any]) -> None:
        write_json(self.run_dir / "run_config.json", config_payload)

    def append_timeline(self, record: dict[str, Any]) -> None:
        with self.timeline_path.open("ab") as handle:
            handle.write(dumps_line(record))
            handle.write(b"\n")

    def write_snapshot(self, snapshot: dict[str, Any], label: str) -> Path:
        path = self.snapshots_dir / f"{label}.json"
        write_json(path, snapshot)
        return path

    def write_final_report(self, report: dict[str, Any]) -> Path:
        path = self.run_dir / "final_report.json"
        write_json(path, report)
        return path

    def write_state_tables(self, state: GameState, label: str) -> Path:
        target_dir = self.tables_dir / label
        target_dir.mkdir(parents=True, exist_ok=True)
        for table_name, frame in sorted(state.tables.items()):
            table_path = target_dir / f"{table_name}.jsonl"
            with table_path.open("wb") as handle:
                for row in frame.iter_rows(named=True):
                    handle.write(dumps_line(row))
                    handle.write(b"\n")
        return target_dir