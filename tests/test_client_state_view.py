from __future__ import annotations

import polars as pl
import pytest

from src.client.client_state import ClientGameStateView, ClientPresentationState
from src.shared.state import GameState


def test_client_state_view_blocks_authoritative_writes_and_freezes_nested_data():
    state = GameState()
    state.globals["preferences"] = {"layers": ["political"]}
    state.time.total_minutes = 12
    state.table_revisions["countries"] = 1
    view = ClientGameStateView(state, {}, ClientPresentationState())

    with pytest.raises(AttributeError, match="update_table"):
        view.update_table("countries", object())
    with pytest.raises(AttributeError, match="read-only"):
        view.time.total_minutes = 13
    with pytest.raises(TypeError):
        view.globals["preferences"]["layers"][0] = "economic"
    with pytest.raises(TypeError):
        view.table_revisions["countries"] = 2
    with pytest.raises(AttributeError):
        view.time = state.time

    assert state.time.total_minutes == 12
    assert state.globals["preferences"]["layers"] == ["political"]
    assert state.table_revisions["countries"] == 1


def test_client_presentation_preferences_do_not_write_to_game_state():
    state = GameState()
    presentation = ClientPresentationState()
    view = ClientGameStateView(state, {}, presentation)

    presentation.geo_language_code = "uk"

    assert view.presentation_state.geo_language_code == "uk"
    assert "geo_language_code" not in state.globals


def test_polars_in_place_mutations_through_table_accessors_do_not_change_snapshot():
    original = pl.DataFrame({"id": [1, 2], "name": ["A", "B"]})
    state = GameState()
    state.tables["countries"] = original.clone()
    view = ClientGameStateView(state, {}, ClientPresentationState())

    view.tables["countries"].replace_column(0, pl.Series("id", [7, 8]))
    view.get_table("countries").replace_column(1, pl.Series("name", ["X", "Y"]))

    assert state.tables["countries"].equals(original)
    assert view.tables["countries"].equals(original)
    assert view.get_table("countries").equals(original)


def test_client_view_detaches_table_snapshot_from_source_dataframe():
    original = pl.DataFrame({"id": [1, 2], "name": ["A", "B"]})
    expected = original.clone()
    state = GameState()
    state.tables["countries"] = original
    view = ClientGameStateView(state, {}, ClientPresentationState())

    state.tables["countries"].replace_column(0, pl.Series("id", [7, 8]))

    assert view.tables["countries"].equals(expected)
    assert view.get_table("countries").equals(expected)


def test_other_polars_in_place_operations_are_isolated_from_table_snapshot():
    original = pl.DataFrame({"id": [1, 2], "name": ["A", "B"]})
    state = GameState()
    state.tables["countries"] = original.clone()
    view = ClientGameStateView(state, {}, ClientPresentationState())
    table = view.get_table("countries")

    table.insert_column(2, pl.Series("temporary", [True, False]))
    table.drop_in_place("temporary")
    table.extend(pl.DataFrame({"id": [3], "name": ["C"]}))

    assert state.tables["countries"].equals(original)
    assert view.tables["countries"].equals(original)
