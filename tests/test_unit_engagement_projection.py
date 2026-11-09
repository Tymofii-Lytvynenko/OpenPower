import unittest
from dataclasses import replace
from types import SimpleNamespace

import numpy as np

from src.client.controllers.camera_controller import CameraController
from src.client.renderers.unit_projection import UnitProjectionService
from src.core.map.engagement_geometry import EARTH_RADIUS_KM, ENGAGEMENT_RADIUS_KM


class UnitEngagementProjectionTest(unittest.TestCase):
    def test_projection_methods_return_early_for_empty_geometry_and_matrices(self) -> None:
        projection = UnitProjectionService(CameraController(distance=2.6), 360, 180, 1.0)
        self.assertEqual(projection.project_units([], {}, 0, 720), [])
        self.assertEqual(projection.project_units([], {}, 1280, 720), [])
        self.assertEqual(projection.project_surface_ring((1.0, 0.0, 0.0), 0.1, 0, 720), [])
        self.assertEqual(projection.project_surface_ring((0.0, 0.0, 0.0), 0.1, 1280, 720), [])

        prepared = projection.prepare_units(
            [
                {
                    "id": "unit-1",
                    "owner": "AAA",
                    "unit_type": "army",
                    "strength": 100,
                    "current_region_id": 1,
                    "source_region_id": 1,
                    "source_latitude": 0.0,
                    "source_longitude": 0.0,
                }
            ],
            {},
        )
        no_matrices = SimpleNamespace(
            distance=2.6,
            update_matrices=lambda *_args: None,
            get_cached_matrices=lambda: (None, None),
        )
        unavailable_projection = UnitProjectionService(no_matrices, 360, 180, 1.0)
        self.assertEqual(unavailable_projection.project_prepared_units(prepared, 1280, 720), [])
        self.assertEqual(
            unavailable_projection.project_surface_ring((1.0, 0.0, 0.0), 0.1, 1280, 720),
            [],
        )

    def test_invisible_projection_and_surface_ring_segments_are_filtered(self) -> None:
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
                    "source_latitude": 0.0,
                    "source_longitude": 0.0,
                }
            ],
            {},
        )
        camera = SimpleNamespace(
            distance=2.6,
            update_matrices=lambda *_args: None,
            get_cached_matrices=lambda: (
                np.zeros((4, 4), dtype=np.float32),
                np.identity(4, dtype=np.float32),
            ),
        )
        hidden_projection = UnitProjectionService(camera, 360, 180, 1.0)
        self.assertEqual(hidden_projection.project_prepared_units(prepared, 1280, 720), [])

    def test_visible_prepared_unit_projects_billboard_and_readiness_fields(self) -> None:
        camera = SimpleNamespace(
            distance=2.6,
            min_distance=2.0,
            max_distance=10.0,
            update_matrices=lambda *_args: None,
            get_cached_matrices=lambda: (
                np.identity(4, dtype=np.float32),
                np.identity(4, dtype=np.float32),
            ),
        )
        projection = UnitProjectionService(camera, 360, 180, 1.0)
        prepared = projection.prepare_units(
            [
                {
                    "id": "unit-1",
                    "owner": "AAA",
                    "unit_type": "army",
                    "strength": 100,
                    "current_region_id": 1,
                    "source_region_id": 1,
                    "source_latitude": 0.0,
                    "source_longitude": 0.0,
                }
            ],
            {},
        )
        prepared = replace(
            prepared,
            source_vectors=np.asarray([[0.0, 0.0, 1.0]], dtype=np.float32),
            target_vectors=np.asarray([[0.0, 0.0, 1.0]], dtype=np.float32),
        )

        projected = projection.project_prepared_units(prepared, 1280, 720)

        self.assertEqual(len(projected), 1)
        self.assertEqual(projected[0].unit_id, "unit-1")
        self.assertEqual(projected[0].readiness_remaining_label, "0h")
        self.assertGreater(projected[0].width, 0.0)
        self.assertEqual(projected[0].local_position, (0.0, 0.0, 1.0))

    def test_spherical_interpolation_handles_linear_curved_and_antipodal_rows(self) -> None:
        projection = UnitProjectionService(CameraController(distance=2.6), 360, 180, 1.0)
        start = np.asarray(
            [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            dtype=np.float32,
        )
        end = np.asarray(
            [[0.9999, 0.01, 0.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]],
            dtype=np.float32,
        )
        result = projection._slerp_rows(start, end, np.asarray([0.5, 0.5, 0.5]))

        np.testing.assert_allclose(np.linalg.norm(result, axis=1), [1.0, 1.0, 1.0], atol=1e-5)
        np.testing.assert_allclose(result[1], [2**-0.5, 2**-0.5, 0.0], atol=1e-5)
        np.testing.assert_allclose(result[2], start[2], atol=1e-5)
        np.testing.assert_array_equal(projection._safe_normalize(np.zeros(3)), np.zeros(3))

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
        snapshot_progress = projection._presentation_movement_progress(prepared, None)
        local_position = projection._resolve_local_positions(prepared, effective)

        self.assertAlmostEqual(float(effective[0]), 0.5)
        self.assertAlmostEqual(float(snapshot_progress[0]), 0.1)
        self.assertFalse(np.allclose(local_position[0], prepared.source_vectors[0]))

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
