import unittest

import polars as pl

from modules.base.systems.military.combat_system import CombatSystem
from modules.base.systems.military.military_system import UNIT_SCHEMA, UnitFactory
from src.core.map.geo import GeoCoordinate
from src.shared.state import GameState


class BattleAlliesTest(unittest.TestCase):
    def test_direct_active_ally_participates_without_transitive_chain(self) -> None:
        factory = UnitFactory()
        rows = [
            factory.create("usa-1", "USA", "army", 100, 1, GeoCoordinate(0, 0), 0),
            factory.create("can-1", "CAN", "army", 100, 1, GeoCoordinate(0, 0), 0),
            factory.create("mex-1", "MEX", "army", 50, 1, GeoCoordinate(0, 0), 0),
            factory.create("fra-1", "FRA", "army", 50, 1, GeoCoordinate(0, 0), 0),
        ]
        state = GameState(tables={
            "regions": pl.DataFrame({"id": [1], "owner": ["CAN"], "controller": ["CAN"], "latitude": [0.0], "longitude": [0.0]}),
            "units": pl.DataFrame(rows, schema=UNIT_SCHEMA),
            "countries_wars": pl.DataFrame({"id": ["war-1"], "side_a": [["USA"]], "side_b": [["CAN"]], "status": ["active"]}),
            "countries_treaties": pl.DataFrame({
                "id": ["pact-usa-mex", "pact-mex-fra"],
                "type": ["alliance", "alliance"],
                "status": ["active", "active"],
                "members": [["USA", "MEX"], ["MEX", "FRA"]],
                "side_a": [["USA", "MEX"], ["MEX", "FRA"]],
                "side_b": [[], []],
            }),
        })
        CombatSystem().update(state, 0)
        participants = {row["country_id"]: row for row in state.get_table("battle_participants").to_dicts()}
        self.assertEqual(participants["MEX"]["role"], "ally")
        self.assertNotIn("FRA", participants)
        self.assertTrue(any(getattr(event, "country_id", "") == "FRA" for event in state.events))

    def test_ambiguous_direct_commitments_are_rejected(self) -> None:
        factory = UnitFactory()
        rows = [
            factory.create("usa-1", "USA", "army", 100, 1, GeoCoordinate(0, 0), 0),
            factory.create("can-1", "CAN", "army", 100, 1, GeoCoordinate(0, 0), 0),
            factory.create("mex-1", "MEX", "army", 50, 1, GeoCoordinate(0, 0), 0),
        ]
        treaty_rows = [
            {"id": "a", "type": "alliance", "status": "active", "members": ["USA", "MEX"], "side_a": ["USA", "MEX"], "side_b": []},
            {"id": "b", "type": "alliance", "status": "active", "members": ["CAN", "MEX"], "side_a": ["CAN", "MEX"], "side_b": []},
        ]
        state = GameState(tables={
            "regions": pl.DataFrame({"id": [1], "owner": ["CAN"], "controller": ["CAN"], "latitude": [0.0], "longitude": [0.0]}),
            "units": pl.DataFrame(rows, schema=UNIT_SCHEMA),
            "countries_wars": pl.DataFrame({"id": ["war-1"], "side_a": [["USA"]], "side_b": [["CAN"]], "status": ["active"]}),
            "countries_treaties": pl.DataFrame(treaty_rows),
        })
        CombatSystem().update(state, 0)
        self.assertFalse(any(row["country_id"] == "MEX" for row in state.get_table("battle_participants").to_dicts()))
        self.assertTrue(any(getattr(event, "country_id", "") == "MEX" for event in state.events))


if __name__ == "__main__":
    unittest.main()
