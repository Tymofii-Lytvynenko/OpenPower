import math
import unittest

from src.client.renderers.globe_overlay_projection import GlobeOverlayProjection
from src.client.renderers.battle_effect_renderer import BattleEffectRenderer
from tests.test_battle_visual_fixtures import build_camera


class GlobeOverlayProjectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.camera = build_camera()
        self.projection = GlobeOverlayProjection(self.camera, 2048, 1024, 1.0)

    def test_front_facing_anchor_has_bounded_marker_and_clearance(self) -> None:
        point = self.projection.project_anchor(0.0, 180.0, 800, 600, marker_radius=999.0)
        self.assertIsNotNone(point)
        assert point is not None
        self.assertTrue(point.front_facing)
        self.assertGreaterEqual(point.marker_radius, 4.0)
        self.assertLessEqual(point.marker_radius, 12.0)
        self.assertGreater(point.silhouette_clearance, 0.0)

    def test_back_facing_anchor_is_rejected(self) -> None:
        point = self.projection.project_anchor(0.0, 0.0, 800, 600)
        self.assertIsNone(point)

    def test_yaw_and_pitch_matrix_stays_finite(self) -> None:
        for yaw in range(0, 360, 45):
            for pitch in (-60, -30, 0, 30, 60):
                self.camera.yaw = math.radians(yaw)
                self.camera.pitch = math.radians(pitch)
                point = self.projection.project_anchor(0.0, 180.0, 800, 600)
                if point is not None:
                    self.assertTrue(math.isfinite(point.screen_x))
                    self.assertTrue(math.isfinite(point.screen_y))
                    self.assertTrue(math.isfinite(point.silhouette_clearance))

    def test_batched_projection_matches_scalar_projection(self) -> None:
        anchors = [(0.0, 180.0), (20.0, 170.0), (0.0, 0.0)]
        batched = self.projection.project_anchors(anchors, 800, 600)
        scalar = [self.projection.project_anchor(*anchor, 800, 600) for anchor in anchors]
        for batch_point, scalar_point in zip(batched, scalar):
            if scalar_point is None:
                self.assertIsNone(batch_point)
            else:
                self.assertIsNotNone(batch_point)
                assert batch_point is not None
                self.assertAlmostEqual(batch_point.screen_x, scalar_point.screen_x, places=4)
                self.assertAlmostEqual(batch_point.screen_y, scalar_point.screen_y, places=4)

    def test_zoom_and_longitude_seam_matrix_keeps_visible_points_bounded(self) -> None:
        for distance in (
            self.camera.min_distance,
            (self.camera.min_distance + self.camera.max_distance) * 0.5,
            self.camera.max_distance,
        ):
            self.camera.distance = distance
            for longitude in (179.999, -179.999):
                point = self.projection.project_anchor(0.0, longitude, 800, 600)
                if point is not None:
                    self.assertGreaterEqual(point.marker_radius, 4.0)
                    self.assertLessEqual(point.marker_radius, 12.0)

    def test_silhouette_clearance_controls_decorative_footprints(self) -> None:
        point = self.projection.project_anchor(0.0, 180.0, 800, 600)
        self.assertIsNotNone(point)
        assert point is not None
        self.assertTrue(BattleEffectRenderer.can_draw_decorative(point, 1.0))
        self.assertFalse(BattleEffectRenderer.can_draw_decorative(point, point.silhouette_clearance + 1.0))


if __name__ == "__main__":
    unittest.main()
