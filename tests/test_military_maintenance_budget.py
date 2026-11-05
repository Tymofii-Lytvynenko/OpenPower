from __future__ import annotations

import unittest

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.economy.budget_system import BudgetSystem
from modules.base.systems.economy.unit_upkeep import readiness_upkeep_by_country, unit_upkeep_by_id
from src.shared.events import EventRealSecond
from src.shared.state import GameState


_SECONDS_PER_YEAR = 365.25 * 24 * 60 * 60


def test_country_upkeep_aggregates_readiness_and_design_costs():
    state = GameState(tables={
        "units": pl.DataFrame([
            {"owner": "AAA", "strength": 10, "readiness_status": "ready", "design_id": "a"},
            {"owner": "AAA", "strength": 30, "readiness_status": "parked", "design_id": "b"},
            {"owner": "BBB", "strength": 0, "readiness_status": "ready", "design_id": "a"},
        ]),
        "unit_designs": pl.DataFrame([
            {"id": "a", "maintenance_cost": 100.0},
            {"id": "b", "maintenance_cost": 5.0},
        ]),
    })
    rows = {row["id"]: row for row in readiness_upkeep_by_country(state, {"ready": 2.0, "parked": 0.5}).to_dicts()}
    assert rows["AAA"]["_readiness_upkeep_factor"] == 0.875
    assert rows["AAA"]["_design_maintenance"] == 1150.0
    assert rows["BBB"]["_readiness_upkeep_factor"] == 1.0
    assert rows["BBB"]["_design_maintenance"] == 0.0


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

    def test_per_unit_breakdown_matches_budget_formula_and_readiness_factor(self) -> None:
        state = self._state()

        self.assertEqual(unit_upkeep_by_id(state), {"USA-fighter-001": 5_001_000.0})

        state.globals["military_readiness_upkeep_factors"] = {"ready": 9.0}
        self.assertEqual(unit_upkeep_by_id(state), {"USA-fighter-001": 10_001_000.0})

    def test_budget_and_unit_estimate_normalize_readiness_identically(self) -> None:
        state = self._state()
        state.update_table("units", state.get_table("units").with_columns(
            pl.lit(" READY ").alias("readiness_status")
        ))
        state.globals["military_readiness_upkeep_factors"] = {"ready": 2.0}
        estimated = sum(unit_upkeep_by_id(state).values())
        state.events = [EventRealSecond(_SECONDS_PER_YEAR, False)]

        BudgetSystem().update(state, 0.0)

        actual = 20_000_000.0 - state.get_table("countries")["money_reserves"][0]
        self.assertEqual(actual, estimated)

    def test_budget_and_unit_estimate_ignore_nonfinite_design_costs(self) -> None:
        for cost in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(cost=cost):
                state = self._state()
                state.update_table("unit_designs", state.get_table("unit_designs").with_columns(
                    pl.lit(cost).alias("maintenance_cost")
                ))
                estimated = sum(unit_upkeep_by_id(state).values())
                state.events = [EventRealSecond(_SECONDS_PER_YEAR, False)]

                BudgetSystem().update(state, 0.0)

                actual = 20_000_000.0 - state.get_table("countries")["money_reserves"][0]
                self.assertEqual(actual, estimated)

    def test_budget_and_unit_estimate_ignore_nonfinite_unit_strength(self) -> None:
        for strength in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(strength=strength):
                state = self._state()
                units = state.get_table("units").with_columns(pl.col("strength").cast(pl.Float64))
                invalid = units.with_columns(
                    pl.lit("invalid-strength").alias("id"),
                    pl.lit(strength).alias("strength"),
                )
                state.update_table("units", pl.concat([units, invalid]))
                state.globals["military_readiness_upkeep_factors"] = {"ready": 2.0}
                estimated = sum(unit_upkeep_by_id(state).values())
                state.events = [EventRealSecond(_SECONDS_PER_YEAR, False)]

                BudgetSystem().update(state, 0.0)

                actual = 20_000_000.0 - state.get_table("countries")["money_reserves"][0]
                self.assertEqual(actual, estimated)

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
