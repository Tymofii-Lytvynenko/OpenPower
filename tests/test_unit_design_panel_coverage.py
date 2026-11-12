from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.military import unit_design_panel as panel_module
from src.client.ui.panels.military.design_selection import UnitDesignSelection
from src.client.ui.panels.military.unit_design_panel import UnitDesignPanel
from tests.test_support.client_presentation import client_state


def make_context(*, own=False, client=None):
    return PanelRenderContext(target_tag="UKR", is_own_country=own, net_client=client)


def make_ui(*, button=False):
    return SimpleNamespace(
        frame=Mock(),
        path=lambda value: f"path:{value}",
        text=Mock(),
        button=Mock(return_value=button),
        button_at=Mock(return_value=False),
        rect=Mock(),
        hitbox=Mock(return_value=False),
    )


def make_imgui(*, role_result=(False, 0), design_result=(False, 0), button=False):
    return SimpleNamespace(
        text_disabled=Mock(),
        text_wrapped=Mock(),
        combo=Mock(side_effect=[role_result, design_result]),
        begin_disabled=Mock(),
        end_disabled=Mock(),
        button=Mock(return_value=button),
        Col_=SimpleNamespace(button="button"),
        push_style_color=Mock(),
        pop_style_color=Mock(),
        get_io=Mock(return_value=SimpleNamespace(
            mouse_pos=SimpleNamespace(x=0.0, y=0.0),
            mouse_wheel=0.0,
        )),
        is_item_active=Mock(return_value=False),
        get_window_draw_list=Mock(return_value=SimpleNamespace(add_rect_filled=Mock())),
        get_color_u32=Mock(side_effect=lambda color: f"color:{color}"),
        get_scroll_x=Mock(return_value=0.0),
        get_scroll_y=Mock(return_value=0.0),
        set_cursor_screen_pos=Mock(),
        push_text_wrap_pos=Mock(),
        pop_text_wrap_pos=Mock(),
        get_cursor_pos_x=Mock(return_value=50.0),
        get_cursor_screen_pos=Mock(return_value=SimpleNamespace(y=100.0)),
        WindowFlags_=SimpleNamespace(no_scrollbar=1, no_scroll_with_mouse=2),
    )


def make_panel_for_content(
    monkeypatch,
    *,
    designs=(),
    all_designs=None,
    selection_id=None,
    role_result=(False, 0),
    design_result=(False, 0),
    clicked=False,
    layout=None,
):
    panel = UnitDesignPanel(UnitDesignSelection(selection_id))
    panel._presenter = SimpleNamespace(designs_for_country=Mock(return_value=list(designs)))
    panel._editor.open = Mock()
    panel._render_tab_buttons = Mock()
    panel._render_statistics = Mock()
    panel._render_overview = Mock()
    ui = make_ui(button=clicked)
    imgui = make_imgui(role_result=role_result, design_result=design_result, button=clicked)
    options = (
        SimpleNamespace(role="infantry", label="Infantry"),
        SimpleNamespace(role="tanks", label="Tank"),
    )
    monkeypatch.setattr(panel_module, "imgui", imgui)
    monkeypatch.setattr(panel_module, "draw_required_tables", lambda *_args: True)
    monkeypatch.setattr(panel_module, "unit_type_options_for_roles", lambda _roles, _state: options)
    monkeypatch.setattr(panel_module, "capabilities_for_design", lambda _design, _state: {"attack": 1.0})
    monkeypatch.setattr(panel_module, "active_gml_layout", lambda: layout)
    tables = {}
    if all_designs is not None:
        tables["unit_designs"] = SimpleNamespace(to_dicts=lambda: list(all_designs))
    state = client_state(tables=tables)
    return panel, state, make_context(own=True, client=object()), ui, imgui


def test_render_returns_false_when_window_is_closed(monkeypatch):
    panel = UnitDesignPanel()

    @contextmanager
    def window(*_args, **_kwargs):
        yield False

    monkeypatch.setattr(panel_module.WindowManager, "window", window)
    content = Mock()
    monkeypatch.setattr(panel, "_render_content", content)

    assert not panel.render(SimpleNamespace(), make_context())
    content.assert_not_called()


