from __future__ import annotations

import unittest

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.demographics.population_system import PopulationSystem
from modules.base.systems.economy.internal_economy_system import InternalEconomySystem
from modules.base.systems.military.military_system import MilitarySystem
from modules.base.systems.military.covert_operations_system import CovertOperationsSystem
from modules.base.systems.world.infrastructure_system import InfrastructureSystem
from src.core.map.geo import GeoCoordinate
from tests.test_regional_infrastructure_fixtures import build_infrastructure_state


class InfrastructureIntegrationTest(unittest.TestCase):
    def test_materialized_transport_capacity_changes_route_duration_by_region(self):
        state = build_infrastructure_state()
        ensure_base_tables(state)
        InfrastructureSystem().update(state, 0.0)
        state.globals["military_infrastructure_duration_coefficient"] = 0.5
        regions = state.get_table("regions")
        strong = regions.filter(pl.col("id") == 202).to_dicts()[0]
        weak = regions.filter(pl.col("id") == 303).to_dicts()[0]
        locations = {101: GeoCoordinate(0.0, 0.0), 202: GeoCoordinate(30.0, 0.0), 303: GeoCoordinate(30.0, 0.0)}
        unit = {"id": "USA-army-001", "owner": "USA", "unit_type": "army", "strength": 100}
        system = MilitarySystem()

        strong_duration = system._route_segment_minutes_for_unit(
            {"id": 101, "owner": "USA"}, strong, locations, unit, state
        )
        weak_duration = system._route_segment_minutes_for_unit(
            {"id": 101, "owner": "USA"}, weak, locations, unit, state
        )

        self.assertGreater(strong["transport_access"], weak["transport_access"])
        self.assertLess(strong_duration, weak_duration)

    def test_regional_telecom_capacity_improves_military_command_coordination(self):
        state = build_infrastructure_state()
        ensure_base_tables(state)
        InfrastructureSystem().update(state, 0.0)
        state.globals["military_infrastructure_duration_coefficient"] = 0.0
        state.globals["military_telecom_coordination_coefficient"] = 0.5
        locations = {101: GeoCoordinate(0.0, 0.0), 202: GeoCoordinate(30.0, 0.0)}
        source = {"id": 101, "owner": "USA"}
        unit = {"id": "USA-army-001", "owner": "USA", "unit_type": "army", "strength": 100}
        system = MilitarySystem()
        low_telecom = {"id": 202, "owner": "CAN", "infrastructure": 0.0, "telecom_capacity": 0.0}
        high_telecom = {**low_telecom, "telecom_capacity": 1.0}

        low_duration = system._route_segment_minutes_for_unit(
            source, low_telecom, locations, unit, state
        )
        high_duration = system._route_segment_minutes_for_unit(
            source, high_telecom, locations, unit, state
        )

        self.assertGreater(low_duration, high_duration)

    def test_strategic_damage_is_attributed_once_and_does_not_spill_to_other_regions(self):
        state = build_infrastructure_state()
        ensure_base_tables(state)
        system = InfrastructureSystem()
        system.update(state, 0.0)
        before = state.get_table("regional_infrastructure")
        state.update_table(
            "strategic_impacts",
            pl.DataFrame(
                [
                    {
                        "id": "impact-transport-1",
                        "region_id": 101,
                        "category": "infrastructure",
                        "severity": 0.25,
                    }
                ],
                schema=state.get_table("strategic_impacts").schema,
            ),
        )

        system.update(state, 0.0)

        damaged = state.get_table("regional_infrastructure")
        target = damaged.filter(
            (pl.col("region_id") == 101) & (pl.col("category") == "transport")
        )["capacity"][0]
        unaffected_before = before.filter(
            (pl.col("region_id") == 202) & (pl.col("category") == "transport")
        )["capacity"][0]
        unaffected_after = damaged.filter(
            (pl.col("region_id") == 202) & (pl.col("category") == "transport")
        )["capacity"][0]
        system.update(state, 0.0)
        repeated = state.get_table("regional_infrastructure").filter(
            (pl.col("region_id") == 101) & (pl.col("category") == "transport")
        )["capacity"][0]

        self.assertLess(target, before.filter(
            (pl.col("region_id") == 101) & (pl.col("category") == "transport")
        )["capacity"][0])
        self.assertEqual(unaffected_after, unaffected_before)
        self.assertEqual(repeated, target)
        self.assertEqual(state.get_table("infrastructure_damage_records").height, 1)

    def test_industrial_access_bounds_country_production_without_creating_output(self):
        state = build_infrastructure_state()
        ensure_base_tables(state)
        InfrastructureSystem().update(state, 0.0)
        state.update_table(
            "domestic_production",
            pl.DataFrame(
                {
                    "country_id": ["USA", "CAN"],
                    "game_resource_id": ["steel", "steel"],
                    "domestic_production": [1_000.0, 1_000.0],
                    "is_legal": [True, True],
                    "is_gov_controlled": [False, False],
                    "tax_rate": [0.0, 0.0],
                }
            ),
        )

        InternalEconomySystem()._process_economy(state, 0.0)

        countries = state.get_table("countries").sort("id")
        self.assertGreater(countries.filter(pl.col("id") == "USA")["gdp"][0],
                           countries.filter(pl.col("id") == "CAN")["gdp"][0])
        self.assertGreater(countries["gdp"].min(), 0.0)

    def test_regional_service_capacity_modifies_demographic_health_without_spreading_globally(self):
        def resulting_older_population(health_capacity: float) -> int:
            state = build_infrastructure_state()
            regions = state.get_table("regions").with_columns(
                pl.when(pl.col("id") == 101)
                .then(health_capacity)
                .otherwise(pl.col("health_capacity"))
                .alias("health_capacity"),
                pl.lit(0, dtype=pl.Int64).alias("pop_14"),
                pl.lit(0, dtype=pl.Int64).alias("pop_15_64"),
                pl.when(pl.col("id") == 101)
                .then(100_000)
                .otherwise(0)
                .cast(pl.Int64)
                .alias("pop_65"),
            )
            state.update_table("regions", regions)
            state.update_table(
                "countries",
                state.get_table("countries").with_columns(
                    pl.lit(80.0).alias("life_expectancy"),
                    pl.lit(0.0).alias("fertility_rate"),
                ),
            )
            ensure_base_tables(state)
            InfrastructureSystem().update(state, 0.0)
            PopulationSystem()._apply_tfr_growth(state, 365.25)
            return int(state.get_table("regions").filter(pl.col("id") == 101)["pop_65"][0])

        higher_capacity_population = resulting_older_population(1.0)
        lower_capacity_population = resulting_older_population(0.1)

        self.assertGreater(lower_capacity_population, 0)
        self.assertLess(lower_capacity_population, higher_capacity_population)

    def test_target_region_telecom_capacity_changes_intelligence_confidence(self):
        state = build_infrastructure_state()
        ensure_base_tables(state)
        InfrastructureSystem().update(state, 0.0)
        cell = {
            "id": "cell-1",
            "country_id": "USA",
            "target_country_id": "CAN",
            "skill_level": "Veteran",
            "concealment": 0.8,
            "readiness": 0.9,
            "communications_ready": True,
        }
        mission = {
            "id": "mission-1",
            "owner_country_id": "USA",
            "target_country_id": "CAN",
            "mission_type": "military_espionage",
            "preparation_required": 1440.0,
            "resolves_at_minute": 2400,
        }
        target = state.get_table("countries").filter(pl.col("id") == "CAN").to_dicts()[0]
        state.update_table(
            "covert_cell_routes",
            pl.DataFrame(
                [
                    {
                        "cell_id": "cell-1",
                        "owner_country_id": "USA",
                        "destination_region_id": 202,
                        "status": "arrived",
                    }
                ],
                schema=state.get_table("covert_cell_routes").schema,
            ),
        )
        system = CovertOperationsSystem()
        low_capacity = system._resolve(state, cell, mission, target, [cell], [])[3]

        state.update_table(
            "regions",
            state.get_table("regions").with_columns(
                pl.when(pl.col("id") == 202)
                .then(1.0)
                .otherwise(pl.col("telecom_capacity"))
                .alias("telecom_capacity")
            ),
        )
        high_capacity = system._resolve(state, cell, mission, target, [cell], [])[3]

        self.assertGreater(high_capacity, low_capacity)



if __name__ == "__main__":
    unittest.main()
