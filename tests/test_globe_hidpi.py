"""Verify view rendering, picking and flags on Arcade's DPI-aware window buffer."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import arcade
import numpy as np
from PIL import Image
from OpenGL.GL import GL_VIEWPORT, glGetIntegerv

from src.client.controllers.camera_controller import CameraController
from src.client.renderers.map_renderer import MapRenderer
from src.client.renderers.unit_batch_renderer import UnitBatchRenderer
from src.client.renderers.unit_projection import UnitProjectionService
from src.client.utils.picking_utils import PickingUtils
from src.client.views.game_view import GameView
from src.client.views.main_menu_view import MainMenuView
from src.client.views.new_game_view import NewGameView
from src.core.cache_service import CacheService
from src.core.map.geo import GeoCoordinate
from src.core.map_data import RegionMapData


@unittest.skipUnless(
    os.environ.get("RUN_MAP_RENDERER_GPU_CHECKS") == "1",
    "Set RUN_MAP_RENDERER_GPU_CHECKS=1 to check window rendering on OpenGL.",
)
class GlobeHiDpiTest(unittest.TestCase):
    def test_rendered_selection_and_flags_match_mouse_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            map_path = root / "regions.png"
            yy, xx = np.indices((360, 720))
            ids = (1 + xx // 60 + (yy // 60) * 12).astype(np.uint32)
            pixels = np.stack(((ids >> 16) & 255, (ids >> 8) & 255, ids & 255), axis=-1)
            Image.fromarray(pixels.astype(np.uint8)).save(map_path)
            window = arcade.Window(720, 540, visible=False, antialiasing=False)
            try:
                camera = CameraController()
                with (
                    patch("src.core.cache_service.ProjectPaths.cache", return_value=root / "cache"),
                    patch.object(CacheService, "save_numpy_array"),
                    patch.object(CacheService, "save_numpy_archive"),
                ):
                    renderer = MapRenderer(camera, RegionMapData(str(map_path)), map_path, map_path)
                batch = UnitBatchRenderer()
                flag_texture = window.ctx.texture((1, 1), components=4, data=bytes((255, 0, 0, 255)))
                flags = SimpleNamespace(
                    texture=flag_texture, texture_id=flag_texture.glo,
                    entry_for=lambda _owner: SimpleNamespace(u0=0, v0=0, u1=1, v1=1),
                )
                noop = lambda *args, **kwargs: None
                overlay = SimpleNamespace(render=noop)
                view = SimpleNamespace(
                    window=window, clear=window.clear, renderer=renderer,
                    imgui=SimpleNamespace(new_frame=noop, render=noop, real_fps=60),
                    ui=SimpleNamespace(setup_frame=noop), _render_menu_window=noop, _render_ui=noop,
                    net=SimpleNamespace(get_state=lambda: None, get_display_total_minutes=lambda: 0),
                    viewport_ctrl=SimpleNamespace(refresh_map_layer_if_stale=noop, show_all_units=True,
                                                  selected_country_tag=None, show_engagement_zones=False),
                    unit_renderer=overlay, event_renderer=overlay, battle_effect_renderer=overlay,
                    unit_context_menu=overlay, unit_details_window=overlay, layout=overlay,
                    unit_interactions=SimpleNamespace(selected_unit_id=None, selected_unit_ids=set(),
                                                      hovered_unit_id=None, drag_preview=None),
                    player_tag="AAA", selected_region_id=None, _active_selection_rect=lambda: None,
                    nav=SimpleNamespace(),
                )
                fw, fh = window.get_framebuffer_size()
                # Retain the REAL default framebuffer. Offscreen buffers bypass
                # Arcade's automatic DPI scaling and cannot catch double scaling.
                for scale in (1.0, 1.25, 1.5):
                    width, height = round(fw / scale), round(fh / scale)
                    with (
                        patch.object(window, "get_size", return_value=(width, height)),
                        patch.object(window, "get_pixel_ratio", return_value=scale),
                    ):
                        for draw in (MainMenuView.on_draw, NewGameView.on_draw, GameView.on_draw):
                            for yaw, pitch, distance in ((0.0, 0.0, 2.6), (0.7, 0.3, 1.8), (-0.5, -0.4, 3.2)):
                                camera.yaw, camera.pitch, camera.distance = yaw, pitch, distance
                                for fx, fy in ((0.454, 0.456), (0.548, 0.537)):
                                    with self.subTest(scale=scale, view=draw.__qualname__, yaw=yaw, x=fx):
                                        x, y = fx * width, fy * height
                                        px, py = int(x * scale), int(y * scale)
                                        renderer.single_select_dense_id = -1
                                        draw(view)
                                        physical_viewport = glGetIntegerv(GL_VIEWPORT)
                                        self.assertLessEqual(abs(physical_viewport[2] - fw), 1)
                                        self.assertLessEqual(abs(physical_viewport[3] - fh), 1)
                                        before = tuple(window.ctx.screen.read(viewport=(px, py, 1, 1)))
                                        region_id = renderer.get_region_id_at_screen_pos(x, y)
                                        self.assertGreater(region_id, 0)
                                        renderer.single_select_dense_id = renderer.texture_manager.real_to_dense[region_id]
                                        draw(view)
                                        after = tuple(window.ctx.screen.read(viewport=(px, py, 1, 1)))
                                        self.assertGreater(after[0] - before[0], 80)

                                        vp, model = camera.get_cached_matrices()
                                        ray_o, ray_d = PickingUtils.screen_to_ray(x, y, width, height, vp)
                                        t = PickingUtils.ray_sphere_intersect(ray_o, ray_d, 1.0)
                                        u, v = PickingUtils.world_to_uv_coords(ray_o + ray_d * t, model)
                                        geo = GeoCoordinate((v - 0.5) * 180, u * 360 - 180)
                                        projection = UnitProjectionService(camera, 720, 360, 1.0)
                                        units = projection.project_units([{
                                            "id": "flag", "owner": "AAA", "current_region_id": region_id,
                                            "latitude": geo.latitude, "longitude": geo.longitude,
                                        }], {}, width, height)
                                        self.assertEqual(len(units), 1)
                                        self.assertAlmostEqual(units[0].screen_x, x, delta=0.01)
                                        self.assertAlmostEqual(units[0].screen_y, y, delta=0.01)
                                        self.assertTrue(batch.render(units, flags, width, height))
                                        self.assertEqual(tuple(window.ctx.screen.read(viewport=(px, py, 1, 1))), (255, 0, 0))
            finally:
                window.close()
