import unittest

import polars as pl

from modules.base.systems.military.covert_operations_system import CovertOperationsSystem
from modules.base.systems.military.covert_resource_effects import (
    apply_resource_production_delta,
    resource_production_total,
)
from src.shared.state import GameState


class CovertResolutionEffectsTest(unittest.TestCase):
    def _state(self) -> GameState:
        return GameState(tables={
            "regions": pl.DataFrame({
                "id": [1, 2],
                "owner": ["USA", "CAN"],
                "controller": ["USA", "CAN"],
            }),
            "regional_production": pl.DataFrame({
                "id": ["rp-usa-cereals", "rp-can-cereals"],
                "country_id": ["USA", "CAN"],
                "region_id": [1, 2],
                "game_resource_id": ["cereals", "cereals"],
                "domestic_production": [100.0, 200.0],
            }),
            "domestic_production": pl.DataFrame({
                "country_id": ["USA", "CAN"],
                "game_resource_id": ["cereals", "cereals"],
                "domestic_production": [100.0, 200.0],
            }),
            "units": pl.DataFrame({
                "id": ["can-ground", "can-air"],
                "owner": ["CAN", "CAN"],
                "design_id": ["design-ground", "design-air"],
                "strength": [100, 100],
            }),
            "unit_designs": pl.DataFrame({
                "id": ["design-ground", "design-air"],
                "domain": ["land", "air"],
            }),
        })

    def test_civilian_sabotage_reduces_only_the_selected_resource(self):
        state = self._state()
        output = {}

        CovertOperationsSystem()._apply_mission_effect(
            state,
            {"mission_type": "civilian_sabotage", "target_resource_id": "cereals", "complexity": "high"},
            {"id": "CAN", "economic_health": 0.8},
            output,
            [],
            [],
            "",
            outcome="success",
        )

        regional = state.get_table("regional_production")
        self.assertEqual(regional.filter(pl.col("country_id") == "CAN")["domestic_production"][0], 196.0)
        self.assertEqual(regional.filter(pl.col("country_id") == "USA")["domestic_production"][0], 100.0)
        national = state.get_table("domestic_production")
        self.assertEqual(national.filter(pl.col("country_id") == "CAN")["domestic_production"][0], 196.0)
        self.assertEqual(output["resource_production_effect"]["delta"], -4.0)

    def test_civilian_espionage_adds_selected_target_output_to_owner(self):
        state = self._state()
        output = {}

        CovertOperationsSystem()._apply_mission_effect(
            state,
            {
                "mission_type": "civilian_espionage",
                "owner_country_id": "USA",
                "target_resource_id": "cereals",
                "complexity": "high",
            },
            {"id": "CAN"},
            output,
            [],
            [],
            "",
            outcome="success",
        )

        regional = state.get_table("regional_production")
        self.assertEqual(regional.filter(pl.col("country_id") == "USA")["domestic_production"][0], 108.0)
        self.assertEqual(regional.filter(pl.col("country_id") == "CAN")["domestic_production"][0], 200.0)
        self.assertEqual(output["resource_production_effect"]["delta"], 8.0)

    def test_military_sabotage_honors_the_selected_openpower_domain(self):
        state = self._state()

        CovertOperationsSystem()._apply_mission_effect(
            state,
            {
                "mission_type": "military_sabotage",
                "target_unit_category": "air",
                "complexity": "high",
            },
            {"id": "CAN"},
            {},
            [],
            [],
            "",
            outcome="success",
        )

        units = state.get_table("units")
        self.assertEqual(units.filter(pl.col("id") == "can-air")["strength"][0], 90)
        self.assertEqual(units.filter(pl.col("id") == "can-ground")["strength"][0], 100)

    def test_resource_effects_do_not_create_production_without_an_existing_basis(self):
        state = GameState(tables={
            "regional_production": pl.DataFrame(schema={
                "id": pl.Utf8,
                "country_id": pl.Utf8,
                "region_id": pl.Int32,
                "game_resource_id": pl.Utf8,
                "domestic_production": pl.Float64,
            }),
            "domestic_production": pl.DataFrame({
                "country_id": ["USA"],
                "game_resource_id": ["cereals"],
                "domestic_production": [0.0],
            }),
        })

        self.assertEqual(resource_production_total(state, "USA", "cereals"), 0.0)
        self.assertEqual(apply_resource_production_delta(state, "USA", "cereals", 10.0), 0.0)
        self.assertEqual(state.get_table("domestic_production")["domestic_production"][0], 0.0)

    def test_uncontrolled_regional_rows_do_not_fall_back_to_national_output(self):
        state = GameState(tables={
            "regions": pl.DataFrame({"id": [2], "owner": ["CAN"], "controller": ["USA"]}),
            "regional_production": pl.DataFrame({
                "id": ["rp-can-cereals"],
                "country_id": ["CAN"],
                "region_id": [2],
                "game_resource_id": ["cereals"],
                "domestic_production": [200.0],
            }),
            "domestic_production": pl.DataFrame({
                "country_id": ["CAN"],
                "game_resource_id": ["cereals"],
                "domestic_production": [200.0],
            }),
        })

        self.assertEqual(resource_production_total(state, "CAN", "cereals"), 0.0)
        self.assertEqual(apply_resource_production_delta(state, "CAN", "cereals", -2.0), 0.0)
        self.assertEqual(state.get_table("domestic_production")["domestic_production"][0], 200.0)
        self.assertEqual(state.get_table("regional_production")["domestic_production"][0], 200.0)

    def test_zero_regional_output_does_not_fall_back_to_positive_national_total(self):
        state = GameState(tables={
            "regions": pl.DataFrame({"id": [2], "owner": ["CAN"], "controller": ["CAN"]}),
            "regional_production": pl.DataFrame({
                "id": ["rp-can-cereals"],
                "country_id": ["CAN"],
                "region_id": [2],
                "game_resource_id": ["cereals"],
                "domestic_production": [0.0],
            }),
            "domestic_production": pl.DataFrame({
                "country_id": ["CAN"],
                "game_resource_id": ["cereals"],
                "domestic_production": [200.0],
            }),
        })

        self.assertEqual(resource_production_total(state, "CAN", "cereals"), 0.0)
        self.assertEqual(apply_resource_production_delta(state, "CAN", "cereals", 2.0), 0.0)
        self.assertEqual(state.get_table("domestic_production")["domestic_production"][0], 200.0)

    def test_missing_controller_column_uses_region_owner(self):
        state = GameState(tables={
            "regions": pl.DataFrame({"id": [2], "owner": ["CAN"]}),
            "regional_production": pl.DataFrame({
                "id": ["rp-can-cereals"],
                "country_id": ["CAN"],
                "region_id": [2],
                "game_resource_id": ["cereals"],
                "domestic_production": [200.0],
            }),
            "domestic_production": pl.DataFrame({
                "country_id": ["CAN"],
                "game_resource_id": ["cereals"],
                "domestic_production": [200.0],
            }),
        })

        self.assertEqual(resource_production_total(state, "CAN", "cereals"), 200.0)
        self.assertEqual(apply_resource_production_delta(state, "CAN", "cereals", -2.0), -2.0)
        self.assertEqual(state.get_table("regional_production")["domestic_production"][0], 198.0)

    def test_civilian_sabotage_does_not_change_an_uncontrolled_resource_fallback(self):
        state = GameState(tables={
            "regions": pl.DataFrame({"id": [2], "owner": ["CAN"], "controller": ["USA"]}),
            "regional_production": pl.DataFrame({
                "id": ["rp-can-cereals"],
                "country_id": ["CAN"],
                "region_id": [2],
                "game_resource_id": ["cereals"],
                "domestic_production": [200.0],
            }),
            "domestic_production": pl.DataFrame({
                "country_id": ["CAN"],
                "game_resource_id": ["cereals"],
                "domestic_production": [200.0],
            }),
        })
        target = {"id": "CAN", "economic_health": 0.8}

        CovertOperationsSystem()._apply_mission_effect(
            state,
            {"mission_type": "civilian_sabotage", "target_resource_id": "cereals", "complexity": "medium"},
            target,
            {},
            [],
            [],
            "",
            outcome="success",
        )

        self.assertEqual(target["economic_health"], 0.8)
        self.assertEqual(state.get_table("domestic_production")["domestic_production"][0], 200.0)

    def test_resource_delta_follows_each_controlled_regions_production_share(self):
        state = GameState(tables={
            "regions": pl.DataFrame({
                "id": [2, 3],
                "owner": ["CAN", "CAN"],
                "controller": ["CAN", "CAN"],
            }),
            "regional_production": pl.DataFrame({
                "id": ["rp-can-cereals-a", "rp-can-cereals-b"],
                "country_id": ["CAN", "CAN"],
                "region_id": [2, 3],
                "game_resource_id": ["cereals", "cereals"],
                "domestic_production": [50.0, 150.0],
            }),
            "domestic_production": pl.DataFrame({
                "country_id": ["CAN"],
                "game_resource_id": ["cereals"],
                "domestic_production": [200.0],
            }),
        })

        self.assertEqual(apply_resource_production_delta(state, "CAN", "cereals", -2.0), -2.0)
        rows = state.get_table("regional_production").sort("region_id")
        self.assertEqual(rows["domestic_production"].to_list(), [49.5, 148.5])
        self.assertEqual(state.get_table("domestic_production")["domestic_production"][0], 198.0)


if __name__ == "__main__":
    unittest.main()
