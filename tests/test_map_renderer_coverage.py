from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.client.renderers import map_renderer as map_renderer_module
from src.client.renderers.base_renderer import BaseRenderer
from src.client.renderers.map_renderer import MapRenderer
from src.core.map.geo import EquirectangularProjection, MapPixelCoordinate


class FakeProgram(dict):
    pass


class FakeContext:
    DEPTH_TEST = "depth-test"

    def __init__(self) -> None:
        self.program_calls = []
        self.enabled_modes = []
        self.disabled_modes = []

    def program(self, **sources):
        self.program_calls.append(sources)
        return FakeProgram()

    def enable_only(self, mode) -> None:
        self.enabled_modes.append(mode)

    def disable(self, mode) -> None:
        self.disabled_modes.append(mode)


class FakeTextureManager:
    def __init__(self, _ctx, _cache_service) -> None:
        self.real_to_dense = {10: 4, 20: 7, 30: 9}
        self.resource_calls = []
        self.selections = []
        self.overlays = []
        self.bound_programs = []

    def load_map_texture(self, *args) -> None:
        self.resource_calls.append(("map", args))

    def load_terrain_texture(self, *args) -> None:
        self.resource_calls.append(("terrain", args))

    def init_lookup_texture(self) -> None:
        self.resource_calls.append(("lookup", ()))

    def set_uniforms(self, program) -> None:
        self.uniform_program = program

    def update_selection(self, dense_ids) -> None:
        self.selections.append(dense_ids)

    def update_overlay(self, color_map) -> None:
        self.overlays.append(color_map)

    def bind_textures(self, program) -> None:
        self.bound_programs.append(program)

    def overlay_transition_progress(self):
        return 0.25


def make_renderer() -> MapRenderer:
    renderer = MapRenderer.__new__(MapRenderer)
    renderer.width = 200
    renderer.height = 100
    renderer.projection_mode = "globe"
    renderer.single_select_dense_id = -1
    renderer._overlay_enabled = True
    renderer._overlay_opacity = 0.9
    renderer._planar_renderer = None
    renderer.globe_radius = 1.0
    renderer.window = SimpleNamespace(get_size=lambda: (800, 600))
    renderer.ctx = FakeContext()
    renderer.texture_manager = FakeTextureManager(renderer.ctx, None)
    renderer.camera = SimpleNamespace(
        update_matrices=MagicMock(),
        get_matrices=MagicMock(return_value=("model", "view", "projection")),
        get_cached_matrices=MagicMock(return_value=("view-projection", "model")),
        get_position=MagicMock(return_value=(1.0, 2.0, 3.0)),
    )
    renderer.program = FakeProgram()
    renderer.sphere = SimpleNamespace(geo=SimpleNamespace(render=MagicMock()))
    renderer.map_data = SimpleNamespace(get_region_id=MagicMock(return_value=42))
    return renderer


def test_constructor_composes_map_resources_and_globe_geometry(monkeypatch, tmp_path: Path) -> None:
    context = FakeContext()
    window = SimpleNamespace(ctx=context)
    monkeypatch.setattr(map_renderer_module.arcade, "get_window", lambda: window)
    monkeypatch.setattr(map_renderer_module.ProjectPaths, "root", lambda: tmp_path)
    monkeypatch.setattr(map_renderer_module, "CacheService", lambda root: ("cache", root))
    monkeypatch.setattr(map_renderer_module, "TextureManager", FakeTextureManager)
    monkeypatch.setattr(map_renderer_module, "MapIndexer", lambda cache: ("indexer", cache))
    monkeypatch.setattr(
        map_renderer_module.ShaderRegistry,
        "load_bundle",
        lambda *_paths: {"vertex_shader": "vertex", "fragment_shader": "fragment"},
    )

    class FakeSphere:
        def __init__(self, ctx, radius, seg_u, seg_v) -> None:
            self.arguments = (ctx, radius, seg_u, seg_v)
            self.geo = SimpleNamespace(render=MagicMock())

        def build_geometry(self, ctx, program) -> None:
            self.build_arguments = (ctx, program)

    monkeypatch.setattr(map_renderer_module, "SphereMesh", FakeSphere)
    map_data = SimpleNamespace(width=200, height=100, packed_map=np.zeros((100, 200), dtype=np.int32))
    map_path = tmp_path / "map.png"
    terrain_path = tmp_path / "terrain.png"

    renderer = MapRenderer(MagicMock(), map_data, map_path, terrain_path)

    assert renderer.window is window
    assert renderer.ctx is context
    assert renderer.projection_mode == "globe"
    assert renderer._overlay_enabled is True
    assert renderer._overlay_opacity == pytest.approx(0.9)
    assert renderer.texture_manager.resource_calls[0][0] == "map"
    assert renderer.texture_manager.resource_calls[1] == ("terrain", (terrain_path,))
    assert renderer.texture_manager.resource_calls[2] == ("lookup", ())
    assert context.program_calls == [{"vertex_shader": "vertex", "fragment_shader": "fragment"}]
    assert renderer.program["u_selected_id"] == -1
    assert renderer.program["u_opacity"] == pytest.approx(0.9)
    assert renderer.sphere.arguments == (context, 1.0, 256, 128)
    assert renderer.sphere.build_arguments == (context, renderer.program)


