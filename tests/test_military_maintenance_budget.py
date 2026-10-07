from __future__ import annotations

import unittest

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.economy.budget_system import BudgetSystem
from src.shared.events import EventRealSecond
from src.shared.state import GameState


_SECONDS_PER_YEAR = 365.25 * 24 * 60 * 60


class MilitaryMaintenanceBudgetTest(unittest.TestCase):
    def test_design_maintenance_uses_existing_annual_budget_contract(self) -> None:
        state = self._state()
        state.events = [EventRealSecond(_SECONDS_PER_YEAR, False)]

        BudgetSystem().update(state, 0.0)

        self.assertEqual(state.get_table("countries")["money_reserves"][0], 14_999_000.0)

    def test_readiness_upkeep_factors_are_bounded_and_scale_existing_upkeep(self) -> None:
        state = self._state()
        state.globals["military_readiness_upkeep_factors"] = {"ready": 9.0}
        state.events = [EventRealSecond(_SECONDS_PER_YEAR, False)]

        BudgetSystem().update(state, 0.0)

        self.assertEqual(state.get_table("countries")["money_reserves"][0], 9_999_000.0)

    def _state(self) -> GameState:
        state = GameState(tables={
            "countries": pl.DataFrame({
                "id": ["USA"], "gdp": [0.0], "human_dev": [1.0],
                "personal_income_tax_rate": [0.0], "military_count": [10],
                "money_reserves": [20_000_000.0], "corruption_index": [0.0],
            }),
            "units": pl.DataFrame({
                "id": ["USA-fighter-001"], "owner": ["USA"], "strength": [10],
                "readiness_status": ["ready"], "design_id": ["fighter-design"],
            }),
            "unit_designs": pl.DataFrame({
                "id": ["fighter-design"], "country_id": ["USA"], "maintenance_cost": [100.0],
            }),
        })
        ensure_base_tables(state)
        return state


if __name__ == "__main__":
    unittest.main()
