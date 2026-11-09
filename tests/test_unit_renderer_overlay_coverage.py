from types import SimpleNamespace
from unittest.mock import Mock

from src.client.renderers.unit_renderer import UnitDragPreview, UnitRenderer
from src.core.map.geo import GeoCoordinate
from src.client.ui.core.theme import GAMETHEME


class DrawList:
    def __init__(self):
        self.lines = []
        self.filled_rectangles = []
        self.rectangles = []
        self.texts = []

    def add_line(self, start, end, color, thickness):
        self.lines.append((start, end, color, thickness))

    def add_rect_filled(self, start, end, color, *args):
        self.filled_rectangles.append((start, end, color, args))

    def add_rect(self, start, end, color, rounding, *, flags, thickness):
        self.rectangles.append((start, end, color, rounding, flags, thickness))

    def add_text(self, position, color, value):
        self.texts.append((position, color, value))


class Imgui:
    ImDrawFlags_ = SimpleNamespace(closed=1)

    @staticmethod
    def get_color_u32(color):
        return color

    @staticmethod
    def calc_text_size(value):
        return SimpleNamespace(x=float(len(value) * 6), y=12.0)

    @staticmethod
    def ImVec2(x, y):
        return (x, y)


def install_imgui(monkeypatch):
    from src.client.renderers import unit_renderer

    fake = Imgui()
    monkeypatch.setattr(unit_renderer, "imgui", fake)
    return fake


def test_route_segment_draws_solid_dash_and_skips_zero_length(monkeypatch):
    install_imgui(monkeypatch)
    renderer = UnitRenderer.__new__(UnitRenderer)
    draw = DrawList()
    color = (0.2, 0.3, 0.4, 1.0)

    renderer._draw_route_segment(draw, (0.0, 0.0), (10.0, 0.0), color, None)
    renderer._draw_route_segment(draw, (0.0, 0.0), (10.0, 0.0), color, (3.0, 2.0))
    renderer._draw_route_segment(draw, (5.0, 5.0), (5.0, 5.0), color, (3.0, 2.0))

    assert draw.lines[0] == ((0.0, 0.0), (10.0, 0.0), color, 2.5)
    assert [line[:2] for line in draw.lines[1:]] == [
        ((0.0, 0.0), (3.0, 0.0)),
        ((5.0, 0.0), (8.0, 0.0)),
    ]


def test_selected_route_draw_breaks_at_unprojected_points_and_labels_status(monkeypatch):
    install_imgui(monkeypatch)
    from src.client.renderers import unit_renderer

    monkeypatch.setattr(unit_renderer, "sample_route_waypoints", lambda waypoints: waypoints)
    renderer = UnitRenderer.__new__(UnitRenderer)
    renderer._route_projection = SimpleNamespace(project_anchors=Mock(return_value=[
        SimpleNamespace(screen_x=10.0, screen_y=20.0),
        SimpleNamespace(screen_x=30.0, screen_y=25.0),
        None,
        SimpleNamespace(screen_x=80.0, screen_y=40.0),
    ]))
    renderer._draw_route_segment = Mock()
    draw = DrawList()
    overlay = SimpleNamespace(
        waypoints=[GeoCoordinate(0.0, 0.0), GeoCoordinate(1.0, 1.0), GeoCoordinate(2.0, 2.0)],
        color=(0.1, 0.2, 0.3, 1.0),
        dash_lengths=(2.0, 1.0),
        label="Move to target",
        status_label="Blocked",
    )

    renderer._draw_selected_routes(draw, [overlay], 200, 100)

    renderer._route_projection.project_anchors.assert_called_once_with(
        [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)], 200, 100,
    )
    renderer._draw_route_segment.assert_called_once_with(
        draw, (10.0, 80.0), (30.0, 75.0), overlay.color, overlay.dash_lengths,
    )
    assert draw.texts[0][2] == "Move to target · Blocked"
    assert draw.texts[0][0] == (88.0, 43.0)
    assert draw.filled_rectangles[0][0] == (84.0, 41.0)


def test_unit_lookup_prefers_topmost_billboard_and_returns_none_for_misses():
    lower = SimpleNamespace(unit_id="lower", contains=lambda x, y: True)
    upper = SimpleNamespace(unit_id="upper", contains=lambda x, y: True)
    renderer = UnitRenderer.__new__(UnitRenderer)
    renderer._billboards = [lower, upper]

    assert renderer.get_unit_at(4, 5) is upper
    assert renderer.get_unit("lower") is lower
    assert renderer.get_unit("missing") is None

    upper.contains = lambda x, y: False
    assert renderer.get_unit_at(4, 5) is lower
    renderer._billboards = []
    assert renderer.get_unit_at(4, 5) is None


