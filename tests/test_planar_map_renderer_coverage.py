from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.client.renderers import planar_map_renderer as planar_module
from src.client.renderers.planar_map_renderer import PlanarMapRenderer, PlanarMapTransform


class RecordingProgram(dict):
    pass


class FakeContext:
    DEPTH_TEST = "depth-test"

    def __init__(self) -> None:
        self.program_calls = []
        self.disabled = []

    def program(self, **sources):
        self.program_calls.append(sources)
        return RecordingProgram()

    def disable(self, mode) -> None:
        self.disabled.append(mode)


class FakeTextureManager:
    def __init__(self) -> None:
        self.uniform_programs = []
        self.bound_programs = []
        self.transition_calls = 0

    def set_uniforms(self, program) -> None:
        self.uniform_programs.append(program)

    def bind_textures(self, program) -> None:
        self.bound_programs.append(program)

    def overlay_transition_progress(self):
        self.transition_calls += 1
        return 0.75


def test_planar_renderer_builds_shader_uniforms_and_geometry(monkeypatch) -> None:
    context = FakeContext()
    texture_manager = FakeTextureManager()
    geometry = SimpleGeometry()
    shader_bundle = {"vertex_shader": "vertex", "fragment_shader": "fragment"}
    monkeypatch.setattr(planar_module.ShaderRegistry, "load_bundle", lambda *_args: shader_bundle)
    monkeypatch.setattr(planar_module.arcade.gl.geometry, "quad_2d_fs", lambda: geometry)

    renderer = PlanarMapRenderer(context, texture_manager, map_width=0, map_height=-4)

    assert (renderer.map_width, renderer.map_height) == (1, 1)
    assert (renderer.transform.map_width, renderer.transform.map_height) == (1, 1)
    assert context.program_calls == [shader_bundle]
    assert renderer.program == {
        "u_map_texture": 0,
        "u_lookup_texture": 1,
        "u_terrain_texture": 2,
        "u_previous_lookup_texture": 3,
    }
    assert texture_manager.uniform_programs == [renderer.program]
    assert renderer.geometry is geometry


class SimpleGeometry:
    def __init__(self) -> None:
        self.render = MagicMock()


def test_planar_renderer_draw_skips_empty_viewports_and_sets_draw_uniforms() -> None:
    context = FakeContext()
    texture_manager = FakeTextureManager()
    renderer = PlanarMapRenderer.__new__(PlanarMapRenderer)
    renderer.context = context
    renderer.texture_manager = texture_manager
    renderer.map_width = 200
    renderer.map_height = 100
    renderer.transform = PlanarMapTransform(200, 100)
    renderer.program = RecordingProgram()
    renderer.geometry = SimpleGeometry()

    renderer.draw((0, 600), overlay_enabled=False, opacity=0.2, selected_dense_id=9)
    assert context.disabled == []
    assert texture_manager.bound_programs == []

    renderer.transform.pan(3, -2)
    renderer.transform.zoom = 2.0
    renderer.draw((800, 600), overlay_enabled=False, opacity=0.2, selected_dense_id=9)

    assert context.disabled == [context.DEPTH_TEST]
    assert texture_manager.bound_programs == [renderer.program]
    assert renderer.program["u_viewport_size"] == (800.0, 600.0)
    assert renderer.program["u_map_size"] == (200.0, 100.0)
    assert renderer.program["u_map_center"] == (0.5, 0.5)
    assert renderer.program["u_pan"] == (3.0, -2.0)
    assert renderer.program["u_zoom"] == 2.0
    assert renderer.program["u_selected_id"] == 9
    assert renderer.program["u_overlay_mode"] == 0
    assert renderer.program["u_opacity"] == pytest.approx(0.2)
    assert renderer.program["u_overlay_transition"] == pytest.approx(0.75)
    renderer.geometry.render.assert_called_once_with(renderer.program)


def test_planar_renderer_view_and_navigation_methods_delegate_to_transform() -> None:
    renderer = PlanarMapRenderer.__new__(PlanarMapRenderer)
    renderer.transform = MagicMock()
    renderer.transform.screen_to_pixel.return_value = (12, 34)

    assert renderer.screen_to_pixel(4, 5, (800, 600)) == (12, 34)
    renderer.pan(3, -2)
    renderer.zoom_at(80, 40, 2, (800, 600))
    renderer.focus_pixel(20, 30)

    renderer.transform.screen_to_pixel.assert_called_once_with(4, 5, (800, 600))
    renderer.transform.pan.assert_called_once_with(3, -2)
    renderer.transform.zoom_at.assert_called_once_with(80, 40, 2, (800, 600))
    renderer.transform.focus_pixel.assert_called_once_with(20, 30)


def test_transform_clamps_dimensions_focuses_edges_and_rejects_outside_picks() -> None:
    transform = PlanarMapTransform(0, -3)

    assert (transform.map_width, transform.map_height) == (1, 1)
    assert transform.screen_to_pixel(0, 0, (0, 100)) is None
    assert transform.screen_to_pixel(100, 50, (100, 100)) is None

    transform.focus_pixel(-10, 10)
    assert transform.center_u == 0.0
    assert transform.center_v == 0.0
    transform.focus_pixel(10, -10)
    assert transform.center_u == 1.0
    assert transform.center_v == 1.0
    assert transform.screen_to_pixel(50, 50, (100, 100)) is None


def test_transform_zoom_ignores_invalid_input_and_clamps_zoom_limits() -> None:
    transform = PlanarMapTransform(200, 100)

    transform.zoom_at(50, 50, 1, (0, 600))
    transform.zoom_at(50, 50, 0, (800, 600))
    assert transform.zoom == 1.0

    transform.zoom_at(50, 50, -10, (800, 600))
    assert transform.zoom == transform.MIN_ZOOM
    transform.zoom = transform.MAX_ZOOM
    transform.zoom_at(50, 50, 10, (800, 600))
    assert transform.zoom == transform.MAX_ZOOM

    transform.pan(4, 5)
    transform.zoom_at(50, 50, -1, (800, 600))
    assert transform.zoom < transform.MAX_ZOOM
