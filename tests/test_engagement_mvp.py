import unittest

import polars as pl

from modules.base.systems.military.combat_system import CombatSystem
from modules.base.systems.military.military_system import MilitarySystem, UnitFactory
from src.core.map.geo import GeoCoordinate
from src.shared.actions import ActionAttackUnit, ActionMoveUnit
from src.shared.engagement import ENGAGEMENT_RADIUS_KM, distance_to_zone_km
from src.shared.state import GameState


class EngagementMvpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.military = MilitarySystem()
        self.combat = CombatSystem()

    def test_route_stops_at_hostile_zone_and_creates_positional_battle(self) -> None:
        state = self._state()
        state.time.total_minutes = 1
        state.current_actions = [
            ActionMoveUnit(
                player_id="tester",
                unit_id="usa-1",
                target_region_id=2,
                target_latitude=0.0,
                target_longitude=10.0,
            )
        ]
        self.military.update(state, 0.0)

        state.current_actions = []
        state.time.total_minutes = 1_000
        self.military.update(state, 0.0)
        units = {row["id"]: row for row in state.get_table("units").to_dicts()}
        attacker = units["usa-1"]

        self.assertFalse(attacker["is_moving"])
        self.assertEqual(attacker["current_region_id"], 2)
        self.assertEqual(attacker["engagement_mode"], "positional")
        self.assertAlmostEqual(
            distance_to_zone_km(
                GeoCoordinate(attacker["latitude"], attacker["longitude"]),
                GeoCoordinate(0.0, 10.0),
            ),
            ENGAGEMENT_RADIUS_KM,
            delta=2.0,
        )

        self.combat.update(state, 0.0)

        battles = state.get_table("battles")
        self.assertEqual(battles.height, 1)
        self.assertEqual(battles["mode"][0], "positional")
        self.assertEqual(battles["status"][0], "active")

    def test_reissued_route_escalates_positional_battle_to_assault(self) -> None:
        state = self._state()
        state.time.total_minutes = 1
        state.current_actions = [
            ActionMoveUnit("tester", "usa-1", 2, 0.0, 10.0)
        ]
        self.military.update(state, 0.0)

        state.current_actions = []
        state.time.total_minutes = 1_000
        self.military.update(state, 0.0)
        self.combat.update(state, 0.0)

        state.current_actions = [
            ActionMoveUnit("tester", "usa-1", 2, 0.0, 10.0)
        ]
        self.military.update(state, 0.0)
        self.combat.update(state, 0.0)

        units = {row["id"]: row for row in state.get_table("units").to_dicts()}
        self.assertEqual(units["usa-1"]["engagement_mode"], "assault")
        self.assertLess(units["usa-1"]["strength"], 100)
        self.assertLess(units["can-1"]["strength"], 100)
        self.assertEqual(state.get_table("battles")["mode"][0], "assault")

    def test_direct_attack_starts_assault_and_resolves_immediately(self) -> None:

        state = self._state()
        state.current_actions = [
            ActionAttackUnit(
                player_id="tester",
                attacker_unit_id="usa-1",
                defender_unit_id="can-1",
            )
        ]

        self.military.update(state, 0.0)
        units_after_order = {row["id"]: row for row in state.get_table("units").to_dicts()}
        self.assertEqual(units_after_order["usa-1"]["current_region_id"], 2)
        self.assertEqual(units_after_order["usa-1"]["engagement_mode"], "assault")
        self.assertEqual(units_after_order["can-1"]["engagement_mode"], "assault")

        self.combat.update(state, 0.0)

        units_after_combat = {row["id"]: row for row in state.get_table("units").to_dicts()}
        self.assertLess(units_after_combat["usa-1"]["strength"], 100)
        self.assertLess(units_after_combat["can-1"]["strength"], 100)
        self.assertEqual(state.get_table("battles")["mode"][0], "assault")

    def _state(self) -> GameState:
        factory = UnitFactory()
        usa = factory.create("usa-1", "USA", "army", 100, 1, GeoCoordinate(0.0, 0.0), 0)
        canada = factory.create("can-1", "CAN", "army", 100, 2, GeoCoordinate(0.0, 10.0), 0)
        return GameState(
            tables={
                "countries": pl.DataFrame({"id": ["USA", "CAN"], "military_count": [100, 100]}),
                "regions": pl.DataFrame(
                    {
                        "id": [1, 2],
                        "owner": ["USA", "CAN"],
                        "controller": ["USA", "CAN"],
                        "latitude": [0.0, 0.0],
                        "longitude": [0.0, 10.0],
                    }
                ),
                "units": pl.DataFrame([usa, canada]),
                "countries_wars": pl.DataFrame(
                    {"id": ["war-usa-can"], "side_a": [["USA"]], "side_b": [["CAN"]], "status": ["active"]}
                ),
            }
        )


if __name__ == "__main__":
    unittest.main()
