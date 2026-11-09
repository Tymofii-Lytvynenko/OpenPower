import polars as pl

from src.shared.state import GameState
from src.simulation.snapshots import StateSnapshotBuilder


def test_table_summary_returns_early_for_zero_column_frames():
    summary = StateSnapshotBuilder()._table_summary(pl.DataFrame())

    assert summary["rows"] == 0
    assert summary["columns"] == 0
    assert "null_counts" not in summary


def test_country_digest_handles_missing_or_incomplete_country_data():
    builder = StateSnapshotBuilder()

    assert builder._countries_digest(GameState()) == {
        "player_country": None,
        "top_reserves": [],
        "top_gdp": [],
    }
    assert builder._player_country_row(GameState(), pl.DataFrame({"id": ["USA"]})) is None
    assert builder._player_country_row(
        GameState(globals={"player_tag": "CAN"}),
        pl.DataFrame({"id": ["USA"]}),
    ) is None
    assert builder._top_country_rows(pl.DataFrame({"id": ["USA"]}), "gdp") == []
