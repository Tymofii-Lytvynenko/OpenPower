import unittest
import json

import polars as pl

from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.shared.state import GameState


class TestMilitaryPresenter(unittest.TestCase):
    def test_unit_list_uses_presentation_clock_for_movement_progress(self):
        state = GameState(
            tables={
                "countries": pl.DataFrame({"id": ["USA"], "name": ["United States"]}),
                "regions": pl.DataFrame({"id": [1], "name": ["Origin"]}),
                "units": pl.DataFrame(
                    {
                        "id": ["unit-1"],
                        "owner": ["USA"],
                        "unit_type": ["army"],
                        "strength": [100],
                        "current_region_id": [1],
                        "departed_at_minute": [10],
                        "arrival_at_minute": [30],
                        "movement_progress": [0.1],
                        "is_moving": [True],
                        "readiness_status": ["ready"],
                        "readiness_transition_id": [""],
                    }
                ),
            }
        )

        rows = MilitaryPresenter().unit_rows(state, "USA", presentation_total_minutes=20.0)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].status, "Moving")
        self.assertAlmostEqual(rows[0].progress_pct, 50.0)

    def test_preferred_war_targets_excludes_self_allies_and_active_enemies(self):
        state = GameState(
            tables={
                "countries": pl.DataFrame(
                    {
                        "id": ["USA", "CAN", "GBR", "MEX", "BRA"],
                        "name": ["United States", "Canada", "United Kingdom", "Mexico", "Brazil"],
                    }
                ),
                "countries_relations": pl.DataFrame(
                    {
                        "source": ["USA", "USA", "USA", "USA"],
                        "target": ["CAN", "GBR", "MEX", "BRA"],
                        "value": [65.0, -90.0, -60.0, -20.0],
                    }
                ),
                "countries_treaties": pl.DataFrame(
                    {
                        "id": ["north_atlantic"],
                        "name": ["North Atlantic Treaty"],
                        "type": ["military_alliance"],
                        "members": [["USA", "CAN"]],
                    },
                    schema={
                        "id": pl.Utf8,
                        "name": pl.Utf8,
                        "type": pl.Utf8,
                        "members": pl.List(pl.Utf8),
                    },
                ),
                "countries_wars": pl.DataFrame(
                    {
                        "id": ["war-001"],
                        "side_a": [["USA"]],
                        "side_b": [["GBR"]],
                        "status": ["active"],
                    },
                    schema={
                        "id": pl.Utf8,
                        "side_a": pl.List(pl.Utf8),
                        "side_b": pl.List(pl.Utf8),
                        "status": pl.Utf8,
                    },
                ),
            }
        )

        targets = MilitaryPresenter().preferred_war_targets(state, "USA")

        self.assertEqual([row["country_tag"] for row in targets], ["MEX", "BRA"])
        self.assertEqual([row["relation_score"] for row in targets], [-60.0, -20.0])

    def test_foreign_force_estimate_uses_best_authorized_fresh_source_and_ranges(self):
        state = GameState(tables={
            "countries": pl.DataFrame({
                "id": ["USA", "CAN", "MEX"],
                "budget_telecom_ratio": [0.9, 0.9, 0.4],
            }),
            "covert_findings": pl.DataFrame({
                "id": ["old-owned", "fresh-allied", "unauthorized"],
                "owner_country_id": ["USA", "CAN", "GBR"],
                "target_country_id": ["MEX", "MEX", "MEX"],
                "category": ["military", "military", "military"],
                "value_json": [
                    json.dumps({"unit_count_estimate": 12, "unit_role_count_estimates": {"tanks": 8}}),
                    json.dumps({
                        "unit_count_estimate": 10,
                        "unit_role_count_estimates": {"fighters": 3},
                        "confidence_factors": {"observer_telecom": 0.9, "active_target_coverage": 2.0},
                    }),
                    json.dumps({"unit_count_estimate": 99, "unit_role_count_estimates": {"bombers": 99}}),
                ],
                "confidence": [0.8, 0.95, 1.0],
                "freshness": [1.0, 1.0, 1.0],
                "discovered_at_minute": [0, 90, 90],
                "expires_at_minute": [100, 190, 190],
            }),
            "treaty_effects": pl.DataFrame({
                "treaty_id": ["alliance"], "country_id": ["CAN"],
                "effect": ["military_intelligence_sharing"], "value": [1.0],
                "detail": ['["USA"]'],
            }),
        })
        state.time.total_minutes = 95

        estimates = MilitaryPresenter().foreign_force_estimates_for_country(state, "USA")

        self.assertEqual(len(estimates), 1)
        estimate = estimates[0]
        self.assertEqual(estimate["target_country_id"], "MEX")
        self.assertEqual(estimate["source_country_id"], "CAN")
        self.assertEqual(estimate["source_type"], "allied")
        self.assertEqual(estimate["total_count_range"], (8, 12))
        self.assertEqual(estimate["role_count_ranges"], (("fighters", 2, 4),))
        self.assertEqual(estimate["source_factors"], {
            "observer_telecom": 0.9, "intelligence_coverage": "sustained",
        })
        self.assertLessEqual(estimate["confidence"], 0.845)
        self.assertEqual(estimate["status"], "estimated")
        restored = GameState.from_ipc(state.to_ipc())
        self.assertEqual(
            estimates,
            MilitaryPresenter().foreign_force_estimates_for_country(restored, "USA"),
        )

    def test_missing_and_expired_foreign_force_observations_never_become_zero_forces(self):
        state = GameState(tables={
            "countries": pl.DataFrame({"id": ["USA", "MEX"], "budget_telecom_ratio": [0.8, 0.5]}),
            "covert_findings": pl.DataFrame({
                "id": ["expired"], "owner_country_id": ["USA"], "target_country_id": ["MEX"],
                "category": ["military"], "value_json": [json.dumps({"unit_count_estimate": 0})],
                "confidence": [0.7], "freshness": [1.0],
                "discovered_at_minute": [0], "expires_at_minute": [10],
            }),
        })
        state.time.total_minutes = 10

        estimate = MilitaryPresenter().foreign_force_estimates_for_country(state, "USA")[0]

        self.assertEqual(estimate["status"], "outdated")
        self.assertIsNone(estimate["total_count_range"])
        self.assertEqual(estimate["role_count_ranges"], ())

        state.update_table("covert_findings", pl.DataFrame(schema=state.get_table("covert_findings").schema))
        self.assertEqual(MilitaryPresenter().foreign_force_estimates_for_country(state, "USA"), [])

    def test_active_enemy_without_authorized_observation_is_returned_as_unknown(self):
        state = GameState(tables={
            "countries": pl.DataFrame({"id": ["USA", "CAN"], "name": ["United States", "Canada"]}),
            "countries_wars": pl.DataFrame({
                "id": ["war-1"], "side_a": [["USA"]], "side_b": [["CAN"]], "status": ["active"],
            }, schema={"id": pl.Utf8, "side_a": pl.List(pl.Utf8), "side_b": pl.List(pl.Utf8), "status": pl.Utf8}),
            "covert_findings": pl.DataFrame({
                "id": ["unauthorized"], "owner_country_id": ["GBR"], "target_country_id": ["CAN"],
                "category": ["military"], "value_json": [json.dumps({"unit_count_estimate": 99})],
                "confidence": [1.0], "discovered_at_minute": [10], "expires_at_minute": [100],
            }),
        })

        estimates = MilitaryPresenter().foreign_force_estimates_for_country(state, "USA")

        self.assertEqual(len(estimates), 1)
        self.assertEqual(estimates[0]["target_country_id"], "CAN")
        self.assertEqual(estimates[0]["target_country_name"], "Canada")
        self.assertEqual(estimates[0]["status"], "unknown")
        self.assertEqual(estimates[0]["source_type"], "none")
        self.assertIsNone(estimates[0]["total_count_range"])
        self.assertEqual(estimates[0]["role_count_ranges"], ())

    def test_mobilization_signals_obey_ally_sharing_and_receiver_confidence_limits(self):
        signal = {
            "signal_type": "mobilization", "domain": "land", "from_readiness": "parked",
            "to_readiness": "ready", "confidence_factors": {"observer_telecom": 0.9, "intelligence_coverage": "limited"},
        }
        state = GameState(tables={
            "countries": pl.DataFrame({
                "id": ["USA", "CAN", "MEX", "GBR"],
                "name": ["United States", "Canada", "Mexico", "United Kingdom"],
                "budget_telecom_ratio": [0.9, 0.5, 0.8, 0.5],
            }),
            "covert_findings": pl.DataFrame({
                "id": ["owned", "allied", "unauthorized"],
                "owner_country_id": ["USA", "MEX", "GBR"],
                "target_country_id": ["CAN", "CAN", "CAN"],
                "category": ["military_mobilization"] * 3,
                "value_json": [json.dumps(signal)] * 3,
                "confidence": [0.6, 0.95, 1.0], "freshness": [1.0, 1.0, 1.0],
                "discovered_at_minute": [40, 50, 55], "expires_at_minute": [100, 110, 115],
            }),
            "treaty_effects": pl.DataFrame({
                "treaty_id": ["alliance"], "country_id": ["MEX"],
                "effect": ["military_intelligence_sharing"], "value": [1.0], "detail": ['["USA"]'],
            }),
        })
        state.time.total_minutes = 60

        presenter = MilitaryPresenter()
        signals = presenter.mobilization_signals_for_country(state, "USA")

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["target_country_id"], "CAN")
        self.assertEqual(signals[0]["source_country_id"], "MEX")
        self.assertEqual(signals[0]["source_type"], "allied")
        self.assertEqual(signals[0]["domain"], "land")
        self.assertLessEqual(signals[0]["confidence"], 0.845)

        state.update_table("treaty_effects", pl.DataFrame(schema=state.get_table("treaty_effects").schema))
        signals = presenter.mobilization_signals_for_country(state, "USA")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["source_country_id"], "USA")
        self.assertEqual(signals[0]["source_type"], "owned")


if __name__ == "__main__":
    unittest.main()
