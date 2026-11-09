from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl
import pytest

from src.client.renderers import unit_renderer as unit_renderer_module
from src.client.renderers.unit_renderer import UnitRenderer


def bare_renderer() -> UnitRenderer:
    renderer = UnitRenderer.__new__(UnitRenderer)
    renderer._camera = SimpleNamespace(yaw=0.1234567, pitch=-0.2345678, distance=4.56789)
    renderer._region_count = 2
    renderer._region_lookup = {}
    renderer._billboards = []
    renderer._projection_cache_key = None
    renderer._prepared_units = object()
    renderer._prepared_units_key = None
    renderer._last_state_id = None
    renderer._last_units_signature = None
    renderer._last_units_revision = None
    renderer._last_owners_hash = None
    renderer._flag_units_signature = None
    renderer._flag_owners = frozenset()
    renderer._filtered_units_cache_key = None
    renderer._filtered_units_cache = None
    renderer._route_overlay_cache_key = None
    renderer._route_overlay_cache = []
    return renderer


class RecordingDrawList:
    def __init__(self) -> None:
        self.filled_rectangles = []
        self.rectangles = []

    def add_rect_filled(self, start, end, color, *args) -> None:
        self.filled_rectangles.append((start, end, color, args))

    def add_rect(self, start, end, color, rounding, *, flags, thickness) -> None:
        self.rectangles.append((start, end, color, rounding, flags, thickness))


class DrawImgui:
    @staticmethod
    def get_color_u32(color):
        return color


def test_constructor_composes_projection_and_rendering_services(monkeypatch) -> None:
    camera = object()
    projection = object()
    route_projection = object()
    geo_projection = object()
    flags = object()
    batch = object()
    prepared = object()
    calls = []

    monkeypatch.setattr(
        unit_renderer_module,
        "UnitProjectionService",
        lambda *args: calls.append(("projection", args)) or projection,
    )
    monkeypatch.setattr(
        unit_renderer_module,
        "GlobeOverlayProjection",
        lambda *args: calls.append(("route-projection", args)) or route_projection,
    )
    monkeypatch.setattr(
        unit_renderer_module,
        "EquirectangularProjection",
        lambda *args: calls.append(("geo-projection", args)) or geo_projection,
    )
    monkeypatch.setattr(unit_renderer_module, "UnitFlagAtlas", lambda: flags)
    monkeypatch.setattr(unit_renderer_module, "UnitBatchRenderer", lambda: batch)
    monkeypatch.setattr(unit_renderer_module.PreparedUnitProjectionData, "empty", lambda: prepared)

    renderer = UnitRenderer(camera, 800, 400, 1.25)

    assert calls == [
        ("projection", (camera, 800, 400, 1.25)),
        ("route-projection", (camera, 800, 400, 1.25)),
        ("geo-projection", (800, 400)),
    ]
    assert renderer._camera is camera
    assert renderer._projection is projection
    assert renderer._route_projection is route_projection
    assert renderer._geo_projection is geo_projection
    assert renderer._flags is flags
    assert renderer._batch is batch
    assert renderer._prepared_units is prepared
    assert renderer._region_lookup == {}
    assert renderer._region_count == -1
    assert renderer._route_overlay_cache == []


class FakeImgui:
    WindowFlags_ = SimpleNamespace(
        no_decoration=1,
        no_background=2,
        no_inputs=4,
        no_saved_settings=8,
        no_focus_on_appearing=16,
        no_nav=32,
    )

    def __init__(self, *, begin_visible=True) -> None:
        self.begin_visible = begin_visible
        self.draw_list = object()
        self.begin_calls = []
        self.positions = []
        self.sizes = []
        self.end_calls = 0

    def get_io(self):
        return SimpleNamespace(display_size=SimpleNamespace(x=800.9, y=600.1))

    def set_next_window_pos(self, position) -> None:
        self.positions.append(position)

    def set_next_window_size(self, size) -> None:
        self.sizes.append(size)

    def begin(self, title, _opened, flags):
        self.begin_calls.append((title, flags))
        return self.begin_visible, None

    def get_window_draw_list(self):
        return self.draw_list

    def end(self) -> None:
        self.end_calls += 1


