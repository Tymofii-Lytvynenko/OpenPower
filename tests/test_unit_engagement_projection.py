import unittest

from src.client.controllers.camera_controller import CameraController
from src.client.renderers.unit_projection import UnitProjectionService
from src.shared.engagement import EARTH_RADIUS_KM, ENGAGEMENT_RADIUS_KM


class UnitEngagementProjectionTest(unittest.TestCase):
    def test_geographic_ring_changes_screen_size_but_keeps_world_radius(self) -> None:
        camera = CameraController(distance=2.6)
        camera.yaw = 0.0
        camera.pitch = 0.0
        projection = UnitProjectionService(camera, 360, 180, 1.0)
        angular_radius = ENGAGEMENT_RADIUS_KM / EARTH_RADIUS_KM

        near_ring = projection.project_surface_ring(
            (0.0, 0.0, -1.0),
            angular_radius,
            1280,
            720,
            32,
        )
        camera.distance = 4.0
        far_ring = projection.project_surface_ring(
            (0.0, 0.0, -1.0),
            angular_radius,
            1280,
            720,
            32,
        )

        self.assertTrue(all(point is not None for point in near_ring))
        self.assertTrue(all(point is not None for point in far_ring))
        near_width = max(point[0] for point in near_ring) - min(point[0] for point in near_ring)
        far_width = max(point[0] for point in far_ring) - min(point[0] for point in far_ring)
        self.assertGreater(near_width, far_width)


if __name__ == "__main__":
    unittest.main()
