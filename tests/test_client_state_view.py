from __future__ import annotations

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
