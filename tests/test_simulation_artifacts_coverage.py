import json

import polars as pl

from src.shared.state import GameState
from src.simulation.artifacts import SimulationArtifactWriter


def test_artifact_writer_persists_run_metadata_timeline_snapshot_and_tables(tmp_path):
    writer = SimulationArtifactWriter(tmp_path / "run")

    writer.write_run_config({"seed": 7})
    writer.append_timeline({"step": 1, "event": "started"})
    writer.append_timeline({"step": 2, "event": "finished"})
    snapshot = writer.write_snapshot({"step": 2}, "final")
    report = writer.write_final_report({"success": True})
    tables = writer.write_state_tables(
        GameState(tables={"countries": pl.DataFrame({"id": ["USA"]})}),
        "final",
    )

    assert json.loads((tmp_path / "run" / "run_config.json").read_text()) == {"seed": 7}
    assert [
        json.loads(line)
        for line in (tmp_path / "run" / "timeline.jsonl").read_text().splitlines()
    ] == [
        {"step": 1, "event": "started"},
        {"step": 2, "event": "finished"},
    ]
    assert json.loads(snapshot.read_text()) == {"step": 2}
    assert json.loads(report.read_text()) == {"success": True}
    assert json.loads((tables / "countries.jsonl").read_text()) == {"id": "USA"}
