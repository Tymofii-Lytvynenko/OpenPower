from __future__ import annotations

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.economy.budget_system import BudgetSystem
from src.shared.actions import ActionUpdateBudget
from src.shared.state import GameState


def test_budget_system_applies_and_bounds_tax_and_sector_ratios_from_one_action():
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {"id": ["AAA"], "personal_income_tax_rate": [0.2], "budget_health_ratio": [0.5]}
            )
        }
    )
    ensure_base_tables(state)
    action = ActionUpdateBudget(
        player_id="player-1",
        country_tag="AAA",
        allocations={
            "personal_income_tax_rate": 1.4,
            "budget_health_ratio": -0.2,
        },
    )

    BudgetSystem()._handle_update_budget(state, action)

    country = state.get_table("countries").row(0, named=True)
    assert country["personal_income_tax_rate"] == 1.0
    assert country["budget_health_ratio"] == 0.0