def test_overlay_need_predicate_covers_selection_motion_readiness_and_stack_top():
    renderer = UnitRenderer.__new__(UnitRenderer)
    base = dict(
        unit_id="U1",
        is_moving=False,
        readiness_transition_id="",
        stack_count=1,
        stack_index=0,
    )

    assert renderer._unit_needs_imgui_overlay(SimpleNamespace(**base), "U1", None, None)
    assert renderer._unit_needs_imgui_overlay(SimpleNamespace(**base), None, {"U1"}, None)
    assert renderer._unit_needs_imgui_overlay(SimpleNamespace(**base), None, None, "U1")
    assert renderer._unit_needs_imgui_overlay(SimpleNamespace(**{**base, "is_moving": True}), None, None, None)
    assert renderer._unit_needs_imgui_overlay(SimpleNamespace(**{**base, "readiness_transition_id": "R1"}), None, None, None)
    assert renderer._unit_needs_imgui_overlay(SimpleNamespace(**{**base, "stack_count": 3, "stack_index": 2}), None, None, None)
    assert not renderer._unit_needs_imgui_overlay(SimpleNamespace(**base), None, None, None)


def test_selection_rectangle_normalizes_drag_direction_and_inverts_screen_y(monkeypatch):
    install_imgui(monkeypatch)
    renderer = UnitRenderer.__new__(UnitRenderer)
    draw = DrawList()

    renderer._draw_selection_rect(draw, (100.0, 20.0, 30.0, 70.0), 100)

    assert draw.filled_rectangles[0][:2] == ((30.0, 30.0), (100.0, 80.0))
    assert draw.rectangles[0][:2] == ((30.0, 30.0), (100.0, 80.0))
    assert draw.rectangles[0][4:] == (0, 1.2)


def test_unit_strength_classification_maps_composition_types_and_clamps_negative_strength():
    renderer = UnitRenderer.__new__(UnitRenderer)

    assert renderer._classify_unit_strength(SimpleNamespace(unit_type="naval ship", strength=9)) == (0, 0, 9, 0)
    assert renderer._classify_unit_strength(SimpleNamespace(unit_type="air fighter", strength=6)) == (0, 0, 0, 6)
    assert renderer._classify_unit_strength(SimpleNamespace(unit_type="armored tank", strength=4)) == (0, 4, 0, 0)
    assert renderer._classify_unit_strength(SimpleNamespace(unit_type="infantry", strength=-3)) == (0, 0, 0, 0)


def test_progress_bar_clamps_fill_and_readiness_label_uses_remaining_time(monkeypatch):
    install_imgui(monkeypatch)
    renderer = UnitRenderer.__new__(UnitRenderer)
    draw = DrawList()
    renderer._draw_progress_bar(draw, 2.0, 3.0, 20.0, 1.4)
    renderer._draw_readiness_label(
        draw,
        SimpleNamespace(readiness_target="ready", readiness_remaining_label="2h"),
        5.0,
        8.0,
    )

    assert [rect[:2] for rect in draw.filled_rectangles] == [
        ((2.0, 3.0), (22.0, 7.0)),
        ((2.0, 3.0), (22.0, 7.0)),
    ]
    assert draw.texts == [((5.0, 8.0), GAMETHEME.colors.text_main, "Ready · 2h")]


def test_drag_preview_draws_route_and_fallback_flag_plate(monkeypatch):
    install_imgui(monkeypatch)
    renderer = UnitRenderer.__new__(UnitRenderer)
    renderer._flags = SimpleNamespace(draw_flag=Mock(return_value=False))
    draw = DrawList()
    preview = UnitDragPreview("U1", "USA", 10.0, 20.0, 50.0, 60.0)

    renderer._draw_drag_preview(draw, preview, 100)

    assert draw.lines == [((10.0, 80.0), (50.0, 40.0), (*GAMETHEME.colors.military[:3], 0.75), 2.0)]
    assert renderer._flags.draw_flag.call_count == 1
    assert draw.filled_rectangles[0][:2] == ((35.0, 28.5), (65.0, 51.5))
    assert draw.filled_rectangles[1][:2] == ((39.0, 32.5), (61.0, 47.5))
