from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import arcade
import polars as pl

from src.client.controllers.viewport_controller import SelectionMode, ViewportController


def _state(regions: pl.DataFrame | None = None):
    return SimpleNamespace(
        tables={} if regions is None else {"regions": regions},
        table_revisions={"regions": 1, "countries": 2, "countries_treaties": 3, "countries_wars": 4, "annexation_claims": 5},
    )


def _controller(state=None, projection: str = "globe") -> ViewportController:
    controller = ViewportController.__new__(ViewportController)
    controller.cam = SimpleNamespace(
        yaw=0.0,
        pitch=0.0,
        min_distance=1.0,
        max_distance=10.0,
        distance=5.0,
        look_at_pixel_coords=Mock(),
        drag=Mock(),
        zoom_scroll=Mock(),
    )
    controller.renderer = Mock()
    controller.renderer.projection_mode = projection
    controller.renderer.width = 100
    controller.renderer.height = 200
    controller.renderer._planar_renderer = SimpleNamespace(transform=SimpleNamespace(
        center_u=0.25, center_v=0.75, MIN_ZOOM=1.0, MAX_ZOOM=16.0, zoom=4.0,
    ))
    controller.net = SimpleNamespace(get_state=Mock(return_value=state))
    controller.on_selection_change = Mock()
    controller.selection_mode = SelectionMode.COUNTRY
    controller.selected_country_tag = None
    controller.show_all_units = False
    controller.show_engagement_zones = True
    controller._map_layer_cache_key = None
    controller._political_source = None
    controller.current_mode_key = "political"
    controller.map_modes = {
        "political": SimpleNamespace(calculate_colors=Mock(return_value={1: (1, 0, 0)}), overlay_enabled=True, opacity=0.9),
        "empire": SimpleNamespace(set_selected_country=Mock()),
    }
    return controller


def test_constructor_and_selection_mode_initialize_composed_map_modes() -> None:
    changed = Mock()
    controller = ViewportController(Mock(), object(), Mock(), Mock(), changed)

    assert controller.selection_mode == SelectionMode.COUNTRY
    assert controller.current_mode_key == "political"
    assert {"political", "empire", "gdp_total", "war_exhaustion"}.issubset(controller.map_modes)
    controller.set_selection_mode(SelectionMode.REGION)
    assert controller.selection_mode == SelectionMode.REGION
    controller.renderer.clear_highlight.assert_called_once_with()
    changed.assert_called_once_with(None)


def test_map_mode_switching_and_overlay_refresh_paths() -> None:
    state = _state(pl.DataFrame({"id": [1], "owner": ["USA"], "controller": ["USA"]}))
    controller = _controller(state)

    controller.set_map_mode("terrain")
    assert controller.current_mode_key == "terrain"
    controller.renderer.set_overlay_style.assert_called_once_with(enabled=False, opacity=0.0)
    controller.set_map_mode("unknown")
    assert controller.current_mode_key == "terrain"

    controller.refresh_map_layer = Mock()
    controller.selected_country_tag = "CAN"
    controller.set_map_mode("empire")
    assert controller.current_mode_key == "empire"
    controller.map_modes["empire"].set_selected_country.assert_called_once_with("CAN")
    controller.renderer.set_overlay_style.assert_called_with(enabled=True, opacity=0.9)
    controller.refresh_map_layer.assert_called_once_with()

    del controller.refresh_map_layer
    controller.current_mode_key = "terrain"
    controller.refresh_map_layer()
    assert controller._map_layer_cache_key == ("terrain", None, 1, 2)
    controller.renderer.update_overlay.assert_not_called()
    controller.refresh_political_layer()
    assert controller.current_mode_key == "political"
    controller.renderer.update_overlay.assert_called_once_with({1: (1, 0, 0)})


def test_refresh_map_layer_updates_colors_and_skips_irrelevant_political_changes() -> None:
    regions = pl.DataFrame({"id": [1], "owner": ["USA"], "controller": ["CAN"], "population": [100]})
    state = _state(regions)
    controller = _controller(state)

    controller.refresh_map_layer_if_stale()
    assert controller.net.get_state.call_count == 1
    controller.renderer.update_overlay.assert_called_once_with({1: (1, 0, 0)})
    assert controller._political_source.columns == ["id", "owner", "controller"]

    changed_population = state.tables["regions"].with_columns(pl.lit(200).alias("population"))
    state.tables["regions"] = changed_population
    state.table_revisions["regions"] += 1
    assert controller.refresh_map_layer_if_stale(state) is False
    assert controller.renderer.update_overlay.call_count == 1

    state.table_revisions["regions"] += 1
    controller._political_source = controller._political_color_source(state)
    controller._map_layer_cache_key = ("political", None, state.table_revisions["regions"] - 1)
    assert controller.refresh_map_layer_if_stale(state) is False