def configure_render(renderer: UnitRenderer, units, *, batch_drawn: bool) -> None:
    renderer._flags = object()
    renderer._batch = SimpleNamespace(render=MagicMock(return_value=batch_drawn))
    renderer._billboards = []
    renderer._get_filtered_units = MagicMock(return_value="filtered")
    renderer._get_units_signature = MagicMock(return_value=("signature",))
    renderer._prepare_flag_atlas_for_state = MagicMock()
    renderer._project_units = MagicMock(return_value=units)
    renderer._get_selected_route_overlays = MagicMock(return_value=[])
    renderer._draw_selected_routes = MagicMock()
    renderer._draw_engagement_zones = MagicMock()
    renderer._draw_unit = MagicMock()
    renderer._draw_unit_overlay = MagicMock()
    renderer._draw_drag_preview = MagicMock()
    renderer._draw_selection_rect = MagicMock()


@pytest.mark.parametrize("batch_drawn", [True, False])
def test_render_routes_batch_and_overlay_draw_paths(monkeypatch, batch_drawn) -> None:
    renderer = bare_renderer()
    unit = SimpleNamespace(unit_id="U2")
    configure_render(renderer, [unit], batch_drawn=batch_drawn)
    ui = FakeImgui()
    monkeypatch.setattr(unit_renderer_module, "imgui", ui)
    renderer._unit_needs_imgui_overlay = MagicMock(return_value=False)
    preview = object()
    selection_rect = (1.0, 2.0, 3.0, 4.0)
    state = object()

    renderer.render(
        state,
        selected_unit_id="U2",
        selected_unit_ids={"U3", "U2"},
        hovered_unit_id=None,
        drag_preview=preview,
        selection_rect=selection_rect,
        visible_owners={"USA"},
        presentation_total_minutes=24.5,
        viewer_country_tag="usa",
    )

    renderer._get_filtered_units.assert_called_once_with(state, {"USA"})
    renderer._get_units_signature.assert_called_once_with(state, "filtered", {"USA"})
    renderer._prepare_flag_atlas_for_state.assert_called_once_with("filtered", preview, ("signature",))
    renderer._project_units.assert_called_once_with(state, "filtered", 800, 600, ("signature",), 24.5)
    renderer._get_selected_route_overlays.assert_called_once_with(state, ["U2", "U3"], "usa")
    renderer._batch.render.assert_called_once_with([unit], renderer._flags, 800, 600)
    assert ui.positions == [(0, 0)]
    assert ui.sizes == [(800.0, 600.0)]
    assert ui.begin_calls == [("##UnitOverlay", 63)]
    renderer._draw_selected_routes.assert_called_once_with(ui.draw_list, [], 800, 600)
    renderer._draw_engagement_zones.assert_called_once_with(ui.draw_list, 800, 600, "U2", {"U3", "U2"}, None)
    if batch_drawn:
        renderer._draw_unit_overlay.assert_called_once_with(ui.draw_list, unit, 800, 600, "U2", {"U3", "U2"}, None)
        renderer._draw_unit.assert_not_called()
    else:
        renderer._draw_unit.assert_called_once_with(ui.draw_list, unit, 800, 600, "U2", {"U3", "U2"}, None)
        renderer._draw_unit_overlay.assert_not_called()
    renderer._draw_drag_preview.assert_called_once_with(ui.draw_list, preview, 600)
    renderer._draw_selection_rect.assert_called_once_with(ui.draw_list, selection_rect, 600)
    assert ui.end_calls == 1


def test_render_returns_without_opening_imgui_when_batch_covers_everything(monkeypatch) -> None:
    renderer = bare_renderer()
    configure_render(renderer, [], batch_drawn=True)
    ui = FakeImgui()
    monkeypatch.setattr(unit_renderer_module, "imgui", ui)

    renderer.render(None, None, None, None, None, show_engagement_zones=False)

    assert ui.begin_calls == []
    assert ui.end_calls == 0
    renderer._draw_selected_routes.assert_not_called()
    renderer._draw_engagement_zones.assert_not_called()


def test_render_ends_hidden_overlay_without_drawing_contents(monkeypatch) -> None:
    renderer = bare_renderer()
    configure_render(renderer, [SimpleNamespace(unit_id="U1")], batch_drawn=False)
    ui = FakeImgui(begin_visible=False)
    monkeypatch.setattr(unit_renderer_module, "imgui", ui)

    renderer.render(None, None, None, None, None, show_engagement_zones=False)

    assert ui.begin_calls
    assert ui.end_calls == 1
    renderer._draw_selected_routes.assert_not_called()
    renderer._draw_unit.assert_not_called()


def test_projection_clears_stale_cache_when_state_or_units_are_missing() -> None:
    renderer = bare_renderer()
    renderer._projection_cache_key = ("old",)
    renderer._prepared_units_key = ("old",)
    renderer._prepared_units = object()

    assert renderer._project_units(None, object(), 800, 600, ("sig",)) == []
    assert renderer._projection_cache_key is None
    assert renderer._prepared_units_key is None

    class EmptyFrame:
        @staticmethod
        def is_empty():
            return True

    assert renderer._project_units(object(), EmptyFrame(), 800, 600, ("sig",)) == []
    assert renderer._prepared_units_key is None


