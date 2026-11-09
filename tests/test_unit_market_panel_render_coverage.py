from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import src.client.ui.panels.military.unit_market_panel as market_module
from src.client.ui.panels.military.unit_market_panel import UnitMarketPanel


def _rect(x=10.0, y=20.0, width=80.0, height=16.0):
    return SimpleNamespace(x=x, y=y, width=width, height=height)


def _theme(monkeypatch):
    colors = SimpleNamespace(
        bg_window=(0.1, 0.2, 0.3, 1.0),
        panel_bg_dark=(0.2, 0.3, 0.4, 0.5),
        pressed_neutral=(0.8, 0.1, 0.2, 0.9),
        hover_neutral=(0.2, 0.8, 0.3, 0.5),
        bg_input=(0.1, 0.1, 0.1, 1.0),
        accent=(0.9, 0.8, 0.1, 1.0),
        text_main=(1.0, 1.0, 1.0, 1.0),
        text_dim=(0.5, 0.5, 0.5, 1.0),
        positive=(0.1, 0.9, 0.2, 1.0),
    )
    monkeypatch.setattr(market_module, "GAMETHEME", SimpleNamespace(colors=colors))
    return colors


def test_render_centers_window_filters_roles_and_returns_closed_state(monkeypatch):
    display_size = {"value": SimpleNamespace(x=0, y=0)}
    opened = {"value": False}
    window_calls = []

    @contextmanager
    def window(*args, **kwargs):
        window_calls.append((args, kwargs))
        yield opened["value"]

    imgui = SimpleNamespace(
        get_io=lambda: SimpleNamespace(display_size=display_size["value"]),
        get_main_viewport=lambda: SimpleNamespace(size=SimpleNamespace(x=400, y=300)),
    )
    monkeypatch.setattr(market_module, "imgui", imgui)
    monkeypatch.setattr(market_module, "WindowManager", SimpleNamespace(window=window))
    ui = Mock()
    gml_widgets = Mock(return_value=ui)
    monkeypatch.setattr(market_module, "GMLWidgets", gml_widgets)

    panel = UnitMarketPanel()
    panel._presenter.market_listings_for_country = Mock(return_value=[])
    panel._designs_by_id = Mock(return_value={})
    assert panel.render(SimpleNamespace(), SimpleNamespace(target_tag=" usa ")) is False
    assert window_calls[0][1]["x"] == 0.0
    assert window_calls[0][1]["y"] == 0.0
    gml_widgets.assert_not_called()

    display_size["value"] = SimpleNamespace(x=800, y=500)
    opened["value"] = True
    listings = [
        {"id": "A", "unit_type": "infantry"},
        {"id": "B", "unit_type": "armor"},
        {"id": "C", "unit_type": ""},
    ]
    panel._presenter.market_listings_for_country.return_value = listings
    panel._listing_role = Mock(side_effect=lambda row, _designs: {
        "A": "infantry", "B": "armor", "C": "",
    }[row["id"]])
    options = [
        SimpleNamespace(role="infantry", label="Infantry"),
        SimpleNamespace(role="armor", label="Armor"),
    ]
    roles_seen = []

    def options_for(roles):
        roles_seen.extend(roles)
        return options

    monkeypatch.setattr(market_module, "unit_type_options_for_roles", options_for)
    panel._selected_role = "stale"
    panel._draw_source_frames = Mock()
    panel._render_type_selector = Mock()
    panel._render_listing_list = Mock(return_value=listings[0])
    panel._render_selection = Mock()
    panel._render_capabilities = Mock()
    state = SimpleNamespace()
    context = SimpleNamespace(target_tag=" usa ")

    assert panel.render(state, context) is True

    assert window_calls[1][1]["x"] == 44.0
    assert window_calls[1][1]["y"] == 14.0
    assert window_calls[1][1]["w"] == 712.0
    assert window_calls[1][1]["h"] == 472.0
    assert panel._presenter.market_listings_for_country.call_args.args == (state, "USA")
    assert roles_seen == ["infantry", "armor"]
    assert panel._selected_role == "infantry"
    panel._render_listing_list.assert_called_once_with(ui, [listings[0]])
    panel._render_selection.assert_called_once_with(ui, listings[0], {}, context)
    panel._render_capabilities.assert_called_once_with(ui, listings[0], {})