@pytest.mark.parametrize("editor_available", [True, False])
def test_render_draws_source_frame_and_opens_editor_only_when_available(
    monkeypatch, editor_available
):
    panel = UnitDesignPanel()
    ui = make_ui()

    @contextmanager
    def window(*_args, **_kwargs):
        yield True

    monkeypatch.setattr(panel_module.WindowManager, "window", window)
    monkeypatch.setattr(panel_module, "GMLWidgets", lambda _root: ui)
    monkeypatch.setattr(panel, "_draw_source_frames", Mock())
    monkeypatch.setattr(panel, "_render_content", Mock(return_value=editor_available))
    panel._editor.render = Mock()

    assert panel.render(SimpleNamespace(), make_context())
    panel._draw_source_frames.assert_called_once_with(ui)
    panel._render_content.assert_called_once()
    assert panel._editor.render.call_count == int(editor_available)


def test_draw_source_frames_adds_three_frames_and_separator(monkeypatch):
    ui = make_ui()
    separator = Mock()
    monkeypatch.setattr(panel_module, "draw_gml_separator", separator)
    monkeypatch.setattr(
        panel_module,
        "GAMETHEME",
        SimpleNamespace(colors=SimpleNamespace(text_dim="dim")),
    )

    UnitDesignPanel._draw_source_frames(ui)

    assert ui.frame.call_args_list == [
        call("frmInner/frmUnitInfo"),
        call("frmInner/tabGroups"),
        call("frmInner/frmUnitInfo1"),
    ]
    separator.assert_called_once_with("path:frmInner/frmUnitInfo/picSep", color="dim")


def test_render_content_returns_when_required_design_table_is_missing(monkeypatch):
    panel = UnitDesignPanel()
    monkeypatch.setattr(panel_module, "draw_required_tables", lambda *_args: False)

    assert not panel._render_content(client_state(tables={}), make_context())


def test_render_content_selects_saved_design_and_opens_editor_from_flow_layout(monkeypatch):
    designs = [
        {"id": "inf-1", "class_name": "infantry", "display_name": "Infantry A", "cost": 1000},
        {"id": "inf-2", "class_name": "infantry", "display_name": "Infantry B", "cost": 2000},
    ]
    panel, state, context, ui, imgui = make_panel_for_content(
        monkeypatch,
        designs=designs,
        selection_id="inf-1",
        design_result=(True, 1),
        clicked=True,
    )

    assert panel._render_content(state, context, ui)

    assert panel._selection.design_id == "inf-2"
    assert panel._role == "infantry"
    panel._render_overview.assert_called_once_with(designs[1], ui, state)
    panel._editor.open.assert_called_once_with("infantry", state)
    assert imgui.begin_disabled.call_args.args == (False,)
    assert imgui.button.call_args.kwargs["test_id"] == "unit_design.create.open"
    assert imgui.text_wrapped.called


def test_render_content_recovers_selected_design_from_global_catalog(monkeypatch):
    design = {"id": "tank-1", "class_name": "tanks", "display_name": "Tank", "cost": 3500}
    panel, state, context, ui, _imgui = make_panel_for_content(
        monkeypatch,
        designs=[],
        all_designs=[design],
        selection_id="tank-1",
        role_result=(False, 1),
    )

    assert panel._render_content(state, context, ui)

    panel._presenter.designs_for_country.assert_called_once_with(state, "UKR")
    assert panel._role == "tanks"
    panel._render_overview.assert_called_once_with(design, ui, state)


def test_render_content_falls_back_to_first_design_and_statistics_tab(monkeypatch):
    design = {"id": "inf-1", "class_name": "infantry", "display_name": "Infantry", "cost": 100}
    panel, state, context, ui, _imgui = make_panel_for_content(
        monkeypatch,
        designs=[design],
        selection_id="missing-id",
    )
    panel._details_tab = "statistics"

    assert panel._render_content(state, context, ui)

    assert panel._role == "infantry"
    panel._render_statistics.assert_called_once_with(ui, {"attack": 1.0}, state)
    assert panel._selection.design_id == "missing-id"


