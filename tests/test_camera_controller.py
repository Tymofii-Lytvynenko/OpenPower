import unittest

from src.client.controllers.camera_controller import CameraController


class CameraControllerTest(unittest.TestCase):
    def test_camera_position_matches_fixed_view_matrix(self) -> None:
        camera = CameraController(distance=2.6)
        camera.yaw = 2.0
        camera.pitch = 0.7

        self.assertEqual(camera.get_position(), (0.0, 0.0, 2.6))

    def test_near_plane_stays_in_front_of_globe_at_closest_zoom(self) -> None:
        camera = CameraController()

        surface_gap = camera.min_distance - 1.0
        self.assertLess(camera.near, surface_gap)

    def test_normalized_map_focus_is_independent_of_texture_resolution(self) -> None:
        original_sized_map = CameraController()
        original_sized_map.look_at_pixel_coords(12_000, 2_400, 16_000, 8_000)

        resized_map = CameraController()
        resized_map.look_at_pixel_fraction(0.75, 0.30, 8_000, 4_000)

        self.assertAlmostEqual(resized_map.yaw, original_sized_map.yaw)
        self.assertAlmostEqual(resized_map.pitch, original_sized_map.pitch)

    def test_drag_and_scroll_apply_sensitivity_and_distance_bounds(self) -> None:
        camera = CameraController(distance=2.6)
        original_yaw = camera.yaw
        original_pitch = camera.pitch

        camera.drag(10, 4)
        self.assertAlmostEqual(camera.yaw, original_yaw + 0.05)
        self.assertAlmostEqual(camera.pitch, original_pitch - 0.02)

        camera.zoom_scroll(4)
        self.assertAlmostEqual(camera.distance, 2.2)
        camera.zoom_scroll(-1000)
        self.assertEqual(camera.distance, camera.max_distance)
        camera.zoom_scroll(1000)
        self.assertEqual(camera.distance, camera.min_distance)

    def test_compatibility_sync_and_column_major_matrix_getter(self) -> None:
        camera = CameraController()

        self.assertIsNone(camera.sync_with_arcade(object()))
        model, view, projection = camera.get_matrices()

        self.assertEqual(len(model), 16)
        self.assertEqual(len(view), 16)
        self.assertEqual(len(projection), 16)
        self.assertEqual(
            model,
            (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0,
             0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0),
        )


if __name__ == "__main__":
    unittest.main()