def test_map_layer_state_keys_and_political_color_source_follow_the_active_mode() -> None:
    controller = _controller(_state(pl.DataFrame({"id": [1], "owner": ["USA"]})))
    state = controller.net.get_state()

    assert controller._map_layer_state_key(state) == ("political", None, 1)
    controller.current_mode_key = "empire"
    controller.selected_country_tag = "CAN"
    assert controller._map_layer_state_key(state) == ("empire", "CAN", 1, 3, 4, 5)
    controller.current_mode_key = "gdp_total"
    assert controller._map_layer_state_key(state) == ("gdp_total", None, 1, 2)
    assert controller._political_color_source(state) is None
    assert controller._political_color_source(None) is None

    controller.current_mode_key = "political"
    assert controller._political_color_source(state).columns == ["id", "owner"]
    assert controller._political_color_source(_state()) is None


def test_region_focus_uses_planar_or_globe_projection_and_selects_the_region() -> None:
    regions = pl.DataFrame({
        "id": [7], "owner": ["CAN"], "controller": ["CAN"], "center_x": [25.0], "center_y": [50.0],
    })
    state = _state(regions)
    planar = _controller(state, projection="planar")

    planar.focus_on_region(7)

    planar.renderer.focus_planar_pixel.assert_called_once_with(25.0, 50.0)
    planar.renderer.set_highlight.assert_called_once_with([7])
    planar.on_selection_change.assert_called_once_with(7)

    globe = _controller(state)
    globe.focus_on_region(7)
    globe.cam.look_at_pixel_coords.assert_called_once_with(25.0, 50.0, 100, 200)

    no_regions = _controller(_state())
    no_regions.focus_on_region(7)
    no_regions.renderer.set_highlight.assert_not_called()


def test_country_focus_validates_rows_selects_largest_region_and_uses_centroid(monkeypatch) -> None:
    regions = pl.DataFrame({
        "id": [1, 2, 3],
        "owner": ["USA", "USA", "CAN"],
        "controller": ["CAN", "CAN", "CAN"],
        "area_km2": [10.0, 50.0, 5.0],
        "center_x": [10.0, 30.0, 90.0],
        "center_y": [20.0, 40.0, 90.0],
    })
    state = _state(regions)
    controller = _controller(state, projection="planar")
    monkeypatch.setattr("src.client.controllers.viewport_controller.calculate_centroid", lambda *_args: (25.0, 35.0))

    assert controller.focus_on_country(" CAN ") == 2
    controller.renderer.focus_planar_pixel.assert_called_once_with(25.0, 165.0)
    controller.renderer.set_highlight.assert_called_once_with([1, 2, 3])
    controller.on_selection_change.assert_called_once_with(2)
    assert controller.selected_country_tag == "CAN"

    globe = _controller(state)
    assert globe.focus_on_country("CAN") == 2
    globe.cam.look_at_pixel_coords.assert_called_once_with(25.0, 165.0, 100, 200)


def test_country_focus_returns_none_for_missing_or_invalid_region_data(monkeypatch) -> None:
    controller = _controller(_state())
    assert controller.focus_on_country(None) is None
    assert controller.focus_on_country(" ") is None
    assert controller.focus_on_country("USA") is None
    assert controller.focus_on_country("USA") is None

    controller = _controller(_state(pl.DataFrame({"owner": ["USA"]})))
    assert controller.focus_on_country("USA") is None
    controller = _controller(_state(pl.DataFrame({"id": [0, None], "owner": ["USA", "USA"]})))
    assert controller.focus_on_country("USA") is None

    controller = _controller(_state(pl.DataFrame({"id": [1], "owner": ["USA"]})))
    assert controller.focus_on_country("CAN") is None
    controller.select_country_viewpoint("CAN")
    controller.focus_on_country = Mock(return_value=9)
    controller.select_country_viewpoint("USA")
    controller.focus_on_country.assert_called_once_with("USA")

    region_rows = pl.DataFrame({"id": [4], "owner": ["USA"], "area_km2": [10.0]})
    assert controller._representative_region_id(region_rows, 4) == 4
    assert controller._representative_region_id(region_rows.head(0), 8) == 8
    monkeypatch.setattr("src.client.controllers.viewport_controller.calculate_centroid", lambda *_args: None)
    no_centroid = _controller(_state(pl.DataFrame({"id": [4], "owner": ["USA"], "center_x": [1.0], "center_y": [2.0]})))
    assert no_centroid.focus_on_country("USA") == 4