def test_render_content_handles_unknown_role_and_no_saved_designs(monkeypatch):
    panel, state, context, ui, imgui = make_panel_for_content(
        monkeypatch,
        designs=[{"id": "mystery", "class_name": "unknown"}],
        selection_id="unknown",
        role_result=(False, 0),
        layout=object(),
    )
    context = make_context(own=False)

    assert panel._render_content(state, context, ui)

    assert panel._role == "infantry"
    assert imgui.combo.call_args_list[1].args[2] == ["No saved designs"]
    panel._render_overview.assert_called_once_with(None, ui, state)
    ui.text.assert_any_call("frmInner/frmUnitInfo1/txtCost", "—")
    assert ui.button.call_args.kwargs["enabled"] is False


def test_render_content_uses_source_button_when_design_creation_is_unavailable(monkeypatch):
    panel = UnitDesignPanel()
    panel._presenter = SimpleNamespace(designs_for_country=Mock(return_value=[]))
    panel._render_tab_buttons = Mock()
    panel._render_overview = Mock()
    ui = make_ui(button=False)
    imgui = make_imgui()
    monkeypatch.setattr(panel_module, "imgui", imgui)
    monkeypatch.setattr(panel_module, "draw_required_tables", lambda *_args: True)
    monkeypatch.setattr(
        panel_module,
        "unit_type_options_for_roles",
        lambda _roles, _state: (SimpleNamespace(role="infantry", label="Infantry"),),
    )
    monkeypatch.setattr(panel_module, "contribution_for", lambda _state, key: {
        "base.military.default_role_profiles": {"infantry": SimpleNamespace(domain="ground")},
        "base.military.canonical_role": lambda value: str(value or "").strip().lower(),
    }[key])
    monkeypatch.setattr(panel_module, "active_gml_layout", lambda: None)

    panel._render_content(client_state(tables={}), make_context(own=False), ui)

    assert imgui.begin_disabled.call_args_list == [call(True), call(True)]
    assert imgui.end_disabled.call_count == 2
    imgui.button.assert_called_once_with("NEW DESIGN", test_id="unit_design.create.open")


def test_source_text_uses_plain_imgui_without_active_layout(monkeypatch):
    ui = make_ui()
    imgui = make_imgui()
    monkeypatch.setattr(panel_module, "imgui", imgui)
    monkeypatch.setattr(panel_module, "active_gml_layout", lambda: None)

    UnitDesignPanel._source_text(ui, "slot", 12)

    imgui.text_disabled.assert_called_once_with("12")
    ui.text.assert_not_called()


def test_source_text_uses_gml_slot_when_active_layout_exists(monkeypatch):
    ui = make_ui()
    imgui = make_imgui()
    monkeypatch.setattr(panel_module, "imgui", imgui)
    monkeypatch.setattr(panel_module, "active_gml_layout", lambda: object())

    UnitDesignPanel._source_text(ui, "slot", "value")

    ui.text.assert_called_once_with("slot", "value")
    imgui.text_disabled.assert_not_called()


@pytest.mark.parametrize("design,expected", [
    (None, "No saved design for this role. Select NEW DESIGN to create one."),
    ({}, "No saved design for this role. Select NEW DESIGN to create one."),
    (
        {"display_name": "Tracked", "branch": "air", "class_name": "attack_aircraft"},
        "Tracked · Air domain · fixed Attack Aircraft role.",
    ),
    (
        {"display_name": "", "branch": "", "class_name": ""},
        "Design · Land domain · fixed Generic role.",
    ),
])
def test_design_description_formats_saved_design_and_empty_states(design, expected):
    assert UnitDesignPanel._design_description(design) == expected