def test_projection_switch_is_validated_and_planar_renderer_is_lazy(monkeypatch) -> None:
    renderer = make_renderer()
    constructed = []

    class FakePlanarRenderer:
        def __init__(self, *args) -> None:
            constructed.append(args)

    monkeypatch.setattr(map_renderer_module, "PlanarMapRenderer", FakePlanarRenderer)

    with pytest.raises(ValueError, match="Unsupported map projection"):
        renderer.set_projection_mode("mercator")

    renderer.set_projection_mode("planar")
    first_planar_renderer = renderer._planar_renderer
    renderer.set_projection_mode("globe")
    renderer.set_projection_mode("planar")

    assert renderer.projection_mode == "planar"
    assert renderer._planar_renderer is first_planar_renderer
    assert len(constructed) == 1
    assert constructed[0] == (renderer.ctx, renderer.texture_manager, 200, 100)


def test_planar_navigation_delegates_only_when_planar_renderer_is_active() -> None:
    renderer = make_renderer()
    planar = SimpleNamespace(
        pan=MagicMock(),
        zoom_at=MagicMock(),
        focus_pixel=MagicMock(),
    )
    renderer._planar_renderer = planar

    renderer.pan_planar(3.0, -2.0)
    renderer.zoom_planar_at(80.0, 40.0, 2)
    renderer.focus_planar_pixel(20.0, 30.0)
    planar.pan.assert_not_called()
    planar.zoom_at.assert_not_called()
    planar.focus_pixel.assert_not_called()

    renderer.projection_mode = "planar"
    renderer.pan_planar(3.0, -2.0)
    renderer.zoom_planar_at(80.0, 40.0, 2)
    renderer.focus_planar_pixel(20.0, 30.0)

    planar.pan.assert_called_once_with(3.0, -2.0)
    planar.zoom_at.assert_called_once_with(80.0, 40.0, 2, (800, 600))
    planar.focus_pixel.assert_called_once_with(20.0, 30.0)


def test_overlay_style_update_and_highlight_map_real_ids_to_dense_ids() -> None:
    renderer = make_renderer()

    renderer.set_overlay_style(False, 0.4)
    colors = {10: (255, 20, 5, 200)}
    renderer.update_overlay(colors)
    renderer.set_highlight([20, 999])
    renderer.set_highlight([10, 30])
    renderer.set_highlight([999])
    renderer.set_highlight([])

    assert (renderer._overlay_enabled, renderer._overlay_opacity) == (False, 0.4)
    assert renderer.texture_manager.overlays == [colors]
    assert renderer.texture_manager.selections == [set(), {4, 9}, set(), set()]
    assert renderer.single_select_dense_id == -1


def test_draw_routes_planar_mode_and_skips_unavailable_planar_renderer() -> None:
    renderer = make_renderer()
    renderer.projection_mode = "planar"
    renderer._planar_renderer = None

    renderer.draw()

    planar = SimpleNamespace(draw=MagicMock())
    renderer._planar_renderer = planar
    renderer.single_select_dense_id = 7
    renderer.draw()

    planar.draw.assert_called_once_with(
        (800, 600),
        overlay_enabled=True,
        opacity=0.9,
        selected_dense_id=7,
    )
    renderer.camera.update_matrices.assert_not_called()


@pytest.mark.parametrize(
    "program,sphere",
    [(None, object()), (object(), None), (object(), SimpleNamespace(geo=None))],
)
def test_draw_skips_globe_when_program_or_geometry_is_unavailable(program, sphere) -> None:
    renderer = make_renderer()
    renderer.program = program
    renderer.sphere = sphere

    renderer.draw()

    renderer.camera.update_matrices.assert_not_called()
    assert renderer.ctx.enabled_modes == []


def test_draw_binds_globe_uniforms_renders_and_disables_depth_test() -> None:
    renderer = make_renderer()
    renderer.single_select_dense_id = 12

    renderer.draw()

    renderer.camera.update_matrices.assert_called_once_with(800, 600)
    assert renderer.ctx.enabled_modes == [renderer.ctx.DEPTH_TEST]
    assert renderer.texture_manager.bound_programs == [renderer.program]
    assert renderer.program["u_model"] == "model"
    assert renderer.program["u_view"] == "view"
    assert renderer.program["u_projection"] == "projection"
    assert renderer.program["u_selected_id"] == 12
    assert renderer.program["u_camera_pos"] == (1.0, 2.0, 3.0)
    assert renderer.program["u_overlay_mode"] == 1
    assert renderer.program["u_overlay_transition"] == 0.25
    renderer.sphere.geo.render.assert_called_once_with(renderer.program)
    assert renderer.ctx.disabled_modes == [renderer.ctx.DEPTH_TEST]


