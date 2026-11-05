from types import SimpleNamespace

import numpy as np
import pytest

from src.client.controllers.camera_controller import CameraController
from src.client.controllers.viewport_controller import ViewportController
from src.client.renderers.mini_map_texture import MiniMapRasterizer
from src.client.renderers.texture_manager import TextureManager


def test_mini_map_rasterizer_samples_region_colors_and_water() -> None:
    source = np.zeros((8, 16), dtype=np.int32)
    source[0:4, 4:12] = 1
    source[0:4, 12:16] = 2
    source[4:8, 4:8] = 1
    source[4:8, 8:16] = 2
    original = source.copy()

    raster = MiniMapRasterizer((4, 2)).rasterize(
        source,
        {1: (100, 50, 20), 2: (10, 20, 30)},
    )

    assert raster.shape == (2, 4, 4)
    assert tuple(raster[0, 0]) == MiniMapRasterizer.WATER
    assert tuple(raster[0, 1]) == (100, 50, 20, 255)
    assert tuple(raster[0, 2]) == MiniMapRasterizer.BORDER
    assert tuple(raster[0, 3]) == (10, 20, 30, 255)
    assert np.array_equal(source, original)


def test_texture_manager_exposes_read_only_palette_for_ui_renderers() -> None:
    manager = object.__new__(TextureManager)
    manager._active_color_map = {7: (12, 34, 56)}

    assert manager.active_color_map[7] == (12, 34, 56)
    with pytest.raises(TypeError):
        manager.active_color_map[7] = (1, 2, 3)


def test_globe_minimap_focus_and_zoom_use_normalized_coordinates() -> None:
    camera = CameraController()
    renderer = SimpleNamespace(width=360, height=180, projection_mode="globe")
    viewport = object.__new__(ViewportController)
    viewport.cam = camera
    viewport.renderer = renderer

    viewport.focus_on_map_fraction(0.25, 0.75)
    assert viewport.map_center_fraction() == pytest.approx((0.25, 0.75))

    viewport.set_zoom_fraction(0.75)
    assert viewport.zoom_fraction() == pytest.approx(0.75)
    assert camera.distance == pytest.approx(2.325)


def test_planar_minimap_zoom_uses_logarithmic_camera_range() -> None:
    from src.client.renderers.planar_map_renderer import PlanarMapTransform

    transform = PlanarMapTransform(360, 180)
    renderer = SimpleNamespace(
        width=360,
        height=180,
        projection_mode="planar",
        _planar_renderer=SimpleNamespace(transform=transform),
    )
    renderer.focus_planar_pixel = transform.focus_pixel
    viewport = object.__new__(ViewportController)
    viewport.renderer = renderer

    viewport.focus_on_map_fraction(0.25, 0.75)
    assert viewport.map_center_fraction() == pytest.approx((90.5 / 360, 135.5 / 180))
    viewport.set_zoom_fraction(0.5)
    assert transform.zoom == pytest.approx(8.0)
    assert viewport.zoom_fraction() == pytest.approx(0.5)