def test_render_tab_buttons_updates_selected_tab_and_restores_imgui_style(monkeypatch):
    panel = UnitDesignPanel()
    ui = make_ui()
    ui.button_at.side_effect = [False, True]
    imgui = make_imgui()
    monkeypatch.setattr(panel_module, "imgui", imgui)
    monkeypatch.setattr(
        panel_module,
        "GAMETHEME",
        SimpleNamespace(colors=SimpleNamespace(interaction_active="active", bg_input="input")),
    )

    panel._render_tab_buttons(ui)

    assert panel._details_tab == "statistics"
    assert imgui.push_style_color.call_count == 2
    assert imgui.pop_style_color.call_count == 2
    assert ui.button_at.call_args_list[0].kwargs["offset"] == (0.0, 179.0)
    assert ui.button_at.call_args_list[1].args[1] == "STATISTICS"


def test_render_statistics_falls_back_to_flow_rows_without_layout(monkeypatch):
    panel = UnitDesignPanel()
    ui = make_ui()
    render_rows = Mock()
    monkeypatch.setattr(panel_module, "active_gml_layout", lambda: None)
    monkeypatch.setattr(panel_module, "render_capability_rows", render_rows)

    state = client_state()
    panel._render_statistics(ui, {"attack": 1.0}, state)

    render_rows.assert_called_once_with(
        ui,
        "frmInner/tabGroups/Tab2/frmList/frmSpecs",
        {"attack": 1.0},
        state,
        test_id_prefix="unit_design.statistics",
    )


@pytest.mark.parametrize("list_rect", [None, SimpleNamespace(x=5, y=10, width=120, height=100)])
@pytest.mark.parametrize("child_open", [True, False])
def test_render_statistics_with_layout_handles_missing_rect_and_child_frame(
    monkeypatch, list_rect, child_open
):
    panel = UnitDesignPanel()
    ui = make_ui()
    ui.rect.return_value = list_rect
    ui.rect.side_effect = lambda slot: list_rect
    session = SimpleNamespace(
        window_position=(50.0, 100.0),
        rect_for=Mock(return_value=SimpleNamespace(y=20.0)),
    )
    rows = Mock()
    scrollbar = Mock()
    monkeypatch.setattr(panel_module, "DESIGN_METRICS", tuple((f"key{i}", "Name", f"label{i}") for i in range(12)))
    monkeypatch.setattr(panel_module, "active_gml_layout", lambda: session)
    monkeypatch.setattr(panel_module, "render_capability_rows", rows)
    monkeypatch.setattr(panel, "_update_statistics_scroll", Mock())
    monkeypatch.setattr(panel, "_render_statistics_scrollbar", scrollbar)

    @contextmanager
    def child_frame(*_args, **_kwargs):
        yield child_open

    monkeypatch.setattr(panel_module, "gml_child_frame", child_frame)
    monkeypatch.setattr(panel_module, "use_gml_layout", lambda _session: nullcontext())
    monkeypatch.setattr(panel_module, "imgui", make_imgui())

    panel_state = client_state()
    panel._render_statistics(ui, {"key0": 1.0}, panel_state)

    if list_rect is None:
        rows.assert_not_called()
        scrollbar.assert_not_called()
    else:
        scrollbar.assert_called_once_with(ui, 3)
        rows.assert_called_once_with(
            ui,
            "frmInner/tabGroups/Tab2/frmList/frmSpecs",
            {"key0": 1.0},
            panel_state,
            test_id_prefix="unit_design.statistics",
            visible_keys={f"key{i}" for i in range(9)},
        ) if child_open else rows.assert_not_called()
        assert session.window_position == (50.0, 100.0)


