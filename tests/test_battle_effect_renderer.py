import unittest

import polars as pl

from src.client.renderers.battle_effect_renderer import BattleEffectRenderer
from src.shared.state import GameState
from tests.test_battle_visual_fixtures import build_battle_frame, build_camera, build_region_frame


class BattleEffectRendererTest(unittest.TestCase):
    def _renderer_and_state(self, *, count: int = 1, **battle_overrides):
        state = GameState(
            tables={
                "battles": build_battle_frame(count, **battle_overrides),
                "regions": build_region_frame(count),
            }
        )
        return BattleEffectRenderer(build_camera(), 2048, 1024, 1.0), state

    def test_mode_labels_and_digest_phase_are_stable(self) -> None:
        renderer, state = self._renderer_and_state(mode="assault")
        row = renderer._normalize_state(state)[0]
        self.assertEqual(renderer._label(renderer._mode(row), renderer._status(row)), "Active")
        first = renderer.phase_for(row, 15.0)
        second = renderer.phase_for(row, 15.0)
        self.assertEqual(first, second)
        self.assertEqual(renderer.phase_for(row, 15.0, reduce_motion=True), 0.5)

    def test_missing_anchor_uses_region_lookup_without_units(self) -> None:
        renderer, state = self._renderer_and_state(
            anchor_latitude=None,
            anchor_longitude=None,
            anchor_source="",
        )
        rows = renderer._normalize_state(state)
        self.assertEqual(renderer._anchor_for_row(rows[0]), (11.0, -19.0))

    def test_invalid_anchor_source_falls_back_to_region(self) -> None:
        renderer, state = self._renderer_and_state(
            anchor_latitude=30.0,
            anchor_longitude=40.0,
            anchor_source="invalid",
        )
        row = renderer._normalize_state(state)[0]
        self.assertEqual(renderer._anchor_for_row(row), (11.0, -19.0))

    def test_fixed_grid_offsets_separate_overlapping_labels(self) -> None:
        renderer, state = self._renderer_and_state(count=2)
        rows = renderer._normalize_state(state)
        points = []
        for row in rows:
            point = renderer._projection.project_anchor(0.0, 180.0, 800, 600)
            self.assertIsNotNone(point)
            points.append((row, point))
        placements = renderer._layout(points, 800, 600, 0.0, False)
        self.assertEqual(len(placements), 2)
        self.assertNotEqual(placements[0].offset, placements[1].offset)
        self.assertEqual(placements[0].anchor_x, placements[1].anchor_x)
        self.assertEqual(placements[0].anchor_y, placements[1].anchor_y)

    def test_dense_same_anchor_stack_uses_spaced_slots_without_label_overlap(self) -> None:
        renderer, state = self._renderer_and_state(count=100)
        rows = renderer._normalize_state(state)
        anchors = [(0.0, 180.0)] * 100
        points = renderer._projection.project_anchors(anchors, 1280, 720)
        projected = [(row, point) for row, point in zip(rows, points) if point is not None]

        placements = renderer._layout(projected, 1280, 720, 0.0, False)
        rectangles = []
        for placement in placements:
            label_width = max(44.0, float(len(placement.label) * 7 + 18))
            rectangles.append((
                placement.label_x,
                placement.label_y,
                placement.label_x + label_width,
                placement.label_y + 22.0,
            ))

        for index, current in enumerate(rectangles):
            for previous in rectangles[:index]:
                self.assertFalse(
                    current[0] < previous[2]
                    and current[2] > previous[0]
                    and current[1] < previous[3]
                    and current[3] > previous[1]
                )
        self.assertEqual(len(placements), 100)

    def test_palette_is_side_level_and_allies_share_identity(self) -> None:
        renderer, state = self._renderer_and_state(
            attacker_side="USA,CAN",
            defender_side="MEX",
        )
        row = renderer._normalize_state(state)[0]
        first, second = renderer.side_colors(row)
        row_with_same_side = dict(row)
        row_with_same_side["attacker_side"] = "CAN,USA"
        self.assertEqual(first, renderer.side_colors(row_with_same_side)[0])
        self.assertNotEqual(first, second)

    def test_revision_change_refreshes_normalized_battles(self) -> None:
        renderer, state = self._renderer_and_state()
        first = renderer._normalize_state(state)
        state.update_table(
            "battles",
            pl.concat(
                [state.tables["battles"], build_battle_frame(2).tail(1)],
                how="vertical",
            ),
        )
        second = renderer._normalize_state(state)
        self.assertIsNot(first, second)
        self.assertEqual(len(second), 2)

    def test_normalized_order_is_battle_id_stable(self) -> None:
        renderer, state = self._renderer_and_state(count=2)
        state.update_table("battles", state.tables["battles"].reverse())
        rows = renderer._normalize_state(state)
        self.assertEqual([row["id"] for row in rows], ["battle-001", "battle-002"])


if __name__ == "__main__":
    unittest.main()
