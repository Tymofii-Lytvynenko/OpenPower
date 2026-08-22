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


if __name__ == "__main__":
    unittest.main()
