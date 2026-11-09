import polars as pl

from modules.base.systems.world.authority_policy import (
    _player_country,
    foreign_government_change_restriction,
    player_controls_country,
)
from src.shared.state import GameState


def test_local_and_trusted_actors_resolve_through_their_authority_rules():
    state = GameState(tables={}, globals={"player_tag": "AAA"})

    assert _player_country(state, "LOCAL_PLAYER") == "AAA"
    assert player_controls_country(state, "LOCAL_PLAYER", "AAA")
    assert _player_country(state, "AI") == ""


def test_foreign_change_reports_missing_regional_control_data():
    state = GameState(
        tables={"countries": pl.DataFrame({"id": ["AAA", "BBB"]})},
        globals={"player_country_map": {"player-1": "AAA"}},
    )

    reason = foreign_government_change_restriction(state, "player-1", "BBB")

    assert reason == "Regional control data is unavailable for this country."
