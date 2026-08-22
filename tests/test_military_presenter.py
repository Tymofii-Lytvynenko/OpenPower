import unittest

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


if __name__ == "__main__":
    unittest.main()
