import unittest

import polars as pl

from src.client.ui.panels.military.presenter import MilitaryPresenter
from src.shared.state import GameState


class BattleStatusInterfaceTest(unittest.TestCase):
    def test_projection_aggregates_participants_and_legacy_defaults(self) -> None:
        state = GameState(tables={
            "battles": pl.DataFrame({
                "id": ["battle-1"], "region_id": [2], "attacker_side": ["USA,MEX"],
                "defender_side": ["CAN"], "mode": ["assault"], "balance": [0.6], "status": ["active"],
                "side_a_strength": [150.0], "side_b_strength": [100.0],
            }),
            "battle_participants": pl.DataFrame({
                "battle_id": ["battle-1", "battle-1"], "country_id": ["MEX", "USA"],
                "side": ["attacker", "attacker"], "role": ["ally", "principal"],
                "unit_count": [1, 2], "weighted_strength": [50.0, 100.0],
            }),
            "battle_units": pl.DataFrame({
                "battle_id": ["battle-1", "battle-1"], "country_id": ["MEX", "USA"],
                "readiness_status": ["fortified", "ready"],
            }),
            "occupations": pl.DataFrame({
                "region_id": [2], "controller_country_id": ["USA"], "garrison_strength": [80],
                "resistance": [0.0], "occupation_status": ["active"],
            }),
        })
        model = MilitaryPresenter().battle_status(state, "battle-1")
        self.assertIsNotNone(model)
        assert model is not None
        self.assertEqual(model.side_a_countries, ("USA", "MEX"))
        self.assertEqual(model.participants[0].role, "ally")
        self.assertEqual(model.participants[0].readiness, ("fortified",))
        self.assertEqual(model.occupation["resistance"], 0.0)


if __name__ == "__main__":
    unittest.main()
