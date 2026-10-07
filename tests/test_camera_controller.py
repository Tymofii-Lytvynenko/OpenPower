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


if __name__ == "__main__":
    unittest.main()
