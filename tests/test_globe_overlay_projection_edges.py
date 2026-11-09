from types import SimpleNamespace

import numpy as np
import pytest

from src.client.renderers.globe_overlay_projection import (
    GlobeOverlayProjection,
    ProjectedSurfacePoint,
    project_surface_anchor,
)
from tests.test_battle_visual_fixtures import build_camera


def _camera(*, matrices=None, distance=8.0):
    if matrices is None:
        identity = np.eye(4, dtype=np.float32)
        matrices = identity, identity
    return SimpleNamespace(
        yaw=0.0,
        pitch=0.0,
        distance=distance,
        fov_deg=60.0,
        near=0.1,
        far=100.0,
        target=(0.0, 0.0, 0.0),
        update_matrices=lambda *_args: None,
        get_cached_matrices=lambda: matrices,
    )


def _projection(camera=None):
    return GlobeOverlayProjection(camera or build_camera(), 2048, 1024, 1.0)


def _use_front_facing_point(projection, monkeypatch, *, model=None, mvp=None):
    projection._geo = SimpleNamespace(geo_to_unit_vector=lambda _coordinate: (0.0, 0.0, 1.0))
    projection._model_matrix = np.eye(4, dtype=np.float32) if model is None else model
    projection._mvp_matrix = np.eye(4, dtype=np.float32) if mvp is None else mvp
    projection._camera_position = np.array([0.0, 0.0, 10.0], dtype=np.float32)
    monkeypatch.setattr(projection, "prepare", lambda *_args: True)


def test_projected_surface_point_exposes_derived_marker_properties():
    point = ProjectedSurfacePoint(12.0, 34.0, 120.0, 240.0, 0.5, 6.0, 9.0, False)

    assert point.marker_size == 12.0
    assert point.is_front_facing is False
    assert point.screen_position == (120.0, 240.0)


@pytest.mark.parametrize("size", [(0, 600), (800, 0), (-1, 600)])
def test_prepare_rejects_non_positive_viewport_dimensions(size):
    projection = _projection()

    assert projection.prepare(*size) is False


@pytest.mark.parametrize("matrices", [(None, np.eye(4)), (np.eye(4), None)])
def test_prepare_retries_when_camera_does_not_supply_both_matrices(matrices):
    camera = _camera(matrices=matrices)
    projection = _projection(camera)

    assert projection.prepare(800, 600) is False
    assert projection._frame_key is None


@pytest.mark.parametrize(
    "latitude,longitude,width,height",
    [
        (0.0, 180.0, 0, 600),
        ("invalid", 180.0, 800, 600),
        (None, 180.0, 800, 600),
        (91.0, 180.0, 800, 600),
        (0.0, 181.0, 800, 600),
        (float("nan"), 180.0, 800, 600),
    ],
)
def test_project_anchor_rejects_invalid_dimensions_and_coordinates(
    latitude, longitude, width, height
):
    projection = _projection()

    assert projection.project_anchor(latitude, longitude, width, height) is None


def test_project_anchor_returns_none_when_camera_preparation_fails(monkeypatch):
    projection = _projection()
    monkeypatch.setattr(projection, "prepare", lambda *_args: False)

    assert projection.project_anchor(0.0, 180.0, 800, 600) is None


def test_project_anchor_returns_none_when_prepared_matrices_are_missing(monkeypatch):
    projection = _projection()
    monkeypatch.setattr(projection, "prepare", lambda *_args: True)
    projection._model_matrix = None
    projection._mvp_matrix = np.eye(4, dtype=np.float32)
    projection._camera_position = np.array([0.0, 0.0, 10.0], dtype=np.float32)

    assert projection.project_anchor(0.0, 180.0, 800, 600) is None


def test_project_anchor_rejects_a_degenerate_transformed_surface_normal(monkeypatch):
    projection = _projection()
    _use_front_facing_point(projection, monkeypatch, model=np.zeros((4, 4), dtype=np.float32))

    assert projection.project_anchor(0.0, 180.0, 800, 600) is None


def test_project_anchor_rejects_zero_clip_w(monkeypatch):
    projection = _projection()
    _use_front_facing_point(projection, monkeypatch, mvp=np.zeros((4, 4), dtype=np.float32))

    assert projection.project_anchor(0.0, 180.0, 800, 600) is None


def test_project_anchor_rejects_points_outside_the_screen_boundary(monkeypatch):
    projection = _projection()
    mvp = np.eye(4, dtype=np.float32)
    mvp[0, 3] = 2.0
    _use_front_facing_point(projection, monkeypatch, mvp=mvp)

    assert projection.project_anchor(0.0, 180.0, 800, 600) is None


def test_project_anchors_returns_none_for_empty_batches_or_failed_preparation(monkeypatch):
    projection = _projection()
    assert projection.project_anchors([], 800, 600) == []

    monkeypatch.setattr(projection, "prepare", lambda *_args: False)

    assert projection.project_anchors([(0.0, 180.0)], 800, 600) == [None]


def test_project_anchors_returns_none_when_prepared_matrices_are_missing(monkeypatch):
    projection = _projection()
    monkeypatch.setattr(projection, "prepare", lambda *_args: True)
    projection._model_matrix = np.eye(4, dtype=np.float32)
    projection._mvp_matrix = None
    projection._camera_position = np.array([0.0, 0.0, 10.0], dtype=np.float32)

    assert projection.project_anchors([(0.0, 180.0)], 800, 600) == [None]


def test_projected_limb_radius_is_zero_when_camera_is_on_the_globe_surface():
    projection = _projection(_camera(distance=1.0))

    assert projection._projected_limb_radius(600) == 0.0


def test_functional_adapter_forwards_projection_arguments():
    expected = object()
    projection = SimpleNamespace(
        project_anchor=lambda *args, **kwargs: (args, kwargs, expected)
    )

    result = project_surface_anchor(projection, 12.0, 34.0, 800, 600, marker_radius=5.0)

    assert result == (
        (12.0, 34.0, 800, 600),
        {"marker_radius": 5.0},
        expected,
    )
