import unittest

import polars as pl

from modules.base.systems.military.combat_system import CombatSystem
from modules.base.systems.military.occupation_system import OccupationSystem
from modules.base.systems.military.military_system import UNIT_SCHEMA, UnitFactory
from src.core.map.geo import GeoCoordinate
from src.shared.events import EventNewHour
from src.shared.state import GameState


class OccupationResolutionTest(unittest.TestCase):
    def test_victory_creates_control_without_changing_owner(self) -> None:
        factory = UnitFactory()
        units = [
            factory.create("usa-1", "USA", "army", 240, 1, GeoCoordinate(0, 0), 0),
            factory.create("can-1", "CAN", "army", 60, 1, GeoCoordinate(0, 0), 0),
        ]
        state = GameState(tables={
            "regions": pl.DataFrame({"id": [1], "owner": ["CAN"], "controller": ["CAN"]}),
            "units": pl.DataFrame(units, schema=UNIT_SCHEMA),
            "countries_wars": pl.DataFrame({"id": ["war-1"], "side_a": [["USA"]], "side_b": [["CAN"]], "status": ["active"]}),
        })
        state.events.append(EventNewHour(1, 60))
        CombatSystem().update(state, 0)
        OccupationSystem().update(state, 0)
        self.assertEqual(state.get_table("regions")["owner"][0], "CAN")
        self.assertEqual(state.get_table("regions")["controller"][0], "USA")
        row = state.get_table("occupations").to_dicts()[0]
        self.assertEqual(row["controller_country_id"], "USA")
        self.assertEqual(row["resistance"], 0.0)


if __name__ == "__main__":
    unittest.main()