@pytest.mark.parametrize(
    ("max_first_row", "session", "rect", "mouse", "wheel", "initial", "expected"),
    [
        (0, None, None, (0, 0), 1.0, 4, 0),
        (5, None, None, (0, 0), 1.0, 2, 2),
        (5, SimpleNamespace(window_position=(10, 20)), None, (0, 0), 1.0, 2, 2),
        (5, SimpleNamespace(window_position=(10, 20)), SimpleNamespace(x=5, y=5, width=20, height=20), (15, 30), 1.0, 3, 2),
        (5, SimpleNamespace(window_position=(10, 20)), SimpleNamespace(x=5, y=5, width=20, height=20), (15, 30), -2.0, 1, 3),
        (5, SimpleNamespace(window_position=(10, 20)), SimpleNamespace(x=5, y=5, width=20, height=20), (15, 30), 0.0, 1, 1),
        (5, SimpleNamespace(window_position=(10, 20)), SimpleNamespace(x=5, y=5, width=20, height=20), (200, 200), -1.0, 1, 1),
    ],
)
def test_update_statistics_scroll_respects_hover_bounds_and_wheel_direction(
    monkeypatch, max_first_row, session, rect, mouse, wheel, initial, expected
):
    panel = UnitDesignPanel()
    panel._statistics_first_row = initial
    ui = make_ui()
    ui.rect.return_value = rect
    imgui = make_imgui()
    imgui.get_io.return_value = SimpleNamespace(
        mouse_pos=SimpleNamespace(x=mouse[0], y=mouse[1]),
        mouse_wheel=wheel,
    )
    monkeypatch.setattr(panel_module, "active_gml_layout", lambda: session)
    monkeypatch.setattr(panel_module, "imgui", imgui)

    panel._update_statistics_scroll(ui, max_first_row)

    assert panel._statistics_first_row == expected


@pytest.mark.parametrize(
    ("session", "rect", "max_first_row", "clicked", "active", "mouse_y", "expected_first_row"),
    [
        (None, None, 4, False, False, 0.0, 0),
        (SimpleNamespace(window_position=(10.0, 20.0)), None, 4, False, False, 0.0, 0),
        (SimpleNamespace(window_position=(10.0, 20.0)), SimpleNamespace(x=5, y=6, width=8, height=100), 0, False, False, 0.0, 0),
        (SimpleNamespace(window_position=(10.0, 20.0)), SimpleNamespace(x=5, y=6, width=8, height=100), 3, True, False, 1000.0, 3),
        (SimpleNamespace(window_position=(10.0, 20.0)), SimpleNamespace(x=5, y=6, width=8, height=100), 3, False, True, -100.0, 0),
    ],
)
def test_render_statistics_scrollbar_draws_thumb_and_maps_pointer(
    monkeypatch, session, rect, max_first_row, clicked, active, mouse_y, expected_first_row
):
    panel = UnitDesignPanel()
    panel._statistics_first_row = 0
    ui = make_ui()
    ui.rect.return_value = rect
    ui.hitbox.return_value = clicked
    imgui = make_imgui()
    imgui.is_item_active.return_value = active
    imgui.get_io.return_value.mouse_pos.y = mouse_y
    monkeypatch.setattr(panel_module, "DESIGN_METRICS", tuple((f"key{i}", "Name", f"Label{i}") for i in range(12)))
    monkeypatch.setattr(panel_module, "active_gml_layout", lambda: session)
    monkeypatch.setattr(panel_module, "imgui", imgui)

    panel._render_statistics_scrollbar(ui, max_first_row)

    assert panel._statistics_first_row == expected_first_row
    if session is not None and rect is not None:
        assert imgui.get_window_draw_list().add_rect_filled.call_count == 2
        assert ui.hitbox.call_args.kwargs["enabled"] is (max_first_row > 0)
    else:
        ui.hitbox.assert_not_called()


def test_render_overview_uses_flow_layout_when_geometry_is_unavailable(monkeypatch):
    panel = UnitDesignPanel()
    flow = Mock()
    monkeypatch.setattr(panel_module, "active_gml_layout", lambda: None)
    monkeypatch.setattr(panel, "_render_overview_flow", flow)
    ui = make_ui()

    panel._render_overview(None, ui, SimpleNamespace())
    panel._render_overview({"id": "d1"}, ui, SimpleNamespace())

    assert flow.call_args_list == [call(None), call({"id": "d1"})]


def test_render_overview_returns_when_container_rect_is_missing(monkeypatch):
    panel = UnitDesignPanel()
    flow = Mock()
    ui = make_ui()
    ui.rect.return_value = None
    monkeypatch.setattr(panel_module, "active_gml_layout", lambda: object())
    monkeypatch.setattr(panel, "_render_overview_flow", flow)

    panel._render_overview({"id": "d1"}, ui, SimpleNamespace())

    flow.assert_called_once_with({"id": "d1"})