def test_projection_reuses_cached_billboards_when_camera_and_revision_key_matches() -> None:
    renderer = bare_renderer()
    renderer._camera = SimpleNamespace(yaw=0.1, pitch=0.2, distance=4.0)
    renderer._billboards = [object()]
    renderer._projection_cache_key = renderer._make_projection_cache_key(("sig",), 800, 600, 5.0)
    renderer._refresh_region_lookup = MagicMock()
    renderer._projection = SimpleNamespace(project_prepared_units=MagicMock())

    result = renderer._project_units(
        SimpleNamespace(tables={}, time=SimpleNamespace(total_minutes=5.0)),
        SimpleNamespace(is_empty=lambda: False),
        800,
        600,
        ("sig",),
        5.0,
    )

    assert result is renderer._billboards
    renderer._refresh_region_lookup.assert_called_once()
    renderer._projection.project_prepared_units.assert_not_called()


def test_projection_prepares_readiness_transitions_and_projects_changed_view() -> None:
    renderer = bare_renderer()
    renderer._camera = SimpleNamespace(yaw=0.1, pitch=0.2, distance=4.0)
    renderer._projection = SimpleNamespace(
        project_prepared_units=MagicMock(return_value=["projected"]),
    )
    renderer._refresh_region_lookup = MagicMock()
    renderer._get_prepared_units = MagicMock(return_value="prepared")
    units = SimpleNamespace(is_empty=lambda: False)
    transitions = pl.DataFrame([
        {
            "unit_id": "U1",
            "id": "R1",
            "target_status": "ready",
            "completes_at_minute": 30,
            "progress": 0.5,
        }
    ])
    state = SimpleNamespace(
        tables={"unit_readiness_transitions": transitions},
        time=SimpleNamespace(total_minutes=20.0),
    )

    result = renderer._project_units(state, units, 800, 600, ("sig",), None)

    assert result == ["projected"]
    renderer._get_prepared_units.assert_called_once_with(units, ("sig",), transitions.to_dicts(), 20.0)
    renderer._projection.project_prepared_units.assert_called_once_with("prepared", 800, 600, None)
    assert renderer._projection_cache_key == renderer._make_projection_cache_key(("sig",), 800, 600, None)


def test_route_overlay_cache_normalizes_viewer_and_invalidates_on_table_revision(monkeypatch) -> None:
    renderer = bare_renderer()
    make_overlays = MagicMock(side_effect=[["first"], ["second"]])
    monkeypatch.setattr(unit_renderer_module, "selected_unit_route_overlays", make_overlays)
    state = SimpleNamespace(table_revisions={"units": 1})

    first = renderer._get_selected_route_overlays(state, ["U1"], " usa ")
    cached = renderer._get_selected_route_overlays(state, ["U1"], "USA")
    state.table_revisions["units"] = 2
    updated = renderer._get_selected_route_overlays(state, ["U1"], "USA")

    assert first == ["first"]
    assert cached is first
    assert updated == ["second"]
    assert make_overlays.call_count == 2
    assert make_overlays.call_args_list[0].args == (state, ["U1"], " usa ")


def test_region_lookup_uses_center_pixels_when_geographic_columns_are_absent() -> None:
    renderer = bare_renderer()
    renderer._geo_projection = SimpleNamespace(
        pixel_to_geo=MagicMock(side_effect=lambda pixel: (pixel.x, pixel.y)),
    )
    state = SimpleNamespace(tables={
        "regions": pl.DataFrame({
            "id": [7],
            "center_x": [12.5],
            "center_y": [30.25],
        })
    })

    renderer._refresh_region_lookup(state)

    assert renderer._region_lookup[7].geo == (12.5, 30.25)
    assert renderer._region_count == 1


def test_engagement_zone_draws_partial_visible_ring_as_line_segments(monkeypatch) -> None:
    class ZoneImgui:
        ImDrawFlags_ = SimpleNamespace(closed=1)

        @staticmethod
        def ImVec2(x, y):
            return (x, y)

        @staticmethod
        def get_color_u32(color):
            return color

    monkeypatch.setattr(unit_renderer_module, "imgui", ZoneImgui)
    renderer = bare_renderer()
    renderer._billboards = [SimpleNamespace(unit_id="U1", local_position=(0.0, 0.0))]
    renderer._projection = SimpleNamespace(
        project_surface_ring=MagicMock(return_value=[(1, 2), None, (3, 4), (5, 6)]),
    )
    draw = SimpleNamespace(add_line=MagicMock(), add_convex_poly_filled=MagicMock(), add_polyline=MagicMock())

    renderer._draw_engagement_zones(draw, 800, 600, "U1", None, None)

    assert draw.add_convex_poly_filled.call_count == 0
    assert draw.add_polyline.call_count == 0
    assert draw.add_line.call_args_list[0].args[:2] == ((3, 4), (5, 6))
    assert draw.add_line.call_args_list[1].args[:2] == ((5, 6), (1, 2))