def test_highlight_clear_resets_single_selection_and_texture_selection() -> None:
    renderer = make_renderer()
    renderer.single_select_dense_id = 5

    renderer.clear_highlight()

    assert renderer.single_select_dense_id == -1
    assert renderer.texture_manager.selections == [set()]


def test_screen_region_and_geo_queries_return_empty_or_projected_values(monkeypatch) -> None:
    renderer = make_renderer()
    renderer.map_data.get_region_id.return_value = 17

    monkeypatch.setattr(renderer, "get_pixel_at_screen_pos", lambda *_args: None)
    assert renderer.get_region_id_at_screen_pos(1, 2) == 0
    assert renderer.get_geo_at_screen_pos(1, 2) is None

    monkeypatch.setattr(renderer, "get_pixel_at_screen_pos", lambda *_args: (20, 30))
    assert renderer.get_region_id_at_screen_pos(1, 2) == 17
    assert renderer.map_data.get_region_id.call_args.args == (20, 30)
    assert renderer.get_geo_at_screen_pos(1, 2) == EquirectangularProjection(200, 100).pixel_to_geo(
        MapPixelCoordinate(20, 30)
    )


def test_screen_pixel_lookup_handles_empty_viewport_and_planar_mode() -> None:
    renderer = make_renderer()
    renderer.window = SimpleNamespace(get_size=lambda: (0, 600))
    assert renderer.get_pixel_at_screen_pos(4, 5) is None

    renderer.window = SimpleNamespace(get_size=lambda: (800, 600))
    renderer.projection_mode = "planar"
    assert renderer.get_pixel_at_screen_pos(4, 5) is None

    planar = SimpleNamespace(screen_to_pixel=MagicMock(return_value=(21, 35)))
    renderer._planar_renderer = planar
    assert renderer.get_pixel_at_screen_pos(4, 5) == (21, 35)
    planar.screen_to_pixel.assert_called_once_with(4, 5, (800, 600))
    renderer.camera.update_matrices.assert_not_called()


@pytest.mark.parametrize(
    "ray,intersection,uv",
    [
        ((None, None), 1.0, (0.5, 0.5)),
        ((np.zeros(3), np.ones(3)), None, (0.5, 0.5)),
        ((np.zeros(3), np.ones(3)), 1.0, None),
    ],
    ids=["ray-miss", "sphere-miss", "uv-miss"],
)
def test_globe_pixel_lookup_stops_when_picking_stage_misses(monkeypatch, ray, intersection, uv) -> None:
    renderer = make_renderer()
    monkeypatch.setattr(map_renderer_module.PickingUtils, "screen_to_ray", lambda *_args: ray)
    monkeypatch.setattr(map_renderer_module.PickingUtils, "ray_sphere_intersect", lambda *_args: intersection)
    monkeypatch.setattr(map_renderer_module.PickingUtils, "world_to_uv_coords", lambda *_args: uv)
    pixel_lookup = MagicMock(return_value=(1, 2))
    monkeypatch.setattr(map_renderer_module.PickingUtils, "uv_to_pixel_coords", pixel_lookup)

    assert renderer.get_pixel_at_screen_pos(12, 24) is None
    pixel_lookup.assert_not_called()


def test_globe_pixel_lookup_projects_ray_hit_to_map_pixel(monkeypatch) -> None:
    renderer = make_renderer()
    ray_origin = np.array([0.0, 0.0, 2.0])
    ray_direction = np.array([0.0, 0.0, -1.0])
    monkeypatch.setattr(
        map_renderer_module.PickingUtils,
        "screen_to_ray",
        lambda *_args: (ray_origin, ray_direction),
    )
    monkeypatch.setattr(map_renderer_module.PickingUtils, "ray_sphere_intersect", lambda *_args: 1.0)
    monkeypatch.setattr(map_renderer_module.PickingUtils, "world_to_uv_coords", lambda *_args: (0.25, 0.75))
    pixel_lookup = MagicMock(return_value=(49, 24))
    monkeypatch.setattr(map_renderer_module.PickingUtils, "uv_to_pixel_coords", pixel_lookup)

    assert renderer.get_pixel_at_screen_pos(400, 300) == (49, 24)

    renderer.camera.update_matrices.assert_called_once_with(800, 600)
    pixel_lookup.assert_called_once_with(0.25, 0.75, 200, 100)


def test_globe_pixel_lookup_stops_when_camera_matrices_are_missing(monkeypatch) -> None:
    renderer = make_renderer()
    renderer.camera.get_cached_matrices.return_value = (None, "model")
    ray_lookup = MagicMock(return_value=(np.zeros(3), np.ones(3)))
    monkeypatch.setattr(map_renderer_module.PickingUtils, "screen_to_ray", ray_lookup)

    assert renderer.get_pixel_at_screen_pos(12, 24) is None

    renderer.camera.update_matrices.assert_called_once_with(800, 600)
    ray_lookup.assert_not_called()
