import unittest

from src.client.controllers.camera_controller import CameraController
from src.client.renderers.unit_projection import UnitProjectionService
from src.core.map.engagement_geometry import EARTH_RADIUS_KM, ENGAGEMENT_RADIUS_KM


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

    def test_presentation_clock_interpolates_movement_between_snapshots(self) -> None:
        projection = UnitProjectionService(CameraController(distance=2.6), 360, 180, 1.0)
        prepared = projection.prepare_units(
            [
                {
                    "id": "unit-1",
                    "owner": "AAA",
                    "unit_type": "army",
                    "strength": 100,
                    "current_region_id": 1,
                    "source_region_id": 1,
                    "target_region_id": 2,
                    "source_latitude": 0.0,
                    "source_longitude": 0.0,
                    "target_latitude": 0.0,
                    "target_longitude": 90.0,
                    "departed_at_minute": 10,
                    "arrival_at_minute": 30,
                    # The server has only published a coarse snapshot value.
                    "movement_progress": 0.1,
                    "is_moving": True,
                }
            ],
            {},
        )

        effective = projection._presentation_movement_progress(prepared, 20.0)

        self.assertAlmostEqual(float(effective[0]), 0.5)

    def test_presentation_progress_clamps_to_movement_schedule(self) -> None:
        projection = UnitProjectionService(CameraController(distance=2.6), 360, 180, 1.0)
        prepared = projection.prepare_units(
            [
                {
                    "id": "unit-1",
                    "current_region_id": 1,
                    "target_region_id": 2,
                    "source_latitude": 0.0,
                    "source_longitude": 0.0,
                    "target_latitude": 0.0,
                    "target_longitude": 90.0,
                    "departed_at_minute": 10,
                    "arrival_at_minute": 30,
                    "movement_progress": 0.8,
                    "is_moving": True,
                }
            ],
            {},
        )

        before_departure = projection._presentation_movement_progress(prepared, 5.0)
        after_arrival = projection._presentation_movement_progress(prepared, 35.0)

        self.assertAlmostEqual(float(before_departure[0]), 0.0)
        self.assertAlmostEqual(float(after_arrival[0]), 1.0)


if __name__ == "__main__":
    unittest.main()