def test_billboards_property_exposes_current_projected_units() -> None:
    renderer = bare_renderer()
    renderer._billboards = ["projected-unit"]

    assert renderer.billboards == ["projected-unit"]


def test_flag_atlas_clears_cached_owners_for_empty_units() -> None:
    renderer = bare_renderer()
    ensure_owners = MagicMock()
    renderer._flags = SimpleNamespace(ensure_owners=ensure_owners)
    renderer._flag_owners = frozenset({"USA"})
    renderer._flag_units_signature = ("old",)

    renderer._prepare_flag_atlas_for_state(
        pl.DataFrame(schema={"owner": pl.String}),
        None,
        ("empty",),
    )

    assert renderer._flag_owners == frozenset()
    assert renderer._flag_units_signature == ("empty",)
    ensure_owners.assert_called_once_with({"USA"})


def test_region_lookup_clears_when_regions_have_no_coordinate_columns() -> None:
    renderer = bare_renderer()
    renderer._region_lookup = {1: object()}
    renderer._region_count = 0
    state = SimpleNamespace(tables={"regions": pl.DataFrame({"id": [1]})})

    renderer._refresh_region_lookup(state)

    assert renderer._region_lookup == {}
    assert renderer._region_count == -1


def test_draw_unit_renders_flag_fallback_progress_stack_and_selected_composition(monkeypatch) -> None:
    monkeypatch.setattr(unit_renderer_module, "imgui", DrawImgui)
    renderer = bare_renderer()
    renderer._flags = SimpleNamespace(draw_flag=MagicMock(return_value=False))
    renderer._draw_progress_bar = MagicMock()
    renderer._draw_readiness_label = MagicMock()
    renderer._draw_stack_badge = MagicMock()
    plate = MagicMock()
    monkeypatch.setattr(unit_renderer_module.UIPrimitives, "unit_composition_plate", plate)
    draw = RecordingDrawList()
    unit = SimpleNamespace(
        unit_id="U1",
        owner="USA",
        screen_x=100.0,
        screen_y=50.0,
        width=20.0,
        height=10.0,
        is_moving=True,
        movement_progress=0.6,
        readiness_transition_id="",
        stack_count=3,
        stack_index=2,
        stack_strength=7,
        unit_type="infantry",
        strength=10,
    )

    renderer._draw_unit(draw, unit, 300, 200, "U1", None, None)

    renderer._flags.draw_flag.assert_called_once_with(draw, "USA", 90.0, 145.0, 110.0, 155.0)
    assert draw.filled_rectangles[0][:2] == ((87.0, 142.0), (113.0, 158.0))
    assert draw.filled_rectangles[1][:2] == ((90.0, 145.0), (110.0, 155.0))
    assert draw.rectangles[0][2] == unit_renderer_module.GAMETHEME.colors.warning
    assert draw.rectangles[0][5] == 1.5
    renderer._draw_progress_bar.assert_called_once_with(draw, 90.0, 159.0, 20.0, 0.6)
    renderer._draw_stack_badge.assert_called_once_with(draw, 107.0, 138.0, 3, 7)
    plate.assert_called_once()
    assert plate.call_args.kwargs["x"] == 117.0
    assert plate.call_args.kwargs["y"] == 127.0
    assert plate.call_args.kwargs["max_value"] == 10

    readiness_unit = SimpleNamespace(
        unit_id="U3",
        owner="MEX",
        screen_x=80.0,
        screen_y=40.0,
        width=18.0,
        height=9.0,
        is_moving=False,
        readiness_transition_id="R3",
        readiness_progress=0.35,
        readiness_target="ready",
        readiness_remaining_label="1h",
        stack_count=1,
        stack_index=0,
        stack_strength=3,
        unit_type="infantry",
        strength=3,
    )
    renderer._draw_unit(draw, readiness_unit, 300, 200, None, None, "U3")
    renderer._draw_progress_bar.assert_called_with(draw, 71.0, 168.5, 18.0, 0.35)
    renderer._draw_readiness_label.assert_called_once_with(draw, readiness_unit, 71.0, 174.5)


