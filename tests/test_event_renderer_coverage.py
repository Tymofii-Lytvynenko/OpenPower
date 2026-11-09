from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import polars as pl
import pytest

import src.client.renderers.event_renderer as event_renderer_module
from src.client.renderers.event_renderer import EventRenderer
from src.core.map.geo import GeoCoordinate


class _DrawList:
    def __init__(self):
        self.calls = []

    def add_rect_filled(self, *args, **kwargs):
        self.calls.append(("filled", args, kwargs))

    def add_rect(self, *args, **kwargs):
        self.calls.append(("rect", args, kwargs))

    def add_text(self, *args, **kwargs):
        self.calls.append(("text", args, kwargs))

    def add_triangle_filled(self, *args, **kwargs):
        self.calls.append(("triangle", args, kwargs))


class _FakeImGui:
    WindowFlags_ = SimpleNamespace(
        no_decoration=1,
        no_background=2,
        no_inputs=4,
        no_saved_settings=8,
        no_focus_on_appearing=16,
        no_nav=32,
    )

    def __init__(self, *, size=(800, 600), begin=True):
        self.display_size = SimpleNamespace(x=size[0], y=size[1])
        self.begin_result = begin
        self.draw_list = _DrawList()
        self.calls = []

    def get_io(self):
        return SimpleNamespace(display_size=self.display_size)

    def set_next_window_pos(self, *args):
        self.calls.append(("position", args))

    def set_next_window_size(self, *args):
        self.calls.append(("size", args))

    def begin(self, *args):
        self.calls.append(("begin", args))
        return self.begin_result, None

    def get_window_draw_list(self):
        return self.draw_list

    def end(self):
        self.calls.append(("end",))

    def calc_text_size(self, text):
        return SimpleNamespace(x=float(len(text) * 8), y=12.0)

    def get_color_u32(self, color):
        return color


def _renderer(*, matrices=None):
    camera = SimpleNamespace(
        distance=3.0,
        update_matrices=Mock(),
        get_cached_matrices=Mock(return_value=matrices or (np.eye(4), np.eye(4))),
    )
    renderer = EventRenderer(camera, 360, 180, 1.0)
    renderer._geo = SimpleNamespace(
        geo_to_unit_vector=lambda _geo: (0.0, 0.0, 1.0),
        pixel_to_geo=lambda point: GeoCoordinate(latitude=point.y, longitude=point.x),
    )
    return renderer, camera


def test_render_skips_missing_state_and_empty_event_list(monkeypatch):
    renderer, camera = _renderer()
    imgui = _FakeImGui()
    monkeypatch.setattr(event_renderer_module, "imgui", imgui)

    renderer.render(None)
    renderer.render(SimpleNamespace(globals={"active_events": []}, tables={}))

    camera.update_matrices.assert_not_called()
    assert imgui.calls == []


@pytest.mark.parametrize("size", [(0, 600), (800, 0)])
def test_render_skips_nonpositive_viewport_dimensions(monkeypatch, size):
    renderer, camera = _renderer()
    monkeypatch.setattr(event_renderer_module, "imgui", _FakeImGui(size=size))
    renderer._refresh_region_cache = Mock()

    renderer.render(SimpleNamespace(globals={"active_events": [{}]}, tables={}))

    renderer._refresh_region_cache.assert_called_once()
    camera.update_matrices.assert_not_called()


@pytest.mark.parametrize("matrices", [(None, np.eye(4)), (np.eye(4), None)])
def test_render_skips_when_camera_matrices_are_unavailable(monkeypatch, matrices):
    renderer, camera = _renderer(matrices=matrices)
    imgui = _FakeImGui()
    monkeypatch.setattr(event_renderer_module, "imgui", imgui)
    renderer._refresh_region_cache = Mock()

    renderer.render(SimpleNamespace(globals={"active_events": [{}]}, tables={}))

    camera.update_matrices.assert_called_once_with(800, 600)
    assert imgui.calls == []


def test_render_projects_visible_events_and_draws_one_overlay(monkeypatch):
    renderer, camera = _renderer()
    imgui = _FakeImGui(begin=True)
    monkeypatch.setattr(event_renderer_module, "imgui", imgui)
    renderer._refresh_region_cache = Mock()
    renderer._project_event = Mock(
        side_effect=[(100.0, 200.0, "Flood warning", "flood", 0.7), None]
    )
    placards = []
    renderer._draw_placard = lambda draw, *args: placards.append((draw, args))
    state = SimpleNamespace(globals={"active_events": [{"id": 1}, {"id": 2}]}, tables={})

    renderer.render(state)

    renderer._refresh_region_cache.assert_called_once_with(state)
    camera.update_matrices.assert_called_once_with(800, 600)
    assert len(placards) == 1
    assert placards[0][1] == (100.0, 200.0, "Flood warning", "flood", 0.7, 600)
    assert [call[0] for call in imgui.calls] == ["position", "size", "begin", "end"]
    assert imgui.calls[2][1][0] == "##EventOverlay"


def test_render_skips_overlay_when_all_events_are_unprojectable(monkeypatch):
    renderer, _ = _renderer()
    imgui = _FakeImGui()
    monkeypatch.setattr(event_renderer_module, "imgui", imgui)
    renderer._refresh_region_cache = Mock()
    renderer._project_event = Mock(return_value=None)

    renderer.render(SimpleNamespace(globals={"active_events": [{"id": 1}]}, tables={}))

    assert imgui.calls == []