def test_source_frames_and_type_selector_reset_changed_selection(monkeypatch):
    ui = Mock()
    UnitMarketPanel._draw_source_frames(ui)
    assert [call.args[0] for call in ui.frame.call_args_list] == [
        "frmBorder/frmInner",
        "frmBorder/frmInner/frmDesignList",
        "frmDesignView",
        "frmDesignView/frm3dModel",
        "frmDesignView/frmUnitSpecs",
    ]

    imgui = Mock()
    imgui.StyleVar_.frame_padding = 1
    imgui.combo.return_value = (True, 1)
    monkeypatch.setattr(market_module, "imgui", imgui)
    panel = UnitMarketPanel()
    panel._selected_role = "infantry"
    panel._selected_listing_id = "listing-1"
    panel._quantity = 4
    panel._quantity_edit_text = "4"
    panel._quantity_editing = True
    panel._request_sent = True
    panel._reset_quantity_repeat = Mock()
    options = [SimpleNamespace(label="Infantry"), SimpleNamespace(label="Armor")]

    panel._render_type_selector(ui, ["infantry", "armor"], options)

    assert panel._selected_role == "armor"
    assert panel._selected_listing_id == ""
    assert panel._quantity == 0
    assert panel._quantity_edit_text == ""
    assert panel._quantity_editing is False
    assert panel._request_sent is False
    panel._reset_quantity_repeat.assert_called_once_with()
    imgui.begin_disabled.assert_called_once_with(False)
    imgui.combo.assert_called_once_with(
        "##unit_market.type", 0, ["Infantry", "Armor"],
        test_id="unit_market.type",
        gml_id="Unit_Buy_Used_Window/frmBorder/frmInner/frmDesignList/cboUnitType",
    )


def test_type_selector_shows_empty_label_and_keeps_empty_role_disabled(monkeypatch):
    imgui = Mock()
    imgui.StyleVar_.frame_padding = 1
    imgui.combo.return_value = (True, 0)
    monkeypatch.setattr(market_module, "imgui", imgui)
    ui = Mock()
    panel = UnitMarketPanel()

    panel._render_type_selector(ui, [], [])

    assert panel._selected_role == ""
    imgui.begin_disabled.assert_called_once_with(True)
    assert imgui.combo.call_args.args[2] == ["No eligible unit types"]


def test_quantity_drawing_helpers_handle_missing_layout_and_empty_text(monkeypatch):
    colors = _theme(monkeypatch)
    imgui = Mock()
    imgui.get_scroll_x.return_value = 0.0
    imgui.get_scroll_y.return_value = 0.0
    imgui.get_color_u32.side_effect = lambda value: value
    monkeypatch.setattr(market_module, "imgui", imgui)
    ui = Mock()
    ui.rect.return_value = _rect()
    monkeypatch.setattr(market_module, "active_gml_layout", lambda: None)
    panel = UnitMarketPanel()

    panel._draw_quantity_mask(ui, "quantity", False, False)
    panel._draw_quantity_selection(ui, "quantity", "123")
    panel._draw_quantity_caret(ui, "quantity", "123")
    UnitMarketPanel._draw_quantity_arrow(ui, "up", down=False, enabled=True)
    panel._draw_quantity_text(ui, "quantity", "", test_id="empty")

    imgui.get_window_draw_list.assert_not_called()
    ui.text_at.assert_not_called()

    ui.rect.return_value = None
    panel._quantity_selection_start = 0
    panel._quantity_selection_end = 2
    monkeypatch.setattr(market_module, "active_gml_layout", lambda: SimpleNamespace(window_position=(0, 0)))
    panel._draw_quantity_selection(ui, "quantity", "123")
    UnitMarketPanel._draw_quantity_arrow(ui, "up", down=False, enabled=True)
    panel._draw_quantity_caret(ui, "quantity", "123")
    panel._draw_quantity_mask(ui, "quantity", False, False)
    imgui.get_window_draw_list.assert_not_called()


def test_quantity_mask_selection_caret_and_arrow_draw_at_scrolled_positions(monkeypatch):
    colors = _theme(monkeypatch)
    draw = Mock()
    imgui = Mock()
    imgui.calc_text_size.side_effect = lambda value: SimpleNamespace(x=len(value) * 5.0, y=8.0)
    imgui.get_scroll_x.return_value = 4.0
    imgui.get_scroll_y.return_value = 6.0
    imgui.get_window_draw_list.return_value = draw
    imgui.get_color_u32.side_effect = lambda value: ("color", value)
    monkeypatch.setattr(market_module, "imgui", imgui)
    session = SimpleNamespace(window_position=(100.0, 200.0))
    monkeypatch.setattr(market_module, "active_gml_layout", lambda: session)
    ui = Mock()
    ui.rect.return_value = _rect(width=50.0, height=16.0)
    panel = UnitMarketPanel()
    panel._quantity_selection_start = 1
    panel._quantity_selection_end = 3
    panel._quantity_cursor_pos = 9

    panel._draw_quantity_mask(ui, "quantity", input_active=True, input_hovered=False)
    panel._draw_quantity_text(ui, "quantity", "12", test_id="quantity.value")
    panel._draw_quantity_selection(ui, "quantity", "12345")
    panel._draw_quantity_caret(ui, "quantity", "12")
    UnitMarketPanel._draw_quantity_arrow(ui, "quantity", down=True, enabled=True)
    UnitMarketPanel._draw_quantity_arrow(ui, "quantity", down=False, enabled=False)

    assert draw.add_rect_filled.call_args_list[0].args[:2] == ((107.0, 215.0), (155.0, 229.0))
    assert ui.text_at.call_args.kwargs == {
        "offset": (37.0, 4.0), "max_width": 10.0, "test_id": "quantity.value",
    }
    assert draw.add_rect_filled.call_args_list[1].args[:2] == ((133.0, 218.0), (143.0, 226.0))
    assert draw.add_line.call_args.args[:2] == ((153.0, 218.0), (153.0, 226.0))
    assert draw.add_triangle_filled.call_count == 2
    assert draw.add_triangle_filled.call_args_list[0].args[0] == (128.0, 220.0)
    assert draw.add_triangle_filled.call_args_list[1].args[2] == (131.0, 220.0)
    assert colors.accent[:3] == (0.9, 0.8, 0.1)


