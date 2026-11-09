from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

from src.client.ui.components.hud import mini_map as mini_map_module
from src.client.ui.components.hud.mini_map import MiniMapPanel


class FakeWidgets:
    rects = {}
    hitboxes = {}
    hitbox_states = {}
    calls = []

    def __init__(self, root):
        self.root = root

    def frame(self, slot):
        self.calls.append(("frame", self.root, slot))

    def rect(self, slot):
        self.calls.append(("rect", self.root, slot))
        return self.rects.get(slot)

    def picture(self, slot, draw):
        self.calls.append(("picture", self.root, slot))
        draw(80, 40)

    def hitbox(self, slot, test_id, **kwargs):
        self.calls.append(("hitbox", self.root, slot, test_id, kwargs))
        return self.hitboxes.get(test_id, False)

    def hitbox_state(self, slot, test_id):
        self.calls.append(("hitbox_state", self.root, slot, test_id))
        return self.hitbox_states.get(test_id, (False, False))


class FakeTextureCache:
    def __init__(self):
        self.get_texture = Mock(return_value="texture")
        self.draw = Mock()
        self.close = Mock()


def install(monkeypatch, *, window_open=True):
    imgui = Mock()
    imgui.WindowFlags_ = SimpleNamespace(
        no_title_bar=1, no_resize=2, no_move=4, no_collapse=8, no_saved_settings=16,
    )
    imgui.MouseButton_ = SimpleNamespace(left="left")
    imgui.get_io.return_value.display_size = SimpleNamespace(x=1000, y=700)
    imgui.get_window_pos.return_value = SimpleNamespace(x=5.0, y=7.0)
    imgui.get_color_u32.side_effect = lambda color: tuple(color)
    imgui.get_mouse_pos.return_value = SimpleNamespace(x=500.0, y=350.0)
    imgui.is_mouse_dragging.return_value = False
    FakeWidgets.rects = {}
    FakeWidgets.hitboxes = {}
    FakeWidgets.hitbox_states = {}
    FakeWidgets.calls = []
    monkeypatch.setattr(mini_map_module, "imgui", imgui)
    monkeypatch.setattr(mini_map_module, "GMLWidgets", FakeWidgets)
    monkeypatch.setattr(mini_map_module, "set_widget_value", Mock())
    monkeypatch.setattr(mini_map_module, "MiniMapTextureCache", FakeTextureCache)
    windows = []

    @contextmanager
    def window(*args, **kwargs):
        windows.append((args, kwargs))
        yield window_open

    monkeypatch.setattr(mini_map_module.WindowManager, "window", staticmethod(window))
    return imgui, windows


def make_viewport(*, width=1000, height=700, mode="political", texture_manager=None):
    renderer = SimpleNamespace(
        map_data="map-data",
        texture_manager=texture_manager,
    )
    viewport = Mock()
    viewport.renderer = renderer
    viewport.current_mode_key = mode
    viewport.map_center_fraction.return_value = (0.5, 0.5)
    viewport.zoom_fraction.return_value = 0.5
    return viewport


def test_render_skips_missing_map_and_invalid_viewport_and_closes_cache(monkeypatch):
    imgui, windows = install(monkeypatch)
    viewport = make_viewport()
    panel = MiniMapPanel(viewport, "UKR")

    viewport.renderer.map_data = None
    panel.render()
    assert windows == []

    viewport.renderer.map_data = "map-data"
    imgui.get_io.return_value.display_size = SimpleNamespace(x=0, y=600)
    panel.render()
    assert windows == []

    panel.close()
    panel.texture_cache.close.assert_called_once_with()


def test_render_positions_window_and_skips_contents_when_native_window_is_closed(monkeypatch):
    _imgui, windows = install(monkeypatch, window_open=False)
    viewport = make_viewport()
    panel = MiniMapPanel(viewport, "UKR")
    panel._render_contents = Mock()

    panel.render()

    assert windows[0][0] == ("MINI MAP",)
    assert windows[0][1]["x"] == 772.0
    assert windows[0][1]["y"] == 545.0
    panel._render_contents.assert_not_called()

    _imgui, windows = install(monkeypatch)
    _imgui.get_io.return_value.display_size = SimpleNamespace(x=100, y=80)
    panel = MiniMapPanel(make_viewport(), "UKR")
    panel._render_contents = Mock()
    panel.render()
    assert windows[0][1]["x"] == 0.0
    assert windows[0][1]["y"] == 0.0
    panel._render_contents.assert_called_once()


def test_content_returns_when_source_map_rectangle_is_unavailable(monkeypatch):
    install(monkeypatch)
    panel = MiniMapPanel(make_viewport(), "UKR")
    panel._render_contents(object(), "map-data")

    panel.texture_cache.get_texture.assert_called_once_with(
        "map-data", {}, mode_key="political", overlay_revision=0,
    )
    assert FakeWidgets.calls == [
        ("frame", "Mini_Map", "frmMap"),
        ("rect", "Mini_Map", "frmMap/btnMap"),
    ]