def test_draw_unit_uses_hover_border_and_skips_selected_only_details(monkeypatch) -> None:
    monkeypatch.setattr(unit_renderer_module, "imgui", DrawImgui)
    renderer = bare_renderer()
    renderer._flags = SimpleNamespace(draw_flag=MagicMock(return_value=True))
    renderer._draw_progress_bar = MagicMock()
    renderer._draw_stack_badge = MagicMock()
    renderer._draw_unit_composition_plate = MagicMock()
    draw = RecordingDrawList()
    unit = SimpleNamespace(
        unit_id="U2",
        owner="CAN",
        screen_x=30.0,
        screen_y=20.0,
        width=12.0,
        height=8.0,
        is_moving=False,
        readiness_transition_id="",
        stack_count=1,
        stack_index=0,
        stack_strength=1,
        strength=1,
        unit_type="infantry",
    )

    renderer._draw_unit(draw, unit, 100, 100, None, None, "U2")

    assert len(draw.filled_rectangles) == 1
    assert draw.rectangles[0][2] == unit_renderer_module.GAMETHEME.colors.info
    assert draw.rectangles[0][5] == 1.5
    renderer._draw_progress_bar.assert_not_called()
    renderer._draw_stack_badge.assert_not_called()
    renderer._draw_unit_composition_plate.assert_not_called()


def test_draw_unit_overlay_handles_hover_readiness_and_selected_stack(monkeypatch) -> None:
    monkeypatch.setattr(unit_renderer_module, "imgui", DrawImgui)
    renderer = bare_renderer()
    renderer._draw_progress_bar = MagicMock()
    renderer._draw_readiness_label = MagicMock()
    renderer._draw_stack_badge = MagicMock()
    renderer._draw_unit_composition_plate = MagicMock()
    draw = RecordingDrawList()
    unit = SimpleNamespace(
        unit_id="U1",
        screen_x=50.0,
        screen_y=30.0,
        width=20.0,
        height=10.0,
        is_moving=False,
        readiness_transition_id="R1",
        readiness_progress=0.4,
        stack_count=2,
        stack_index=1,
        stack_strength=6,
        strength=8,
        unit_type="tank",
    )

    renderer._draw_unit_overlay(
        draw,
        SimpleNamespace(unit_id="U2", is_moving=False, readiness_transition_id="", stack_count=1),
        200,
        100,
        None,
        None,
        None,
    )
    assert draw.rectangles == []

    renderer._draw_unit_overlay(draw, unit, 200, 100, None, None, "U1")
    assert draw.rectangles[0][2] == unit_renderer_module.GAMETHEME.colors.info
    renderer._draw_progress_bar.assert_called_once_with(draw, 40.0, 79.0, 20.0, 0.4)
    renderer._draw_readiness_label.assert_called_once_with(draw, unit, 40.0, 85.0)
    renderer._draw_stack_badge.assert_called_once_with(draw, 57.0, 58.0, 2, 6)

    renderer._draw_unit_overlay(draw, unit, 200, 100, "U1", None, None)
    assert draw.rectangles[1][2] == unit_renderer_module.GAMETHEME.colors.warning
    renderer._draw_unit_composition_plate.assert_called_once_with(draw, unit, 60.0, 65.0, 200, 100)

    moving_unit = SimpleNamespace(
        unit_id="U3",
        screen_x=50.0,
        screen_y=30.0,
        width=20.0,
        height=10.0,
        is_moving=True,
        movement_progress=0.8,
        readiness_transition_id="",
        stack_count=1,
    )
    renderer._draw_unit_overlay(draw, moving_unit, 200, 100, None, None, None)
    assert renderer._draw_progress_bar.call_args.args == (draw, 40.0, 79.0, 20.0, 0.8)


def test_composition_plate_moves_left_and_clamps_to_window_edges(monkeypatch) -> None:
    renderer = bare_renderer()
    unit = SimpleNamespace(
        screen_x=180.0,
        width=20.0,
        unit_type="naval ship",
        strength=9,
    )
    plate = MagicMock()
    monkeypatch.setattr(unit_renderer_module.UIPrimitives, "unit_composition_plate", plate)

    renderer._draw_unit_composition_plate(object(), unit, 190.0, 0.0, 200, 100)

    assert plate.call_args.kwargs["x"] == 45.0
    assert plate.call_args.kwargs["y"] == 4.0
    assert plate.call_args.kwargs["max_value"] == 9
    assert [row.value for row in plate.call_args.kwargs["rows"]] == [0, 0, 9, 0]
