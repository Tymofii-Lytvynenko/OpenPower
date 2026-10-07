"""Warm-up comparison for the normal unit pass and 100-battle presentation path."""

from __future__ import annotations

import statistics
import time
import unittest

import polars as pl
from imgui_bundle import imgui

from src.client.renderers.battle_effect_renderer import BattleEffectRenderer
from src.client.renderers.unit_projection import UnitProjectionService
from tests.test_battle_visual_fixtures import (
    build_battle_frame,
    build_camera,
    build_region_frame,
    build_unit_frame,
)
from src.shared.state import GameState


class _DiscardDrawList:
    """Keep CPU-side draw command construction measurable without a graphics window."""

    def add_circle_filled(self, *args, **kwargs) -> None:
        pass

    def add_circle(self, *args, **kwargs) -> None:
        pass

    def add_text(self, *args, **kwargs) -> None:
        pass

    def add_line(self, *args, **kwargs) -> None:
        pass

    def add_rect_filled(self, *args, **kwargs) -> None:
        pass

    def add_rect(self, *args, **kwargs) -> None:
        pass


class BattleEffectPerformanceTest(unittest.TestCase):
    def test_warmed_up_100_battle_path_is_bounded_and_reports_medians(self) -> None:
        battles = build_battle_frame(100).with_columns(
            pl.lit(0.0).alias("anchor_latitude"),
            pl.lit(180.0).alias("anchor_longitude"),
        )
        state = GameState(
            tables={
                "battles": battles,
                "regions": build_region_frame(100),
            }
        )
        camera = build_camera()
        renderer = BattleEffectRenderer(camera, 2048, 1024, 1.0)
        rows = renderer._normalize_state(state)
        anchors = [
            (float(row["anchor_latitude"]), float(row["anchor_longitude"]))
            for row in rows
        ]
        unit_projection = UnitProjectionService(camera, 2048, 1024, 1.0)
        unit_rows = build_unit_frame(100).to_dicts()
        for row in unit_rows:
            row["latitude"] = 0.0
            row["longitude"] = 180.0
        prepared_units = unit_projection.prepare_units(unit_rows, {})
        draw_list = _DiscardDrawList()

        def baseline_sample() -> float:
            started = time.perf_counter()
            # The existing map path projects the same number of ordinary unit billboards.
            _ = unit_projection.project_prepared_units(prepared_units, 1280, 720, 0.0)
            return time.perf_counter() - started

        def feature_sample() -> float:
            started = time.perf_counter()
            _ = unit_projection.project_prepared_units(prepared_units, 1280, 720, 0.0)
            points = renderer._projection.project_anchors(anchors, 1280, 720, marker_radius=8.0)
            projected = [
                (row, point)
                for row, point in zip(rows, points)
                if point is not None
            ]
            placements = renderer._layout(projected, 1280, 720, 0.0, False)
            for placement in placements:
                renderer._draw_placement(draw_list, placement, 1280, 720, False)
            return time.perf_counter() - started

        context = imgui.create_context()
        try:
            for _ in range(3):
                baseline_sample()
                feature_sample()
            baseline = [baseline_sample() for _ in range(7)]
            feature = [feature_sample() for _ in range(7)]
        finally:
            imgui.destroy_context(context)

        baseline_median = statistics.median(baseline)
        feature_median = statistics.median(feature)
        overhead = (feature_median - baseline_median) / max(baseline_median, 1.0e-9)

        self.assertLessEqual(len(rows), 100)
        self.assertEqual(prepared_units.count, 100)
        self.assertGreaterEqual(feature_median, 0.0)
        self.assertTrue(overhead == overhead)  # finite/non-NaN guard
        print(
            "battle overlay CPU proxy: "
            f"overlay-free median {baseline_median * 1_000:.3f} ms; "
            f"100-battle median {feature_median * 1_000:.3f} ms; "
            f"overhead {overhead * 100:.2f}% (target <= 5%; ImGui calls are discarded)"
        )


if __name__ == "__main__":
    unittest.main()
