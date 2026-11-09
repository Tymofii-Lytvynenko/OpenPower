import numpy as np
import pytest

from src.client.utils.picking_utils import PickingUtils


def test_ray_sphere_intersection_covers_miss_entry_exit_and_inside_origin():
    assert PickingUtils.ray_sphere_intersect(
        np.array([0.0, 0.0, 5.0]), np.array([0.0, 0.0, -1.0]), 1.0
    ) == 4.0
    assert PickingUtils.ray_sphere_intersect(
        np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]), 1.0
    ) == 1.0
    assert PickingUtils.ray_sphere_intersect(
        np.array([1.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]), 1.0
    ) is None
    assert PickingUtils.ray_sphere_intersect(
        np.array([0.0, 0.0, 5.0]), np.array([0.0, 1.0, 0.0]), 1.0
    ) is None


def test_ray_sphere_intersection_retains_single_positive_root_fallback(monkeypatch):
    # A negative square root is impossible in production; it exercises the defensive single-root fallback.
    monkeypatch.setattr(np, "sqrt", lambda _value: -1.0)

    distance = PickingUtils.ray_sphere_intersect(
        np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]), 1.0
    )

    assert distance == 0.5


def test_screen_to_ray_rejects_invalid_viewports_and_singular_matrices():
    assert PickingUtils.screen_to_ray(10, 10, 0, 20, np.eye(4)) == (None, None)
    assert PickingUtils.screen_to_ray(10, 10, 20, 0, np.eye(4)) == (None, None)
    assert PickingUtils.screen_to_ray(10, 10, 20, 20, np.zeros((4, 4))) == (None, None)


def test_screen_to_ray_unprojects_center_and_normalizes_direction():
    origin, direction = PickingUtils.screen_to_ray(50, 50, 100, 100, np.eye(4))

    np.testing.assert_allclose(origin, [0.0, 0.0, -1.0])
    np.testing.assert_allclose(direction, [0.0, 0.0, 1.0])


@pytest.mark.parametrize("last_row", ([0, 0, 1, 1], [0, 0, -1, 1]))
def test_screen_to_ray_rejects_near_or_far_points_at_infinity(monkeypatch, last_row):
    inverse = np.eye(4)
    inverse[3] = last_row
    monkeypatch.setattr(np.linalg, "inv", lambda _matrix: inverse)

    assert PickingUtils.screen_to_ray(50, 50, 100, 100, np.eye(4)) == (None, None)


def test_screen_to_ray_rejects_degenerate_zero_length_direction(monkeypatch):
    inverse = np.zeros((4, 4))
    inverse[3, 3] = 1.0
    monkeypatch.setattr(np.linalg, "inv", lambda _matrix: inverse)

    assert PickingUtils.screen_to_ray(50, 50, 100, 100, np.eye(4)) == (None, None)


def test_world_to_uv_rejects_singular_models_and_origin_hits():
    assert PickingUtils.world_to_uv_coords(np.ones(3), np.zeros((4, 4))) is None
    assert PickingUtils.world_to_uv_coords(np.zeros(3), np.eye(4)) is None


def test_world_to_uv_wraps_negative_longitude_and_maps_latitude():
    assert PickingUtils.world_to_uv_coords(np.array([1.0, 0.0, -1.0]), np.eye(4)) == pytest.approx((0.875, 0.5))
    assert PickingUtils.world_to_uv_coords(np.array([0.0, 1.0, 0.0]), np.eye(4)) == pytest.approx((0.0, 0.0))


def test_uv_to_pixel_wraps_longitude_and_clamps_vertical_coordinate():
    assert PickingUtils.uv_to_pixel_coords(1.25, 2.0, 100, 50) == (25, 0)
    assert PickingUtils.uv_to_pixel_coords(-0.25, 0.0, 100, 50) == (75, 49)
