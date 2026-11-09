import polars as pl

from modules.base.systems.world.territory_system import TerritorySystem
from src.shared.actions import ActionOccupyRegion
from src.shared.state import GameState


def test_occupation_fills_missing_controller_from_owner_then_updates_controller():
    state = GameState(
        tables={"regions": pl.DataFrame({"id": [1], "owner": ["POL"]})}
    )
    state.current_actions = [ActionOccupyRegion("server", 1, "UKR")]

    TerritorySystem().update(state, 0.0)

    regions = state.get_table("regions")
    assert regions["owner"].to_list() == ["POL"]
    assert regions["controller"].to_list() == ["UKR"]