def test_region_selection_uses_authoritative_controller_and_clears_invalid_selection() -> None:
    regions = pl.DataFrame({
        "id": [1, 2, 3], "owner": ["USA", "USA", "CAN"], "controller": ["CAN", "CAN", "CAN"],
    })
    controller = _controller(_state(regions))

    controller.select_region_by_id(1)
    assert controller.selected_country_tag == "CAN"
    controller.renderer.set_highlight.assert_called_once_with([1, 2, 3])
    controller.on_selection_change.assert_called_once_with(1)

    controller.select_region_by_id(None)
    assert controller.selected_country_tag is None
    controller.renderer.clear_highlight.assert_called_once_with()
    controller.on_selection_change.assert_called_with(None)

    controller = _controller(_state(pl.DataFrame({"id": [1], "owner": ["None"]})))
    controller.select_region_by_id(1)
    assert controller.selected_country_tag is None
    controller.renderer.set_highlight.assert_called_once_with([1])

    region_mode = _controller(_state())
    region_mode.selection_mode = SelectionMode.REGION
    region_mode.select_region_by_id(3)
    region_mode.net.get_state.assert_not_called()
    region_mode.renderer.set_highlight.assert_called_once_with([3])


def test_empire_selection_refreshes_overlay_and_clicks_delegate_to_region_selection() -> None:
    controller = _controller(_state(pl.DataFrame({"id": [1], "owner": ["USA"]})))
    controller.current_mode_key = "empire"
    controller.refresh_map_layer = Mock()

    controller.select_region_by_id(4)
    controller.renderer.clear_highlight.assert_called_once_with()
    controller.refresh_map_layer.assert_called_once_with()
    controller.on_selection_change.assert_called_once_with(4)

    controller.select_region_by_id(0)
    controller.on_selection_change.assert_called_with(None)
    controller.renderer.get_region_id_at_screen_pos.return_value = 6
    controller.select_region_by_id = Mock()
    controller._handle_click_selection(10.0, 20.0)
    controller.select_region_by_id.assert_called_once_with(6)


def test_map_input_routes_to_planar_and_globe_controls() -> None:
    controller = _controller(projection="planar")
    controller._handle_click_selection = Mock()

    controller.on_mouse_press(10, 20, arcade.MOUSE_BUTTON_LEFT)
    controller._handle_click_selection.assert_called_once_with(10, 20)
    controller.on_mouse_press(10, 20, arcade.MOUSE_BUTTON_RIGHT)
    controller.on_mouse_release(10, 20, arcade.MOUSE_BUTTON_LEFT)
    controller.on_mouse_drag(0, 0, 3, 4, arcade.MOUSE_BUTTON_RIGHT)
    controller.renderer.pan_planar.assert_called_once_with(3, 4)
    controller.on_mouse_scroll(10, 20, 0, 1)
    controller.renderer.zoom_planar_at.assert_called_once_with(10, 20, 1)

    controller.renderer.projection_mode = "globe"
    controller.on_mouse_drag(0, 0, 5, 6, arcade.MOUSE_BUTTON_RIGHT)
    controller.cam.drag.assert_called_once_with(5, 6)
    controller.on_mouse_scroll(0, 0, 0, -1)
    controller.cam.zoom_scroll.assert_called_once_with(-1)


def test_region_lookup_handles_invalid_values_and_renderer_errors() -> None:
    controller = _controller()
    controller.renderer.get_region_id_at_screen_pos.return_value = 5
    assert controller.get_region_at(1, 2) == 5
    controller.renderer.get_region_id_at_screen_pos.return_value = 0
    assert controller.get_region_at(1, 2) is None
    controller.renderer.get_region_id_at_screen_pos.side_effect = RuntimeError("map not ready")
    assert controller.get_region_at(1, 2) is None


def test_normalized_camera_helpers_cover_planar_globe_and_degenerate_ranges() -> None:
    planar = _controller(projection="planar")
    assert planar.map_center_fraction() == (0.25, 0.25)
    assert planar.zoom_fraction() == 0.5
    planar.set_zoom_fraction(1.0)
    assert planar.renderer._planar_renderer.transform.zoom == 16.0
    planar.renderer._planar_renderer.transform.MIN_ZOOM = 4.0
    planar.renderer._planar_renderer.transform.MAX_ZOOM = 2.0
    assert planar.zoom_fraction() == 0.0

    globe = _controller()
    assert globe.map_center_fraction() == (0.75, 0.5)
    assert globe.zoom_fraction() == 5.0 / 9.0
    globe.set_zoom_fraction(0.25)
    assert globe.cam.distance == 7.75
    globe.cam.min_distance = 5.0
    globe.cam.max_distance = 5.0
    assert globe.zoom_fraction() == 0.0


def test_focus_fraction_clamps_coordinates_for_both_projections() -> None:
    planar = _controller(projection="planar")
    planar.focus_on_map_fraction(1.5, -0.5)
    planar.renderer.focus_planar_pixel.assert_called_once_with(100.0, 0.0)
    globe = _controller()
    globe.focus_on_map_fraction(-1.0, 2.0)
    globe.cam.look_at_pixel_coords.assert_called_once_with(0.0, 200.0, 100, 200)
