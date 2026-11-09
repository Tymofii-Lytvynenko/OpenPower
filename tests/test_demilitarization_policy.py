import polars as pl

from modules.base.systems.world.demilitarization_policy import DemilitarizationPolicy
from src.shared.state import GameState


def test_current_strength_falls_back_to_represented_units_without_declared_counts():
    state = GameState(
        tables={
            "units": pl.DataFrame(
                {
                    "owner": ["AAA", "AAA", "BBB"],
                    "strength": [10, 15, 50],
                }
            ),
            "countries": pl.DataFrame({"name": ["AAA"]}),
        }
    )
    policy = DemilitarizationPolicy()

    assert policy.current_strength(state, "aaa") == 25

    state.tables["countries"] = pl.DataFrame({"id": ["BBB"]})

    assert policy.current_strength(state, "AAA") == 25


def test_committed_production_counts_only_active_country_orders():
    state = GameState(tables={})
    orders = iter(
        [
            {"country_id": " aaa ", "quantity": 3, "status": "queued"},
            {"country_id": "AAA", "quantity": 5, "status": "COMPLETED"},
            {"country_id": "BBB", "quantity": 20, "status": "queued"},
            {"country_id": "AAA", "quantity": -2, "status": "in_production"},
            {"country_id": "AAA", "quantity": 9, "status": "cancelled"},
        ]
    )

    assert DemilitarizationPolicy().committed_production(state, "AAA", orders) == 8
