import unittest

import polars as pl

from modules.base.systems.military.military_system import UNIT_SCHEMA, UnitFactory
from src.client.ui.panels.unit_details_window import UnitDetailsPresenter
from src.core.map.geo import GeoCoordinate
from src.shared.state import GameState


class UnitDetailsReadinessTest(unittest.TestCase):
    def test_details_resolve_target_and_remaining_time_from_authoritative_eta(self) -> None:
        unit = UnitFactory().create("usa-1", "USA", "army", 100, 1, GeoCoordinate(0, 0), 0)
        unit["readiness_transition_id"] = "transition-1"
        unit["readiness_eta_minute"] = 3000
        unit["readiness_progress"] = 0.5
        state = GameState(
            tables={
                "units": pl.DataFrame([unit], schema=UNIT_SCHEMA),
                "countries": pl.DataFrame({"id": ["USA"], "name": ["United States"]}),
                "regions": pl.DataFrame({"id": [1], "name": ["Origin"]}),
                "unit_readiness_transitions": pl.DataFrame({
                    "id": ["transition-1"],
                    "unit_id": ["usa-1"],
                    "target_status": ["fortified"],
                    "completes_at_minute": [3000],
                }),
            }
        )
        state.time.total_minutes = 1500
        model = UnitDetailsPresenter().build(state, "usa-1")
        self.assertIsNotNone(model)
        assert model is not None
        self.assertEqual(model.readiness_target, "Fortified")
        self.assertEqual(model.readiness_remaining_minutes, 1500)
        self.assertEqual(model.readiness_remaining_label, "1d 1h")


if __name__ == "__main__":
    unittest.main()
