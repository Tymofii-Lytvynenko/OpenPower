from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import polars as pl

from src.client.ui.panels.military.map_information import selected_unit_composition, region_control
from src.client.ui.panels.military.map_information_windows import MapInformationWindows
from src.client.ui.panels.shared.unit_categories import unit_category
from src.client.ui.layouts.gml_layout import get_gml_layout, GMLLayoutSession


def world(unit_type="infantry", equipment_quantity=9, owner="UKR"):
    return SimpleNamespace(tables={
        "units": pl.DataFrame([dict(id="one", owner=owner, unit_type=unit_type, strength=1000,
                                     equipment_quantity=equipment_quantity)]),
        "regions": pl.DataFrame([dict(id=1, name="Kyiv", owner="UKR", controller="POL")]),
    })


def test_own_group_quantity_units_and_missing_equipment_are_explicit():
    infantry = selected_unit_composition(world(), "one", "UKR")
    assert infantry.quantities == {"I": 1000, "G": 0, "N": 0, "A": 0}
    assert infantry.fractions["I"] == 1
    ground = selected_unit_composition(world("air_defense"), "one", "UKR")
    assert ground.quantities["G"] == 9
    assert ground.fractions["G"] == 1
    assert selected_unit_composition(world("air_defense", None), "one", "UKR").quantities["G"] is None


def test_foreign_or_unknown_composition_is_not_invented_from_snapshot_rows():
    for state in (world(owner="POL"), world("unknown_role"), world("strategic_missiles")):
        result = selected_unit_composition(state, "one", "UKR")
        assert set(result.quantities.values()) == {None}
        assert not any(result.fractions.values())
    assert selected_unit_composition(world(), "removed", "UKR") is None


def test_missing_selection_and_uncontrolled_region_have_no_composition_details():
    state = world()
    assert selected_unit_composition(state, None, "UKR") is None

    state.tables["regions"] = pl.DataFrame(
        [dict(id=2, name="Unknown", owner="", controller="")]
    )
    assert region_control(state, 2) is None


def test_region_political_owner_and_military_controller_are_separate():
    result = region_control(world(), 1)
    assert (result.political_tag, result.military_tag) == ("UKR", "POL")
    assert region_control(world(), 0) is None
    state = world()
    state.tables["regions"] = state.tables["regions"].drop("controller")
    assert region_control(state, 1).military_tag == "UKR"


def test_passive_role_metadata_matches_authoritative_catalog_categories():
    from modules.base.systems.military.capability_catalog import DEFAULT_ROLE_PROFILES, ROLE_ALIASES
    from modules.base.systems.military.battle_public_counts import battle_unit_category
    for role in (*DEFAULT_ROLE_PROFILES, *ROLE_ALIASES):
        authoritative = battle_unit_category(role)
        # The map composition has four visible slots; nuclear X is source-hidden.
        assert unit_category(role) == (None if authoritative == "X" else authoritative)


def test_source_window_dimensions_and_instance_only_dynamic_width():
    small = get_gml_layout("Small_Unit_Info_Window")
    sphere = get_gml_layout("Sphere_Control_Window")
    assert (small.width, small.height) == (86, 51)
    assert (sphere.width, sphere.height) == (145, 56)
    session = GMLLayoutSession(sphere, (10, 20), (250, 56))
    path = "Sphere_Control_Window/frmMilitaryCountry/lblCountry"
    original = session.rect_for(path)
    session.resize_component(path, width=130)
    assert session.rect_for(path).width == 130
    assert session.rect_for(path).x == original.x
    assert GMLLayoutSession(sphere, (10, 20), (145, 56)).rect_for(path).width == 25


def test_composition_suppressed_for_multiple_selection_drag_or_invisible_projection():
    windows = MapInformationWindows("UKR")
    with patch("src.client.ui.panels.military.map_information_windows.WindowManager.window") as begin:
        windows.render_selected_unit(world(), set(), lambda _: None, 720)
        windows.render_selected_unit(world(), {"one", "two"}, lambda _: None, 720)
        windows.render_selected_unit(world(), {"one"}, lambda _: None, 720)
        windows.render_selected_unit(world(), {"one"}, lambda _: object(), 720, dragging=True)
    begin.assert_not_called()


def test_game_view_delegates_projected_selection_and_tab_map_hit_without_ui_capture():
    from src.client.views.game_view import GameView
    # The hook only needs these ports, so no native Arcade window is required.
    view = SimpleNamespace(map_information=MagicMock(), unit_renderer=MagicMock(),
                           unit_interactions=SimpleNamespace(selected_unit_ids={"one"}, drag_preview=None),
                           window=SimpleNamespace(height=720), viewport_ctrl=MagicMock())
    view.viewport_ctrl.get_region_at.return_value = 1
    io = SimpleNamespace(want_capture_mouse=False, want_text_input=False)
    native = MagicMock()
    native.get_mouse_pos.return_value = SimpleNamespace(x=100, y=200)
    native.is_key_down.return_value = True
    native.get_io.return_value = io
    with patch("src.client.views.game_view.imgui", native):
        GameView._render_map_information(view, world())
        view.viewport_ctrl.get_region_at.assert_called_once_with(100, 520)
        assert view.map_information.render_region.call_args.kwargs["active"] is True
        io.want_capture_mouse = True
        GameView._render_map_information(view, world())
        assert view.map_information.render_region.call_args.kwargs["active"] is False