def test_render_capabilities_handles_missing_layout_rect_and_closed_child(monkeypatch):
    imgui = Mock()
    imgui.ChildFlags_.borders = 1
    monkeypatch.setattr(market_module, "imgui", imgui)
    panel = UnitMarketPanel()
    panel._saved_capabilities = Mock(return_value={})
    ui = Mock()
    monkeypatch.setattr(market_module, "active_gml_layout", lambda: None)
    panel._render_capabilities(ui, None, {})

    session = SimpleNamespace(
        layout=SimpleNamespace(component=Mock(return_value=None)),
        rect_for=Mock(),
        resize_component=Mock(),
    )
    monkeypatch.setattr(market_module, "active_gml_layout", lambda: session)
    panel._render_capabilities(ui, {"design_id": "D"}, {"D": {"design": "saved"}})
    session.layout.component.assert_called_once_with(
        "Unit_Buy_Used_Window/frmDesignView/frmUnitSpecs/frmList",
    )
    imgui.begin_child.assert_not_called()

    rect = _rect(width=120.0, height=210.0)
    session.layout.component.return_value = object()
    session.rect_for.return_value = rect
    imgui.begin_child.return_value = False
    panel._render_capabilities(ui, None, {})

    session.resize_component.assert_called_once_with(
        "Unit_Buy_Used_Window/frmDesignView/frmUnitSpecs/frmList", width=134.0,
    )
    imgui.begin_child.assert_called_once_with(
        "unit_market.capabilities", (120.0, 210.0), child_flags=1,
        test_id="unit_market.capabilities",
        gml_id="Unit_Buy_Used_Window/frmDesignView/frmUnitSpecs/frmList",
    )
    imgui.end_child.assert_called_once_with()


def test_render_capabilities_draws_each_source_metric_when_child_is_open(monkeypatch):
    imgui = Mock()
    imgui.ChildFlags_.borders = 1
    imgui.begin_child.return_value = True
    monkeypatch.setattr(market_module, "imgui", imgui)
    component = object()
    rect = _rect(width=90.0, height=240.0)
    session = SimpleNamespace(
        layout=SimpleNamespace(component=Mock(return_value=component)),
        rect_for=Mock(return_value=rect),
        resize_component=Mock(),
    )
    monkeypatch.setattr(market_module, "active_gml_layout", lambda: session)
    monkeypatch.setattr(market_module, "DESIGN_METRICS", [
        ("armor", "Armor", "Armor"),
        ("speed", "Speed", "Speed"),
    ])
    panel = UnitMarketPanel()
    panel._saved_capabilities = Mock(return_value={"armor": 4.0})
    panel._draw_scrolled_text = Mock()
    panel._draw_scrolled_capability = Mock()
    ui = Mock()
    design = {"id": "D"}

    panel._render_capabilities(ui, {"design_id": "D"}, {"D": design})

    panel._saved_capabilities.assert_called_once_with(design)
    assert panel._draw_scrolled_text.call_args_list == [
        ((session, "Unit_Buy_Used_Window/frmDesignView/frmUnitSpecs/frmList/frmInner/lblArmor", "Armor", "unit_market.capability.armor.label"), {}),
        ((session, "Unit_Buy_Used_Window/frmDesignView/frmUnitSpecs/frmList/frmInner/lblSpeed", "Speed", "unit_market.capability.speed.label"), {}),
    ]
    assert panel._draw_scrolled_capability.call_args_list == [
        ((session, "Unit_Buy_Used_Window/frmDesignView/frmUnitSpecs/frmList/frmInner/frmArmor", "armor", 4.0), {}),
        ((session, "Unit_Buy_Used_Window/frmDesignView/frmUnitSpecs/frmList/frmInner/frmSpeed", "speed", None), {}),
    ]