def test_render_overview_shows_no_design_guidance_for_empty_selection(monkeypatch):
    panel = UnitDesignPanel()
    ui = make_ui()
    ui.rect.return_value = SimpleNamespace(x=5.0, y=10.0, width=140.0, height=100.0)
    session = SimpleNamespace(window_position=(100.0, 200.0))
    imgui = make_imgui()
    monkeypatch.setattr(panel_module, "active_gml_layout", lambda: session)
    monkeypatch.setattr(panel_module, "imgui", imgui)

    panel._render_overview(None, ui, SimpleNamespace())

    assert any("3D model preview unavailable" in str(call.args[0]) for call in imgui.text_disabled.call_args_list)
    assert any("No design selected" in str(call.args[0]) for call in imgui.text_disabled.call_args_list)
    assert imgui.set_cursor_screen_pos.call_count == 2


def test_render_overview_can_return_to_design_list(monkeypatch):
    panel = UnitDesignPanel(UnitDesignSelection("tank-1"))
    ui = make_ui()
    ui.rect.return_value = SimpleNamespace(x=5.0, y=10.0, width=140.0, height=100.0)
    ui.button_at.return_value = True
    imgui = make_imgui()
    monkeypatch.setattr(panel_module, "active_gml_layout", lambda: SimpleNamespace(window_position=(10.0, 20.0)))
    monkeypatch.setattr(panel_module, "imgui", imgui)

    panel._render_overview({"id": "tank-1", "display_name": "Main tank"}, ui, SimpleNamespace())

    assert panel._selection.design_id is None
    imgui.text_disabled.assert_any_call("Viewing design: Main tank", test_id="unit_design.detail.selected")
    ui.button_at.assert_called_once()


def test_render_overview_renders_fixed_profile_and_capability_rules(monkeypatch):
    panel = UnitDesignPanel()
    design = {
        "id": "tank-1",
        "class_name": "tanks",
        "domain": "land",
        "quality": 0.85,
        "speed": 0.6,
        "firepower": 0.75,
        "valid_targets_json": '["armor", "fortification"]',
        "vulnerabilities_json": '["air"]',
    }
    ui = make_ui()
    ui.rect.return_value = SimpleNamespace(x=5.0, y=10.0, width=140.0, height=100.0)
    imgui = make_imgui()
    monkeypatch.setattr(panel_module, "active_gml_layout", lambda: SimpleNamespace(window_position=(10.0, 20.0)))
    monkeypatch.setattr(panel_module, "imgui", imgui)
    panel._render_overview(design, ui, client_state())

    assert any("Fixed role definition" in str(call.args[0]) for call in imgui.text_disabled.call_args_list)
    assert any("Quality 85%  Speed 60%  Firepower 75%" in str(call.args[0]) for call in imgui.text_disabled.call_args_list)
    wrapped = [call.args[0] for call in imgui.text_wrapped.call_args_list]
    assert "Fixed targets: armor, fortification" in wrapped
    assert "Fixed counter vulnerabilities: air" in wrapped
    assert imgui.push_text_wrap_pos.call_count == 3
    assert imgui.pop_text_wrap_pos.call_count == 3


def test_render_overview_flow_describes_empty_and_saved_designs(monkeypatch):
    imgui = make_imgui()
    monkeypatch.setattr(panel_module, "imgui", imgui)

    UnitDesignPanel._render_overview_flow(None)
    UnitDesignPanel._render_overview_flow(
        {"valid_targets_json": '["ground"]', "vulnerabilities_json": "bad-json"}
    )

    assert any("No design selected" in str(call.args[0]) for call in imgui.text_disabled.call_args_list)
    assert "Fixed targets: ground" in [call.args[0] for call in imgui.text_wrapped.call_args_list]
    assert "Fixed counter vulnerabilities: none configured" in [call.args[0] for call in imgui.text_wrapped.call_args_list]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('["a", 2]', ["a", "2"]),
        ('{"not": "a list"}', []),
        ("invalid-json", []),
        (None, []),
    ],
)
def test_decode_list_accepts_json_arrays_and_rejects_other_values(value, expected):
    assert UnitDesignPanel._decode_list(value) == expected
