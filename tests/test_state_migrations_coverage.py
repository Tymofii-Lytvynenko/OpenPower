import unittest

import polars as pl

from src.server.state_migrations import (
    _normalize_longitude,
    migrate_political_state,
    migrate_tactical_combat_state,
    validate_tactical_combat_state,
)
from src.shared.schema import WorldSchemaRegistry
from src.shared.state import GameState


class StateMigrationsCoverageTest(unittest.TestCase):
    def test_political_migration_skips_tables_without_registered_schemas(self) -> None:
        state = GameState()
        migrate_political_state(state, WorldSchemaRegistry())

        self.assertEqual(state.tables, {})

    def test_tactical_migration_adds_missing_legacy_unit_columns(self) -> None:
        state = GameState(tables={"units": pl.DataFrame({"id": ["unit-1"]})})

        migrate_tactical_combat_state(state)

        unit = state.tables["units"].row(0, named=True)
        self.assertEqual(unit["readiness_status"], "ready")
        self.assertEqual(unit["readiness_transition_id"], "")
        self.assertEqual(unit["readiness_progress"], 0.0)
        self.assertEqual(unit["readiness_eta_minute"], 0)
        self.assertEqual(unit["unit_lifecycle"], "available")
        self.assertEqual(unit["training_state"], "")
        self.assertEqual(unit["training_progress"], 0.0)

    def test_tactical_migration_normalizes_null_and_invalid_readiness_fields(self) -> None:
        state = GameState(
            tables={
                "units": pl.DataFrame(
                    {
                        "id": ["unit-1", "unit-2"],
                        "readiness_status": [" PARKED ", None],
                        "readiness_transition_id": [None, "transition-2"],
                        "readiness_progress": [-0.5, 1.5],
                        "readiness_eta_minute": [None, 12],
                    }
                )
            }
        )

        migrate_tactical_combat_state(state)

        units = state.tables["units"]
        self.assertEqual(units["readiness_status"].to_list(), ["parked", "ready"])
        self.assertEqual(units["readiness_transition_id"].to_list(), ["", "transition-2"])
        self.assertEqual(units["readiness_progress"].to_list(), [0.0, 1.0])
        self.assertEqual(units["readiness_eta_minute"].to_list(), [0, 12])

    def test_tactical_migration_without_battles_is_a_no_op_for_anchors(self) -> None:
        state = GameState()

        migrate_tactical_combat_state(state)

        self.assertEqual(state.tables, {})

    def test_battle_migration_preserves_coordinates_and_wraps_longitudes(self) -> None:
        state = GameState(
            tables={
                "battles": pl.DataFrame(
                    {
                        "id": ["seam", "origin", "legacy-source"],
                        "region_id": [0, 0, 0],
                        "anchor_latitude": [10.0, 0.0, -5.0],
                        "anchor_longitude": [180.0, 0.0, 12.0],
                        "anchor_source": [" CONTACT ", "", "legacy"],
                    }
                )
            }
        )

        migrate_tactical_combat_state(state)

        battles = state.tables["battles"].to_dicts()
        self.assertEqual(battles[0]["anchor_longitude"], -180.0)
        self.assertEqual(battles[0]["anchor_source"], "contact")
        self.assertEqual((battles[1]["anchor_latitude"], battles[1]["anchor_longitude"]), (0.0, 0.0))
        self.assertEqual(battles[1]["anchor_source"], "contact")
        self.assertEqual(battles[2]["anchor_source"], "legacy")
        self.assertEqual(_normalize_longitude(-181.0), 179.0)

    def test_battle_migration_keeps_unresolvable_anchors_visible(self) -> None:
        state = GameState(
            tables={
                "battles": pl.DataFrame(
                    {
                        "id": ["bad-region", "bad-region-center"],
                        "region_id": ["not-an-id", "7"],
                    }
                ),
                "regions": pl.DataFrame(
                    {
                        "id": ["malformed", "7"],
                        "latitude": [51.0, 91.0],
                        "longitude": [0.0, 0.0],
                    }
                ),
            }
        )

        migrate_tactical_combat_state(state)

        battles = state.tables["battles"]
        self.assertEqual(battles["anchor_latitude"].to_list(), [None, None])
        self.assertEqual(battles["anchor_longitude"].to_list(), [None, None])
        self.assertEqual(battles["anchor_source"].to_list(), ["", ""])
        issues = validate_tactical_combat_state(state)
        self.assertIn("battles.invalid_anchor_coordinate:bad-region", issues)
        self.assertIn("battles.invalid_anchor_source:bad-region-center", issues)

    def test_battle_migration_without_regions_keeps_missing_anchors_visible(self) -> None:
        state = GameState(tables={"battles": pl.DataFrame({"id": ["battle-1"], "region_id": [4]})})

        migrate_tactical_combat_state(state)

        issues = validate_tactical_combat_state(state)
        self.assertIn("battles.invalid_anchor_coordinate:battle-1", issues)
        self.assertIn("battles.invalid_anchor_source:battle-1", issues)

    def test_validation_reports_missing_unit_id_and_transition_columns(self) -> None:
        state = GameState(
            tables={
                "units": pl.DataFrame(
                    {
                        "readiness_status": ["unknown"],
                        "readiness_transition_id": ["orphan"],
                        "readiness_eta_minute": [-1],
                    }
                ),
                "unit_readiness_transitions": pl.DataFrame(
                    {"id": ["transition-1", "transition-2"], "unit_id": ["unit-1", "unit-1"]}
                ),
            }
        )

        issues = validate_tactical_combat_state(state)

        self.assertIn("units.missing_id", issues)
        self.assertIn("units.invalid_readiness_status:1", issues)
        self.assertIn("units.negative_readiness_eta:1", issues)
        self.assertIn("unit_readiness_transitions.duplicate_unit:1", issues)
        self.assertIn("unit_readiness_transitions.missing_pending_order_id", issues)

    def test_validation_reports_invalid_transition_order_and_battle_contracts(self) -> None:
        state = GameState(
            tables={
                "units": pl.DataFrame(
                    {
                        "id": ["unit-1", "unit-2"],
                        "readiness_status": ["unknown", "ready"],
                        "readiness_transition_id": ["wrong", "missing"],
                        "readiness_eta_minute": [-1, 0],
                    }
                ),
                "unit_readiness_transitions": pl.DataFrame(
                    {
                        "id": ["transition-1", "transition-2", "transition-3"],
                        "unit_id": ["unit-1", "unit-1", "ghost"],
                        "from_status": ["unknown", "parked", "parked"],
                        "target_status": ["unknown", "ready", "ready"],
                        "stage": ["unknown", "direct", "direct"],
                        "started_at_minute": [10, 0, 0],
                        "completes_at_minute": [5, 1, 0],
                        "progress": [1.5, 0.5, 0.0],
                        "pending_order_id": ["other", "", ""],
                    }
                ),
                "unit_pending_orders": pl.DataFrame(
                    {
                        "id": ["order-1", "order-2", "order-3", "order-4"],
                        "unit_id": ["unit-1", "unit-1", "ghost", "unit-2"],
                        "status": ["queued", "queued", "queued", "completed"],
                    }
                ),
                "battles": pl.DataFrame(
                    {
                        "id": ["invalid", "bad-conclusion"],
                        "status": ["flying", "concluded"],
                        "started_at_minute": [10, 10],
                        "updated_at_minute": [5, 10],
                        "concluded_at_minute": [0, 9],
                        "anchor_latitude": [91.0, 0.0],
                        "anchor_longitude": [200.0, 0.0],
                        "anchor_source": ["unknown", "contact"],
                    }
                ),
            }
        )

        issues = validate_tactical_combat_state(state)

        expected = {
            "units.invalid_readiness_status:1",
            "units.negative_readiness_eta:1",
            "unit_readiness_transitions.duplicate_unit:1",
            "unit_readiness_transitions.invalid_from_status:transition-1",
            "unit_readiness_transitions.invalid_target_status:transition-1",
            "unit_readiness_transitions.invalid_stage:transition-1",
            "unit_readiness_transitions.invalid_timing:transition-1",
            "unit_readiness_transitions.invalid_progress:transition-1",
            "unit_readiness_transitions.unit_reference_mismatch:transition-1",
            "unit_readiness_transitions.eta_mismatch:transition-1",
            "unit_readiness_transitions.orphan_unit:transition-3",
            "unit_pending_orders.duplicate_queued_unit:1",
            "unit_pending_orders.unlinked_transition:order-1",
            "unit_pending_orders.unlinked_transition:order-2",
            "unit_pending_orders.orphan_unit:order-3",
            "unit_pending_orders.unlinked_transition:order-3",
            "units.orphan_readiness_transition:unit-2",
            "battles.invalid_status:invalid",
            "battles.invalid_timing:invalid",
            "battles.invalid_anchor_coordinate:invalid",
            "battles.invalid_anchor_source:invalid",
            "battles.invalid_conclusion_time:bad-conclusion",
        }
        self.assertTrue(expected.issubset(set(issues)))


if __name__ == "__main__":
    unittest.main()