def test_content_draws_map_controls_and_routes_map_zoom_home_and_magnifier_actions(monkeypatch):
    imgui, _windows = install(monkeypatch)
    texture_manager = SimpleNamespace(active_color_map={2: (10, 20, 30)}, overlay_revision=7)
    viewport = make_viewport(mode="political", texture_manager=texture_manager)
    viewport.map_center_fraction.return_value = (2.0, -1.0)
    viewport.zoom_fraction.return_value = 1.4
    viewport.show_all_units = False
    interacted = Mock()
    panel = MiniMapPanel(viewport, "UKR", on_interaction=interacted)
    FakeWidgets.rects = {
        "frmMap/btnMap": SimpleNamespace(x=10, y=20, width=100, height=50),
        "btnZoom": SimpleNamespace(x=120, y=20, width=10, height=100),
        "btnHome": SimpleNamespace(x=140, y=20, width=20, height=30),
        "togMagnifier": SimpleNamespace(x=170, y=20, width=24, height=24),
    }
    FakeWidgets.hitbox_states = {"mini_map.zoom": (False, True), "mini_map.map": (False, True)}
    FakeWidgets.hitboxes = {"mini_map.home": True, "mini_map.magnifier": True}
    imgui.is_mouse_dragging.return_value = True
    imgui.get_mouse_pos.side_effect = [
        SimpleNamespace(x=0.0, y=127.0),
        SimpleNamespace(x=1000.0, y=-100.0),
    ]

    panel._render_contents(viewport.renderer, "map-data")

    panel.texture_cache.get_texture.assert_called_once_with(
        "map-data", {2: (10, 20, 30)}, mode_key="political", overlay_revision=7,
    )
    panel.texture_cache.draw.assert_called_once_with("texture", 80, 40, test_id="mini_map.image")
    viewport.set_zoom_fraction.assert_called_once_with(0.0)
    viewport.focus_on_map_fraction.assert_called_once_with(1.0, 0.0)
    viewport.focus_on_country.assert_called_once_with("UKR")
    assert viewport.show_all_units is True
    assert interacted.call_args_list == [
        (("mini_map.zoom",),), (("mini_map.navigate",),),
    ]
    assert mini_map_module.set_widget_value.call_args.args == ("mini_map.magnifier", True)
    draw = imgui.get_window_draw_list.return_value
    assert draw.add_triangle_filled.called
    assert draw.add_rect_filled.call_count >= 7
    assert draw.add_line.call_count >= 15
    assert draw.add_rect.call_count >= 2


def test_terrain_mode_uses_default_palette_and_missing_texture_still_draws_crosshair(monkeypatch):
    imgui, _windows = install(monkeypatch)
    texture_manager = SimpleNamespace(active_color_map={1: (1, 2, 3)}, overlay_revision=2)
    viewport = make_viewport(mode="terrain", texture_manager=texture_manager)
    panel = MiniMapPanel(viewport, "UKR")
    panel.texture_cache.get_texture.return_value = None
    FakeWidgets.rects = {"frmMap/btnMap": SimpleNamespace(x=0, y=0, width=100, height=50)}

    panel._render_contents(viewport.renderer, "map-data")

    panel.texture_cache.get_texture.assert_called_once_with(
        "map-data", {}, mode_key="terrain", overlay_revision=2,
    )
    assert not any(call[0] == "picture" for call in FakeWidgets.calls)
    assert imgui.get_window_draw_list.return_value.add_line.call_count == 2
    assert imgui.get_window_draw_list.return_value.add_rect.call_count == 2


def test_control_helpers_handle_missing_slots_and_optional_viewport_methods(monkeypatch):
    imgui, _windows = install(monkeypatch)
    viewport = SimpleNamespace()
    panel = MiniMapPanel(viewport, "UKR")
    widgets = FakeWidgets("Mini_Map")
    draw = Mock()

    panel._draw_zoom(draw, widgets, (0.0, 0.0))
    panel._draw_home(draw, widgets, (0.0, 0.0))
    panel._draw_magnifier(draw, widgets, (0.0, 0.0))
    assert panel._map_center() == (0.5, 0.5)
    assert panel._zoom_fraction() == 0.5
    panel._set_zoom_fraction(2.0)
    assert MiniMapPanel._window_origin() == (5.0, 7.0)

    FakeWidgets.rects = {"btnZoom": SimpleNamespace(x=1, y=2, width=0, height=0)}
    panel._draw_zoom(draw, widgets, (0.0, 0.0))
    assert imgui.get_mouse_pos.called is False


def test_zoom_fraction_and_map_center_are_clamped_and_controls_without_callbacks_remain_safe(monkeypatch):
    imgui, _windows = install(monkeypatch)
    viewport = Mock()
    viewport.zoom_fraction.return_value = -2.0
    viewport.map_center_fraction.return_value = (-1.0, 3.0)
    panel = MiniMapPanel(viewport, "UKR")
    FakeWidgets.rects = {"btnZoom": SimpleNamespace(x=2, y=3, width=8, height=10)}
    FakeWidgets.hitbox_states = {"mini_map.zoom": (True, False)}
    imgui.get_mouse_pos.return_value = SimpleNamespace(x=0, y=50)

    panel._draw_zoom(Mock(), FakeWidgets("Mini_Map"), (0.0, 0.0))

    viewport.set_zoom_fraction.assert_called_once_with(0.0)
    assert panel._map_center() == (0.0, 1.0)
