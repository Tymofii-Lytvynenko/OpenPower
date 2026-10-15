import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from imgui_bundle import imgui

from src.client.renderers.unit_renderer import UnitRenderer


class EngagementZoneImGuiTest(unittest.TestCase):
    def test_selected_unit_ring_renders_with_real_imgui(self):
        context = imgui.create_context()
        try:
            io = imgui.get_io()
            io.display_size = (640, 480)
            io.delta_time = 1 / 60
            io.backend_flags |= imgui.BackendFlags_.renderer_has_textures
            imgui.new_frame()
            renderer = UnitRenderer.__new__(UnitRenderer)
            renderer._billboards = [
                SimpleNamespace(unit_id="selected", local_position=(0, 0, 1))
            ]
            renderer._projection = Mock()
            renderer._projection.project_surface_ring.return_value = [
                (10, 10), (30, 10), (30, 30), (10, 30)
            ]
            draw_list = imgui.get_background_draw_list()
            renderer._draw_engagement_zones(
                draw_list, 640, 480, "selected", None, None
            )
            self.assertGreater(len(draw_list.vtx_buffer), 0)
            imgui.end_frame()
        finally:
            imgui.destroy_context(context)
