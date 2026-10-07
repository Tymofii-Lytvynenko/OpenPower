import unittest

import polars as pl

from modules.base.systems.military.battle_anchor_policy import (
    build_contact_anchor,
    resolve_battle_anchor,
)
from src.server.state_migrations import migrate_tactical_combat_state, validate_tactical_combat_state
from src.shared.state import GameState


class BattleAnchorPolicyTest(unittest.TestCase):
    def test_spherical_mean_handles_longitude_seam(self) -> None:
        anchor = build_contact_anchor(
            [
                {"id": "b", "latitude": 0.0, "longitude": -179.0},
                {"id": "a", "latitude": 0.0, "longitude": 179.0},
            ]
        )
        self.assertIsNotNone(anchor)
        assert anchor is not None
        self.assertAlmostEqual(anchor.latitude, 0.0, places=6)
        self.assertAlmostEqual(abs(anchor.longitude), 180.0, places=6)
        self.assertEqual(anchor.source, "contact")

    def test_region_fallback_uses_actual_region_coordinates(self) -> None:
        anchor = resolve_battle_anchor([], {"latitude": 47.2, "longitude": 8.5}, None)
        self.assertEqual(anchor.source, "region_center")
        self.assertEqual((anchor.latitude, anchor.longitude), (47.2, 8.5))

    def test_zero_zero_is_a_valid_contact_anchor(self) -> None:
        anchor = resolve_battle_anchor(
            [{"id": "unit", "latitude": 0.0, "longitude": 0.0}],
            {"latitude": 30.0, "longitude": 30.0},
        )
        self.assertEqual((anchor.latitude, anchor.longitude), (0.0, 0.0))
        self.assertEqual(anchor.source, "contact")

    def test_prior_anchor_is_preserved_when_contact_moves(self) -> None:
        prior = {
            "anchor_latitude": 2.0,
            "anchor_longitude": 3.0,
            "anchor_source": "contact",
        }
        anchor = resolve_battle_anchor(
            [{"id": "unit", "latitude": 40.0, "longitude": 40.0}],
            {"latitude": 50.0, "longitude": 50.0},
            prior,
        )
        self.assertEqual((anchor.latitude, anchor.longitude), (2.0, 3.0))
        self.assertEqual(anchor.source, "contact")

    def test_legacy_migration_backfills_region_before_validation(self) -> None:
        state = GameState(
            tables={
                "battles": pl.DataFrame(
                    {
                        "id": ["battle-1"],
                        "region_id": [7],
                        "status": ["active"],
                        "started_at_minute": [0],
                        "updated_at_minute": [0],
                        "concluded_at_minute": [0],
                    }
                ),
                "regions": pl.DataFrame(
                    {"id": [7], "latitude": [51.5], "longitude": [-0.1]}
                ),
            }
        )
        migrate_tactical_combat_state(state)
        row = state.tables["battles"].to_dicts()[0]
        self.assertEqual(row["anchor_source"], "region_center")
        self.assertEqual((row["anchor_latitude"], row["anchor_longitude"]), (51.5, -0.1))
        self.assertEqual(validate_tactical_combat_state(state), ())

    def test_explicit_invalid_anchor_source_is_reported(self) -> None:
        state = GameState(
            tables={
                "battles": pl.DataFrame(
                    {
                        "id": ["battle-1"],
                        "region_id": [7],
                        "anchor_latitude": [1.0],
                        "anchor_longitude": [2.0],
                        "anchor_source": ["invented"],
                        "status": ["active"],
                        "started_at_minute": [0],
                        "updated_at_minute": [0],
                        "concluded_at_minute": [0],
                    }
                )
            }
        )
        migrate_tactical_combat_state(state)
        self.assertIn("battles.invalid_anchor_source:battle-1", validate_tactical_combat_state(state))


if __name__ == "__main__":
    unittest.main()
