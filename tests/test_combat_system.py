import unittest

import polars as pl

from modules.base.systems.military.combat_system import CombatSystem, ConflictContext
from src.shared.events import EventBattleEnded, EventBattleStarted, EventNewHour
from src.shared.state import GameState


class TestCombatSystem(unittest.TestCase):
    def setUp(self):
        self.system = CombatSystem()

    def test_strategy_readiness_risk_holding_and_counterattack_projections_reach_resolver(self):
        attacker = {
            "id": "usa-1", "owner": "USA", "strength": 100,
            "readiness_status": "ready", "combat_posture": "defend",
            "combat_strength_modifier": 1.0, "combat_readiness_modifier": 0.5,
            "combat_holding_modifier": 1.2, "combat_attack_risk_modifier": 1.25,
            "combat_counterattack_modifier": 1.2, "combat_casualty_modifier": 1.0,
            "combat_defense_modifier": 1.0, "war_exhaustion_modifier": 1.0,
            "cohesion": 1.0,
        }
        defender = {
            "id": "can-1", "owner": "CAN", "strength": 100,
            "readiness_status": "ready", "combat_posture": "hold",
            "combat_strength_modifier": 1.0, "combat_readiness_modifier": 1.0,
            "combat_holding_modifier": 1.0, "combat_attack_risk_modifier": 1.0,
            "combat_counterattack_modifier": 1.0, "combat_casualty_modifier": 1.0,
            "combat_defense_modifier": 1.0, "war_exhaustion_modifier": 1.0,
            "cohesion": 1.0,
        }

        self.assertEqual(self.system._total_strength([attacker], {"USA"}), 50)
        self.assertAlmostEqual(self.system._casualty_modifier([attacker], {"USA"}), 1.25)
        self.assertAlmostEqual(self.system._side_damage_factor([attacker, defender], {"USA"}, {"CAN"}), 1.2)
        defender["combat_holding_modifier"] = 1.2
        self.assertAlmostEqual(self.system._side_damage_factor([attacker, defender], {"USA"}, {"CAN"}), 1.0)

    def test_hostile_units_create_active_battle(self):
        state = self._build_state(
            units=[
                {"id": "usa-1", "owner": "USA", "strength": 120, "current_region_id": 1, "is_moving": False},
                {"id": "can-1", "owner": "CAN", "strength": 110, "current_region_id": 1, "is_moving": False},
            ],
            wars=[{"side_a": ["USA"], "side_b": ["CAN"]}],
        )

        self.system.update(state, 0.1)

        battles = state.get_table("battles")
        battle_units = state.get_table("battle_units")
        regions = state.get_table("regions")

        self.assertEqual(len(battles), 1)
        self.assertEqual(len(battle_units), 2)
        self.assertEqual(battles["status"][0], "active")
        self.assertEqual(regions["controller"][0], "CAN")
        self.assertTrue(any(isinstance(event, EventBattleStarted) for event in state.events))
        self.assertFalse(any(isinstance(event, EventBattleEnded) for event in state.events))

    def test_hourly_resolution_occupies_region_for_victor(self):
        state = self._build_state(
            units=[
                {"id": "usa-1", "owner": "USA", "strength": 240, "current_region_id": 1, "is_moving": False},
                {"id": "can-1", "owner": "CAN", "strength": 60, "current_region_id": 1, "is_moving": False},
            ],
            wars=[{"side_a": ["USA"], "side_b": ["CAN"]}],
        )
        state.events.append(EventNewHour(hour=1, total_minutes=60))

        self.system.update(state, 0.1)

        battles = state.get_table("battles")
        units = state.get_table("units")
        regions = state.get_table("regions")
        countries = state.get_table("countries")

        self.assertEqual(len(battles), 1)
        self.assertEqual(battles["status"][0], "concluded")
        self.assertEqual(len(units), 1)
        self.assertEqual(units["owner"][0], "USA")
        self.assertEqual(regions["controller"][0], "USA")
        self.assertEqual(countries.filter(pl.col("id") == "USA")["military_count"][0], units["strength"][0])
        self.assertEqual(countries.filter(pl.col("id") == "CAN")["military_count"][0], 0)
        self.assertTrue(any(isinstance(event, EventBattleStarted) for event in state.events))
        self.assertTrue(any(isinstance(event, EventBattleEnded) for event in state.events))

    def test_undefended_enemy_region_becomes_occupied(self):
        state = self._build_state(
            units=[
                {"id": "usa-1", "owner": "USA", "strength": 80, "current_region_id": 1, "is_moving": False},
            ],
            wars=[{"side_a": ["USA"], "side_b": ["CAN"]}],
        )

        self.system.update(state, 0.1)

        regions = state.get_table("regions")
        self.assertEqual(regions["owner"][0], "CAN")
        self.assertEqual(regions["controller"][0], "USA")
        self.assertEqual(len(state.get_table("battles")), 0)

    def test_no_occupation_without_active_war(self):
        state = self._build_state(
            units=[
                {"id": "usa-1", "owner": "USA", "strength": 80, "current_region_id": 1, "is_moving": False},
            ],
            wars=[],
        )

        self.system.update(state, 0.1)

        self.assertEqual(state.get_table("regions")["controller"][0], "CAN")
        self.assertEqual(len(state.get_table("battles")), 0)

    def test_capability_matrix_limits_losses_to_targets_attackers_can_engage(self):
        conflict = ConflictContext(
            war_id="war-1",
            side_a_members=frozenset({"USA"}),
            side_b_members=frozenset({"CAN"}),
            side_a_tags=frozenset({"USA"}),
            side_b_tags=frozenset({"CAN"}),
        )
        units = [
            {"id": "usa-tank", "owner": "USA", "strength": 100, "readiness_status": "ready"},
            {"id": "can-tank", "owner": "CAN", "strength": 60, "readiness_status": "ready", "combat_posture": "back_off"},
            {"id": "can-fighter", "owner": "CAN", "strength": 60, "readiness_status": "ready", "combat_posture": "back_off"},
        ]
        self.system._capability_index = {
            "usa-tank": {"role": "tanks", "domain": "land", "valid_targets": ["armor"], "vulnerabilities": [], "capabilities": {}},
            "can-tank": {"role": "tanks", "domain": "land", "valid_targets": ["armor"], "vulnerabilities": [], "capabilities": {}},
            "can-fighter": {"role": "fighters", "domain": "air", "valid_targets": ["air"], "vulnerabilities": [], "capabilities": {}},
        }

        self.system._apply_combat_round(units, conflict, "positional")

        self.assertLess(units[1]["strength"], 60)
        self.assertEqual(units[2]["strength"], 60)

    def test_configured_role_without_matching_target_deals_no_damage(self):
        conflict = ConflictContext(
            war_id="war-1",
            side_a_members=frozenset({"USA"}),
            side_b_members=frozenset({"CAN"}),
            side_a_tags=frozenset({"USA"}),
            side_b_tags=frozenset({"CAN"}),
        )
        units = [
            {"id": "usa-tank", "owner": "USA", "strength": 100, "readiness_status": "ready"},
            {"id": "can-fighter", "owner": "CAN", "strength": 60, "readiness_status": "ready", "combat_posture": "back_off"},
        ]
        self.system._capability_index = {
            "usa-tank": {"role": "tanks", "domain": "land", "valid_targets": ["armor"], "vulnerabilities": [], "capabilities": {}},
            "can-fighter": {"role": "fighters", "domain": "air", "valid_targets": ["air"], "vulnerabilities": [], "capabilities": {}},
        }

        self.system._apply_combat_round(units, conflict, "positional")

        self.assertEqual(units[0]["strength"], 100)
        self.assertEqual(units[1]["strength"], 60)

    def test_capability_counter_is_bounded_and_applies_only_to_valid_target(self):
        attacker = {"id": "usa-tank", "owner": "USA", "strength": 100}
        matching_target = {"id": "can-tank", "owner": "CAN", "strength": 60}
        outside_target = {"id": "can-fighter", "owner": "CAN", "strength": 60}
        self.system._capability_index = {
            "usa-tank": {"role": "tanks", "domain": "land", "valid_targets": ["armor"], "vulnerabilities": [], "capabilities": {}},
            "can-tank": {"role": "tanks", "domain": "land", "valid_targets": ["armor"], "vulnerabilities": ["land"], "capabilities": {}},
            "can-fighter": {"role": "fighters", "domain": "air", "valid_targets": ["air"], "vulnerabilities": [], "capabilities": {}},
        }

        factor = self.system._capability_damage_factor(attacker, [matching_target, outside_target])

        self.assertAlmostEqual(factor, 1.1)
        self.assertLessEqual(self.system._side_damage_factor(
            [attacker, matching_target, outside_target], {"USA"}, {"CAN"},
        ), 1.5)

    def test_capability_projection_does_not_change_battle_lifecycle_or_sovereignty(self):
        baseline = self._battle_state_with_projection(include_projection=False)
        projected = self._battle_state_with_projection(include_projection=True)

        CombatSystem().update(baseline, 0.1)
        CombatSystem().update(projected, 0.1)

        baseline_battle = baseline.get_table("battles").to_dicts()[0]
        projected_battle = projected.get_table("battles").to_dicts()[0]
        self.assertEqual(projected_battle["id"], baseline_battle["id"])
        self.assertEqual(projected_battle["war_id"], baseline_battle["war_id"])
        self.assertEqual(projected_battle["attacker_side"], baseline_battle["attacker_side"])
        self.assertEqual(projected_battle["defender_side"], baseline_battle["defender_side"])
        self.assertEqual(projected_battle["status"], "active")
        self.assertEqual(projected_battle["round"], 0)
        self.assertGreater(projected_battle["side_a_strength"], baseline_battle["side_a_strength"])

        for state in (baseline, projected):
            battle_units = state.get_table("battle_units").sort("unit_id").to_dicts()
            self.assertEqual(
                [(row["unit_id"], row["side"], row["readiness_status"]) for row in battle_units],
                [("can-1", "SIDE_B", "parked"), ("usa-1", "SIDE_A", "ready")],
            )
            units = state.get_table("units").sort("id").to_dicts()
            self.assertEqual(
                [(row["owner"], row["strength"], row["readiness_status"], row["readiness_transition_id"], row["readiness_progress"], row["readiness_eta_minute"])
                 for row in units],
                [("CAN", 80, "parked", "", 0.0, 0), ("USA", 100, "ready", "ready-fortified", 0.25, 600)],
            )
            transitions = state.get_table("unit_readiness_transitions").to_dicts()
            self.assertEqual(
                [(row["id"], row["unit_id"], row["progress"], row["completes_at_minute"])
                 for row in transitions],
                [("ready-fortified", "usa-1", 0.25, 600)],
            )
            region = state.get_table("regions").to_dicts()[0]
            self.assertEqual((region["owner"], region["controller"]), ("CAN", "CAN"))
            self.assertTrue(state.get_table("occupations").is_empty())

    def _build_state(self, units: list[dict], wars: list[dict]) -> GameState:
        tables = {
            "countries": pl.DataFrame(
                {
                    "id": ["USA", "CAN"],
                    "military_count": [240, 120],
                }
            ),
            "regions": pl.DataFrame(
                {
                    "id": [1],
                    "owner": ["CAN"],
                    "controller": ["CAN"],
                }
            ),
            "units": pl.DataFrame(units),
            "countries_wars": pl.DataFrame(wars) if wars else pl.DataFrame(schema={"side_a": pl.List(pl.Utf8), "side_b": pl.List(pl.Utf8)}),
        }
        return GameState(tables=tables)

    def _battle_state_with_projection(self, include_projection: bool) -> GameState:
        state = self._build_state(
            units=[
                {
                    "id": "usa-1", "owner": "USA", "strength": 100, "current_region_id": 1,
                    "is_moving": False, "readiness_status": "ready", "readiness_progress": 0.25,
                    "readiness_transition_id": "ready-fortified", "readiness_eta_minute": 600,
                },
                {
                    "id": "can-1", "owner": "CAN", "strength": 80, "current_region_id": 1,
                    "is_moving": False, "readiness_status": "parked", "readiness_progress": 0.0,
                    "readiness_transition_id": "", "readiness_eta_minute": 0,
                },
            ],
            wars=[{"side_a": ["USA"], "side_b": ["CAN"]}],
        )
        state.update_table(
            "unit_readiness_transitions",
            pl.DataFrame([{
                "id": "ready-fortified", "unit_id": "usa-1", "from_status": "ready",
                "target_status": "fortified", "stage": "ready_to_fortified",
                "started_at_minute": 0, "completes_at_minute": 600, "progress": 0.25,
                "pending_order_id": "",
            }]),
        )
        if include_projection:
            state.update_table(
                "unit_capability_projections",
                pl.DataFrame([
                    {
                        "unit_id": "usa-1", "role": "tanks", "domain": "land",
                        "valid_targets_json": '["armor"]', "vulnerabilities_json": "[]",
                        "capabilities_json": '{"gun_damage":100,"gun_precision":1}',
                    },
                    {
                        "unit_id": "can-1", "role": "tanks", "domain": "land",
                        "valid_targets_json": '["armor"]', "vulnerabilities_json": "[]",
                        "capabilities_json": "{}",
                    },
                ]),
            )
        return state


if __name__ == "__main__":
    unittest.main()