def test_render_ends_overlay_when_begin_reports_collapsed_window(monkeypatch):
    renderer, _ = _renderer()
    imgui = _FakeImGui(begin=False)
    monkeypatch.setattr(event_renderer_module, "imgui", imgui)
    renderer._refresh_region_cache = Mock()
    renderer._project_event = Mock(return_value=(100.0, 200.0, "Event", "unknown", 0.5))
    renderer._draw_placard = Mock()

    renderer.render(SimpleNamespace(globals={"active_events": [{}]}, tables={}))

    renderer._draw_placard.assert_not_called()
    assert imgui.calls[-1] == ("end",)


def test_project_event_returns_screen_coordinates_and_uses_defaults():
    renderer, _ = _renderer()
    renderer._region_geo_cache[4] = GeoCoordinate(latitude=0.0, longitude=0.0)

    result = renderer._project_event(
        {"region_id": 4},
        np.eye(4),
        np.eye(4),
        np.array([0.0, 0.0, 3.0], dtype=np.float32),
        800,
        600,
    )

    assert result == (400.0, 300.0, "Event", "", 0.5)


def test_project_event_skips_unknown_regions_back_faces_invalid_clip_and_offscreen_points():
    renderer, _ = _renderer()
    renderer._region_geo_cache[4] = GeoCoordinate(latitude=0.0, longitude=0.0)
    camera = np.array([0.0, 0.0, 3.0], dtype=np.float32)
    assert renderer._project_event({"region_id": 9}, np.eye(4), np.eye(4), camera, 800, 600) is None
    assert renderer._project_event({"region_id": 4}, np.eye(4), np.eye(4), -camera, 800, 600) is None
    zero_w = np.eye(4)
    zero_w[3] = 0.0
    assert renderer._project_event({"region_id": 4}, np.eye(4), zero_w, camera, 800, 600) is None
    offscreen = np.eye(4)
    offscreen[0, 3] = 2.0
    assert renderer._project_event({"region_id": 4}, np.eye(4), offscreen, camera, 800, 600) is None


def test_draw_placard_draws_background_border_severity_bar_label_and_pointer(monkeypatch):
    renderer, _ = _renderer()
    imgui = _FakeImGui()
    monkeypatch.setattr(event_renderer_module, "imgui", imgui)
    draw = imgui.draw_list

    renderer._draw_placard(draw, 100.0, 200.0, "Storm", "flood", 0.5, 600)

    assert [call[0] for call in draw.calls] == ["filled", "rect", "filled", "text", "triangle"]
    background = draw.calls[0][1]
    assert background[0] == (72.0, 361.0)
    assert background[2] == (0.04, 0.04, 0.06, pytest.approx(0.84))
    assert draw.calls[1][1][2] == event_renderer_module._EVENT_COLORS["flood"]
    assert draw.calls[3][1][2] == "Storm"


def test_region_cache_uses_geographic_rows_and_skips_rebuild_for_same_size():
    renderer, _ = _renderer()
    state = SimpleNamespace(
        tables={
            "regions": pl.DataFrame(
                [{"id": 1, "latitude": 50.0, "longitude": 30.0}]
            )
        }
    )

    renderer._refresh_region_cache(state)

    assert renderer._region_geo_cache == {1: GeoCoordinate(latitude=50.0, longitude=30.0)}
    assert renderer._region_cache_size == 1
    renderer._geo.geo_to_unit_vector = Mock(return_value=(0.0, 0.0, 1.0))
    renderer._refresh_region_cache(state)
    renderer._geo.geo_to_unit_vector.assert_not_called()


def test_region_cache_converts_pixel_centers_and_leaves_cache_when_no_coordinates_exist():
    renderer, _ = _renderer()
    renderer._refresh_region_cache(
        SimpleNamespace(
            tables={"regions": pl.DataFrame([{"id": 2, "center_x": 180.0, "center_y": 90.0}])}
        )
    )
    assert renderer._region_geo_cache[2] == GeoCoordinate(latitude=90.0, longitude=180.0)
    previous = dict(renderer._region_geo_cache)
    renderer._refresh_region_cache(
        SimpleNamespace(tables={"regions": pl.DataFrame([{"id": 3, "name": "No coordinates"}])})
    )
    assert renderer._region_geo_cache == previous


def test_region_cache_does_not_clear_existing_data_when_regions_table_is_missing():
    renderer, _ = _renderer()
    cached = GeoCoordinate(latitude=1.0, longitude=2.0)
    renderer._region_geo_cache[9] = cached

    renderer._refresh_region_cache(SimpleNamespace(tables={}))

    assert renderer._region_geo_cache == {9: cached}


def test_region_cache_ignores_a_new_table_without_coordinate_columns():
    renderer, _ = _renderer()
    cache_size = renderer._region_cache_size
    state = SimpleNamespace(
        tables={"regions": pl.DataFrame([{"id": 3, "name": "No coordinates"}])}
    )

    renderer._refresh_region_cache(state)

    assert renderer._region_geo_cache == {}
    assert renderer._region_cache_size == cache_size
