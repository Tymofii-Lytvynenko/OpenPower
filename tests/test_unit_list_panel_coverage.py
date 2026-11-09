from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.military import unit_list_panel as panel_module
from src.client.ui.panels.military.unit_list_panel import (
    UnitListPanel,
    _UnitListEntry,
    _format_intelligence_context,
    _format_quantity,
    _source_position,
    _status_color,
    _status_kind,
)
from src.shared.actions import ActionDisbandUnits, ActionListUsedUnit


class FakeUI:
    def __init__(self, *, clicked=(), rects=None):
        self.clicked = set(clicked)
        self.rects = rects or {}
        self.calls = []

    def path(self, slot):
        return slot

    def text(self, *args, **kwargs):
        self.calls.append(("text", args, kwargs))

    def text_at(self, *args, **kwargs):
        self.calls.append(("text_at", args, kwargs))

    def meter(self, *args, **kwargs):
        self.calls.append(("meter", args, kwargs))

    def rect(self, slot):
        return self.rects.get(slot)

    def hitbox(self, slot, test_id, **kwargs):
        self.calls.append(("hitbox", slot, test_id, kwargs))
        return test_id in self.clicked

    def button(self, slot, label, test_id, **kwargs):
        self.calls.append(("button", slot, label, test_id, kwargs))
        return test_id in self.clicked


class FakeClient:
    player_id = "player-1"

    def __init__(self):
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)


def entry(unit_id="U1", **overrides):
    values = {
        "unit_id": unit_id,
        "unit_type": "Infantry",
        "quantity_text": "10",
        "quantity_value": 10,
        "name": "First Division",
        "position": "Capital",
        "status": "Ready",
        "training_level": "Regular",
        "for_sale": False,
        "design_id": "design-1",
        "design_cost": 1200.0,
        "upkeep_value": 30.0,
        "upkeep_text": "30",
        "status_kind": "ready",
        "tooltip": "Unit tooltip",
    }
    values.update(overrides)
    return _UnitListEntry(**values)


def fake_imgui(**overrides):
    values = {
        "StyleVar_": SimpleNamespace(frame_padding="frame_padding"),
        "MouseButton_": SimpleNamespace(left="left"),
        "push_style_var": Mock(),
        "pop_style_var": Mock(),
        "get_io": Mock(return_value=SimpleNamespace(
            display_size=SimpleNamespace(x=1200, y=800),
            mouse_pos=SimpleNamespace(x=0, y=0),
            mouse_wheel=0.0,
            key_ctrl=False,
            mouse_double_click_time=0.3,
        )),
        "get_main_viewport": Mock(return_value=SimpleNamespace(size=SimpleNamespace(x=1200, y=800))),
        "get_time": Mock(return_value=1.0),
        "is_mouse_double_clicked": Mock(return_value=False),
        "is_item_active": Mock(return_value=False),
        "get_color_u32": Mock(side_effect=lambda color: color),
        "get_window_draw_list": Mock(return_value=Mock()),
        "get_scroll_x": Mock(return_value=0.0),
        "get_scroll_y": Mock(return_value=0.0),
        "combo": Mock(return_value=(False, 0)),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_render_uses_fallback_viewport_and_returns_window_state(monkeypatch):
    fake = fake_imgui(get_io=Mock(return_value=SimpleNamespace(display_size=SimpleNamespace(x=0, y=0))))
    monkeypatch.setattr(panel_module, "imgui", fake)
    window_calls = []

    @contextmanager
    def window(*args, **kwargs):
        window_calls.append((args, kwargs))
        yield True

    monkeypatch.setattr(panel_module.WindowManager, "window", window)
    widgets = Mock()
    monkeypatch.setattr(panel_module, "GMLWidgets", Mock(return_value=widgets))
    panel = UnitListPanel()
    panel._render_content = Mock()

    assert panel.render(object(), PanelRenderContext(target_tag="USA", is_own_country=True)) is True

    assert window_calls[0][1]["x"] == pytest.approx(182.5)
    assert window_calls[0][1]["y"] == pytest.approx(186.5)
    widgets.frame.assert_any_call("frmInner/frmList")
    panel._render_content.assert_called_once()


def test_render_returns_false_without_constructing_widgets(monkeypatch):
    monkeypatch.setattr(panel_module, "imgui", fake_imgui())

    @contextmanager
    def window(*args, **kwargs):
        yield False

    monkeypatch.setattr(panel_module.WindowManager, "window", window)
    widgets = Mock()
    monkeypatch.setattr(panel_module, "GMLWidgets", widgets)

    assert UnitListPanel().render(object(), PanelRenderContext(target_tag="USA", is_own_country=True)) is False
    widgets.assert_not_called()


def test_render_content_composes_owned_and_foreign_flows(monkeypatch):
    panel = UnitListPanel()
    values = [entry(str(index)) for index in range(25)]
    panel._own_entries = Mock(return_value=values)
    panel._render_type_filter = Mock()
    panel._render_headers = Mock()
    panel._filtered_entries = Mock(return_value=values)
    panel._sorted_entries = Mock(return_value=values)
    panel._apply_wheel_scroll = Mock()
    panel._render_scrollbar = Mock()
    panel._render_rows = Mock()
    panel._render_actions = Mock()
    panel._first_visible_row = 12
    context = PanelRenderContext(target_tag=" usa ", is_own_country=True)
    state = object()
    ui = FakeUI()

    panel._render_content(state, context, ui)

    panel._own_entries.assert_called_once_with(state, "USA")
    panel._render_headers.assert_called_once_with(ui, own_country=True)
    panel._apply_wheel_scroll.assert_called_once_with(ui, 5)
    panel._render_scrollbar.assert_called_once_with(ui, 5)
    panel._render_rows.assert_called_once_with(values, True, ui)
    panel._render_actions.assert_called_once()
    assert panel._first_visible_row == 5

    panel = UnitListPanel()
    panel._foreign_entries = Mock(return_value=[])
    panel._render_type_filter = Mock()
    panel._render_accuracy = Mock()
    panel._render_headers = Mock()
    panel._filtered_entries = Mock(return_value=[])
    panel._sorted_entries = Mock(return_value=[])
    panel._apply_wheel_scroll = Mock()
    panel._render_scrollbar = Mock()
    panel._render_rows = Mock()
    panel._render_actions = Mock()
    foreign_context = PanelRenderContext(target_tag="CAN", is_own_country=False)

    panel._render_content(object(), foreign_context, ui)

    panel._render_accuracy.assert_called_once()
    panel._render_headers.assert_called_once_with(ui, own_country=False)
    panel._render_rows.assert_called_once_with([], False, ui)
    panel._render_actions.assert_not_called()


def test_own_entries_convert_presenter_rows():
    panel = UnitListPanel()
    panel._presenter = Mock()
    panel._presenter.unit_rows.return_value = [SimpleNamespace(
        unit_id="U1", unit_type="Tank", quantity=3, design_name="Armor",
        location="North", status="Ready", training_level="Veteran", for_sale=False,
        design_id="d1", design_cost=5000, upkeep=25, route_summary="North route",
    )]

    values = panel._own_entries(object(), "USA")

    panel._presenter.unit_rows.assert_called_once()
    assert values[0].name == "Armor"
    assert values[0].upkeep_text == "25"
    assert "Route: North route" in values[0].tooltip


def test_estimate_entries_handles_missing_fields_and_role_ranges():
    rows = UnitListPanel._estimate_entries([{
        "target_country_id": "MEX",
        "status": "estimated",
        "observed_at_minute": -5,
        "total_count_range": (1200, 2400),
        "role_count_ranges": (("air_defense", 2, 4),),
    }], "MEX")

    assert len(rows) == 2
    assert rows[0].quantity_text == "1 200–2 400"
    assert rows[0].position == "No source · t=0"
    assert rows[0].name == "MEX"
    assert rows[1].unit_type == "Air Defense"
    assert rows[1].quantity_text == "2–4"
    assert "estimate 1" in rows[1].name


def test_signal_entries_formats_outdated_signal_without_source():
    rows = UnitListPanel._signal_entries([{
        "target_country_id": "CAN",
        "domain": "",
        "status": "outdated",
        "observed_at_minute": 0,
        "source_factors": {"intelligence_coverage": "invalid"},
    }], "CAN")

    assert rows[0].unit_type == "Military signal"
    assert rows[0].status == "Outdated signal"
    assert rows[0].status_kind == "warning"
    assert rows[0].position == "No source · t=0"
    assert "No unit identity is shown" in rows[0].tooltip


def test_type_filter_updates_selection_and_resets_scroll_and_rows(monkeypatch):
    fake = fake_imgui(combo=Mock(return_value=(True, 1)))
    monkeypatch.setattr(panel_module, "imgui", fake)
    panel = UnitListPanel()
    panel._filter_type = "No longer available"
    panel._first_visible_row = 8
    panel._selected_unit_ids = {"U1"}
    ui = FakeUI()

    panel._render_type_filter([entry()], ui)

    assert panel._filter_type == panel_module.REFERENCE_UNIT_TYPE_OPTIONS[0].label
    assert panel._first_visible_row == 0
    assert panel._selected_unit_ids == set()
    fake.push_style_var.assert_called_once()
    fake.pop_style_var.assert_called_once()
    assert any(call[0] == "text" and call[1][1] == "UNIT TYPE" for call in ui.calls)


def test_type_filter_ignores_invalid_combo_index_and_restores_style(monkeypatch):
    fake = fake_imgui(combo=Mock(return_value=(True, 999)))
    monkeypatch.setattr(panel_module, "imgui", fake)
    panel = UnitListPanel()
    panel._filter_type = "All"

    panel._render_type_filter([], FakeUI())

    assert panel._filter_type == "All"
    fake.push_style_var.assert_called_once()
    fake.pop_style_var.assert_called_once()


def test_accuracy_clamps_and_averages_estimate_confidence():
    panel = UnitListPanel()
    panel._presenter = Mock()
    panel._presenter.foreign_force_estimates_for_country.return_value = [
        {"confidence": -0.5}, {"confidence": 1.5},
    ]
    ui = FakeUI()

    panel._render_accuracy(object(), "MEX", ui)

    confidence_call = next(call for call in ui.calls if call[0] == "text" and call[1][1] == "50%")
    assert confidence_call[2]["right"] is True
    meter_call = next(call for call in ui.calls if call[0] == "meter")
    assert meter_call[1][1] == pytest.approx(0.5)


def test_accuracy_without_estimates_shows_unavailable_state():
    panel = UnitListPanel()
    panel._presenter = Mock()
    panel._presenter.foreign_force_estimates_for_country.return_value = []
    ui = FakeUI()

    panel._render_accuracy(object(), "MEX", ui)

    assert any(call[0] == "text" and call[1][1] == "—" for call in ui.calls)
    assert next(call for call in ui.calls if call[0] == "meter")[1][1] == 0.0


def test_header_click_updates_sort_and_foreign_upkeep_is_disabled():
    panel = UnitListPanel()
    ui = FakeUI(clicked={
        "unit_list.sort.quantity.arrow",
        "unit_list.sort.training",
        "unit_list.sort.for_sale",
    })

    panel._render_headers(ui, own_country=False)

    assert panel._sort_key == "for_sale"
    assert panel._sort_ascending is True
    disabled_upkeep = [call for call in ui.calls if call[0] == "hitbox" and call[2] == "unit_list.sort.upkeep"]
    assert disabled_upkeep[0][3]["enabled"] is False
    assert any(call[0] == "hitbox" and call[2] == "unit_list.sort.upkeep.arrow" and call[3]["enabled"] is False for call in ui.calls)


def test_sort_header_hitbox_stops_before_separate_arrow_target():
    rects = {
        "frmInner/frmList/btnType": SimpleNamespace(x=10, y=5, width=80, height=20),
        "frmInner/frmList/btnTypeIcon": SimpleNamespace(x=70, y=5, width=12, height=20),
    }
    ui = FakeUI(clicked={"unit_list.sort.type"}, rects=rects)
    panel = UnitListPanel()

    panel._render_headers(ui, own_country=True)

    type_hit = next(call for call in ui.calls if call[0] == "hitbox" and call[2] == "unit_list.sort.type")
    assert type_hit[3]["width"] == 60
    assert panel._sort_key == "type"
    assert panel._sort_ascending is False


def test_header_text_handles_missing_rect_and_draws_dimmed_text():
    ui = FakeUI(rects={"slot": SimpleNamespace(width=8)})

    UnitListPanel._draw_header_text(ui, "missing", "Name", True)
    UnitListPanel._draw_header_text(ui, "slot", "Upkeep", False)

    call = next(call for call in ui.calls if call[0] == "text_at")
    assert call[2]["max_width"] == 3.0
    assert call[2]["tooltip"] == "OpenPower does not expose this source value."


def test_sort_icon_only_draws_for_active_sort_key():
    panel = UnitListPanel()
    ui = FakeUI(rects={"active": SimpleNamespace(width=30)})

    panel._draw_sort_icon(ui, "inactive", "quantity")
    panel._draw_sort_icon(ui, "active", "type")

    assert len([call for call in ui.calls if call[0] == "text_at"]) == 1
    assert ui.calls[0][1][1] == "▲"


def test_select_sort_toggles_direction_and_resets_scroll():
    panel = UnitListPanel()
    panel._first_visible_row = 6

    panel._select_sort("type")
    assert panel._sort_ascending is False
    assert panel._first_visible_row == 0

    panel._first_visible_row = 3
    panel._select_sort("quantity")
    assert panel._sort_key == "quantity"
    assert panel._sort_ascending is True
    assert panel._first_visible_row == 0


def test_filter_supports_role_labels_and_arbitrary_foreign_types():
    panel = UnitListPanel()
    rows = [entry(unit_type="infantry"), entry("U2", unit_type="tanks"), entry("U3", unit_type="Orbital Defense")]
    panel._filter_type = "Infantry"
    assert [row.unit_id for row in panel._filtered_entries(rows)] == ["U1"]

    panel._filter_type = "Orbital Defense"
    assert [row.unit_id for row in panel._filtered_entries(rows)] == ["U3"]

    panel._filter_type = "All"
    assert panel._filtered_entries(rows) is rows


@pytest.mark.parametrize(
    ("sort_key", "ascending", "expected"),
    [
        ("quantity", True, ["U2", "U1", "U3"]),
        ("quantity", False, ["U1", "U2", "U3"]),
        ("training", True, ["U2", "U1", "U3"]),
        ("name", True, ["U2", "U1", "U3"]),
        ("status", False, ["U1", "U2", "U3"]),
        ("value", True, ["U2", "U1", "U3"]),
        ("upkeep", False, ["U2", "U1", "U3"]),
        ("for_sale", False, ["U1", "U2", "U3"]),
        ("unknown", True, ["U1", "U2", "U3"]),
    ],
)
def test_sorted_entries_keeps_missing_values_after_known_values(sort_key, ascending, expected):
    rows = [
        entry("U1", quantity_value=8, training_level="Elite", name="Zulu", status="Ready", design_cost=90, upkeep_value=4, for_sale=True),
        entry("U2", quantity_value=2, training_level="Recruit", name="Alpha", status="Blocked", design_cost=10, upkeep_value=30, for_sale=False),
        entry("U3", quantity_value=None, training_level="unknown", name="", status="", design_cost=None, upkeep_value=None, for_sale=False),
    ]
    panel = UnitListPanel()
    panel._sort_key = sort_key
    panel._sort_ascending = ascending

    result = panel._sorted_entries(rows)

    assert [row.unit_id for row in result] == expected


def test_wheel_scroll_clamps_and_moves_only_inside_roster(monkeypatch):
    panel = UnitListPanel()
    ui = FakeUI(rects={"frmInner/frmList/frmList": SimpleNamespace(x=10, y=20, width=100, height=100)})
    io = SimpleNamespace(mouse_pos=SimpleNamespace(x=30, y=60), mouse_wheel=1.0)
    monkeypatch.setattr(panel_module, "imgui", fake_imgui(get_io=Mock(return_value=io)))
    monkeypatch.setattr(panel_module, "active_gml_layout", lambda: SimpleNamespace(window_position=(0, 0)))
    panel._first_visible_row = 4

    panel._apply_wheel_scroll(ui, 10)

    assert panel._first_visible_row == 1
    io.mouse_wheel = -2.0
    panel._apply_wheel_scroll(ui, 10)
    assert panel._first_visible_row == 7
    io.mouse_pos = SimpleNamespace(x=500, y=500)
    panel._apply_wheel_scroll(ui, 10)
    assert panel._first_visible_row == 7


def test_wheel_scroll_resets_when_no_overflow_and_ignores_missing_layout(monkeypatch):
    panel = UnitListPanel()
    panel._first_visible_row = 7
    ui = FakeUI()
    panel._apply_wheel_scroll(ui, 0)
    assert panel._first_visible_row == 0

    panel._first_visible_row = 2
    monkeypatch.setattr(panel_module, "active_gml_layout", lambda: None)
    panel._apply_wheel_scroll(ui, 10)
    assert panel._first_visible_row == 2


def test_scrollbar_draws_track_and_maps_click_to_row(monkeypatch):
    draw = Mock()
    fake = fake_imgui(
        get_window_draw_list=Mock(return_value=draw),
        get_io=Mock(return_value=SimpleNamespace(mouse_pos=SimpleNamespace(y=260))),
    )
    monkeypatch.setattr(panel_module, "imgui", fake)
    monkeypatch.setattr(panel_module, "active_gml_layout", lambda: SimpleNamespace(window_position=(100, 200)))
    ui = FakeUI(clicked={"unit_list.scrollbar"}, rects={
        "frmInner/frmList/scrList": SimpleNamespace(x=5, y=10, width=12, height=100),
    })
    panel = UnitListPanel()

    panel._render_scrollbar(ui, 20)

    assert panel._first_visible_row == 10
    assert len([call for call in draw.add_rect_filled.call_args_list]) == 2
    hit = next(call for call in ui.calls if call[0] == "hitbox")
    assert hit[3]["enabled"] is True


def test_scrollbar_handles_missing_layout_and_disabled_track(monkeypatch):
    panel = UnitListPanel()
    ui = FakeUI(rects={"frmInner/frmList/scrList": SimpleNamespace(x=0, y=0, width=10, height=8)})
    monkeypatch.setattr(panel_module, "active_gml_layout", lambda: None)
    panel._render_scrollbar(ui, 0)
    assert ui.calls == []

    monkeypatch.setattr(panel_module, "active_gml_layout", lambda: SimpleNamespace(window_position=(0, 0)))
    fake = fake_imgui(get_window_draw_list=Mock(return_value=Mock()))
    monkeypatch.setattr(panel_module, "imgui", fake)
    panel._render_scrollbar(ui, 0)
    assert ui.calls[0][3]["enabled"] is False


@pytest.mark.parametrize(
    ("own", "filter_type", "expected"),
    [
        (True, "Infantry", "No units match this filter."),
        (True, "All", "No deployed units are tracked for this country."),
        (False, "All", "No authorized aggregate force estimate is available."),
    ],
)
def test_empty_roster_explains_why_no_rows_are_shown(own, filter_type, expected):
    panel = UnitListPanel()
    panel._filter_type = filter_type
    ui = FakeUI()

    panel._render_rows([], own, ui)

    assert ui.calls[0][0] == "text_at"
    assert ui.calls[0][1][1] == expected


def test_render_rows_draws_foreign_data_without_selection_controls():
    panel = UnitListPanel()
    ui = FakeUI()

    panel._render_rows([entry(unit_id="")], False, ui)

    assert len([call for call in ui.calls if call[0] == "text"]) == 7
    assert not any(call[0] == "hitbox" for call in ui.calls)


def test_row_click_selects_and_double_click_opens_design(monkeypatch):
    fake = fake_imgui(is_mouse_double_clicked=Mock(return_value=True))
    monkeypatch.setattr(panel_module, "imgui", fake)
    panel = UnitListPanel(open_design_cb=Mock())
    ui = FakeUI(clicked={"unit_list.view_design.U1"})

    panel._render_rows([entry()], True, ui)

    assert panel._selected_unit_ids == {"U1"}
    assert panel._open_design_cb.call_args.args == ("design-1",)
    assert panel._training_submission_selection is None


def test_control_click_toggles_existing_row_selection(monkeypatch):
    io = SimpleNamespace(key_ctrl=True, mouse_double_click_time=0.3)
    monkeypatch.setattr(panel_module, "imgui", fake_imgui(get_io=Mock(return_value=io)))
    panel = UnitListPanel()
    panel._selected_unit_ids = {"U1"}

    panel._render_rows([entry()], True, FakeUI(clicked={"unit_list.view_design.U1"}))

    assert panel._selected_unit_ids == set()


def test_control_click_adds_an_unselected_row(monkeypatch):
    io = SimpleNamespace(key_ctrl=True, mouse_double_click_time=0.3)
    monkeypatch.setattr(panel_module, "imgui", fake_imgui(get_io=Mock(return_value=io)))
    panel = UnitListPanel()
    panel._selected_unit_ids = {"U2"}

    panel._render_rows([entry()], True, FakeUI(clicked={"unit_list.view_design.U1"}))

    assert panel._selected_unit_ids == {"U1", "U2"}


def test_row_hitbox_stops_at_next_compressed_row(monkeypatch):
    monkeypatch.setattr(panel_module, "imgui", fake_imgui())
    frame = "frmInner/frmList/frmList/frm1"
    next_frame = "frmInner/frmList/frmList/frm2"
    ui = FakeUI(rects={
        frame: SimpleNamespace(x=0, y=10, width=100, height=16),
        next_frame: SimpleNamespace(x=0, y=24, width=100, height=16),
    })

    UnitListPanel()._render_rows([entry()], True, ui)

    row_hit = next(call for call in ui.calls if call[0] == "hitbox")
    assert row_hit[3]["height"] == 14


def test_row_selection_and_markers_use_layout_coordinates(monkeypatch):
    draw = Mock()
    fake = fake_imgui(get_window_draw_list=Mock(return_value=draw))
    monkeypatch.setattr(panel_module, "imgui", fake)
    monkeypatch.setattr(panel_module, "active_gml_layout", lambda: SimpleNamespace(window_position=(100, 200)))
    rect = SimpleNamespace(x=10, y=20, width=30, height=16)
    ui = FakeUI(rects={"row": rect, "marker": rect})

    UnitListPanel._draw_row_selection(ui, "row")
    UnitListPanel._draw_row_marker(ui, "marker", (1, 0, 0, 1))
    UnitListPanel._draw_row_marker(ui, "missing", None)

    assert draw.add_rect_filled.call_count == 2


def test_render_entry_draws_sale_marker():
    panel = UnitListPanel()
    ui = FakeUI()

    panel._render_entry(entry(for_sale=True), 1, False, ui)

    assert len([call for call in ui.calls if call[0] == "text"]) == 7


def test_status_and_format_helpers_cover_fallbacks():
    assert _format_quantity(1234567) == "1 234 567"
    assert _source_position("", "t=2") == "No source · t=2"
    assert _source_position("usa", "t=2") == "usa · t=2"
    assert _format_intelligence_context("", "none", 2, "bad", None, ["ignored"]).startswith("No intelligence source")
    assert _format_intelligence_context("USA", "owned", 2, 0.5, 0.2, {}).endswith(".")
    assert _status_kind("blocked") == "warning"
    assert _status_kind("in transit") == "info"
    assert _status_kind("fortified") == "success"
    assert _status_kind("unknown") == "muted"
    assert _status_color("unknown") == panel_module.GAMETHEME.colors.text_main


def test_training_action_opens_confirmation_and_marks_accepted_selection(monkeypatch):
    monkeypatch.setattr(panel_module, "training_offer", lambda state, unit_id, country: {"unit_id": unit_id})
    train = Mock()
    panel = UnitListPanel(open_train_cb=train)
    panel._presenter = Mock()
    panel._presenter.marketable_units_for_country.return_value = []
    panel._selected_unit_ids = {"U1"}
    client = FakeClient()
    state = object()
    ui = FakeUI(clicked={"unit_list.train"})

    panel._render_actions(state, PanelRenderContext(target_tag="USA", is_own_country=True, net_client=client), [entry()], "USA", ui)

    train.assert_called_once()
    assert train.call_args.args[:2] == (state, ["U1"])
    train.call_args.kwargs["on_accept"]()
    assert panel._training_submission_selection == frozenset({"U1"})
    train_button = next(call for call in ui.calls if call[0] == "button" and call[3] == "unit_list.train")
    assert train_button[4]["enabled"] is True
    assert train_button[4]["tooltip"] == "Open a confirmation for 1 selected unit(s)."


def test_sell_action_sends_listing_action_and_clears_selection(monkeypatch):
    monkeypatch.setattr(panel_module, "training_offer", lambda state, unit_id, country: None)
    panel = UnitListPanel()
    panel._presenter = Mock()
    panel._presenter.marketable_units_for_country.return_value = [{"id": "U1"}]
    panel._selected_unit_ids = {"U1"}
    client = FakeClient()
    ui = FakeUI(clicked={"unit_list.sell"})

    panel._render_actions(object(), PanelRenderContext(target_tag="USA", is_own_country=True, net_client=client), [entry()], "USA", ui)

    assert len(client.actions) == 1
    assert isinstance(client.actions[0], ActionListUsedUnit)
    assert client.actions[0].country_tag == "USA"
    assert client.actions[0].unit_id == "U1"
    assert panel._selected_unit_ids == set()
    sell_button = next(call for call in ui.calls if call[0] == "button" and call[3] == "unit_list.sell")
    assert sell_button[4]["tooltip"] == "Selected units will be listed at 75% of design cost."


def test_disband_action_sends_selected_ids_and_clears_selection(monkeypatch):
    monkeypatch.setattr(panel_module, "training_offer", lambda state, unit_id, country: None)
    panel = UnitListPanel()
    panel._presenter = Mock()
    panel._presenter.marketable_units_for_country.return_value = []
    panel._selected_unit_ids = {"U2", "U1"}
    client = FakeClient()
    rows = [entry("U1"), entry("U2")]
    ui = FakeUI(clicked={"unit_list.disband"})

    panel._render_actions(object(), PanelRenderContext(target_tag="USA", is_own_country=True, net_client=client), rows, "USA", ui)

    assert len(client.actions) == 1
    assert isinstance(client.actions[0], ActionDisbandUnits)
    assert client.actions[0].unit_ids == ["U1", "U2"]
    assert panel._selected_unit_ids == set()


def test_submitted_training_selection_disables_repeat_actions(monkeypatch):
    monkeypatch.setattr(panel_module, "training_offer", lambda state, unit_id, country: {"unit_id": unit_id})
    panel = UnitListPanel(open_train_cb=Mock())
    panel._presenter = Mock()
    panel._presenter.marketable_units_for_country.return_value = [{"id": "U1"}]
    panel._selected_unit_ids = {"U1"}
    panel._training_submission_selection = frozenset({"U1"})
    ui = FakeUI()

    panel._render_actions(object(), PanelRenderContext(target_tag="USA", is_own_country=True, net_client=FakeClient()), [entry()], "USA", ui)

    for test_id in ("unit_list.sell", "unit_list.train"):
        button = next(call for call in ui.calls if call[0] == "button" and call[3] == test_id)
        assert button[4]["enabled"] is False
        assert button[4]["tooltip"].startswith("Wait for updated unit data")


def test_unavailable_training_explains_gameplay_reason(monkeypatch):
    monkeypatch.setattr(panel_module, "training_offer", lambda state, unit_id, country: None)
    monkeypatch.setattr(panel_module, "training_unavailable_reason", lambda state, unit_id, country: f"{unit_id} cannot train")
    panel = UnitListPanel(open_train_cb=Mock())
    panel._presenter = Mock()
    panel._presenter.marketable_units_for_country.return_value = []
    panel._selected_unit_ids = {"U1"}
    ui = FakeUI()

    panel._render_actions(object(), PanelRenderContext(target_tag="USA", is_own_country=True, net_client=FakeClient()), [entry()], "USA", ui)

    button = next(call for call in ui.calls if call[0] == "button" and call[3] == "unit_list.train")
    assert button[4]["enabled"] is False
    assert button[4]["tooltip"] == "U1 cannot train"


def test_action_tooltips_cover_empty_selection_and_missing_network_client(monkeypatch):
    monkeypatch.setattr(panel_module, "training_offer", lambda state, unit_id, country: {"unit_id": unit_id})
    panel = UnitListPanel()
    panel._presenter = Mock()
    panel._presenter.marketable_units_for_country.return_value = []
    ui = FakeUI()

    panel._render_actions(object(), PanelRenderContext(target_tag="USA", is_own_country=True), [entry()], "USA", ui)

    train = next(call for call in ui.calls if call[0] == "button" and call[3] == "unit_list.train")
    disband = next(call for call in ui.calls if call[0] == "button" and call[3] == "unit_list.disband")
    assert train[4]["tooltip"] == "Select one or more units first."
    assert disband[4]["tooltip"] == "Select one or more owned units first."

    panel._selected_unit_ids = {"U1"}
    ui = FakeUI()
    panel._render_actions(object(), PanelRenderContext(target_tag="USA", is_own_country=True), [entry()], "USA", ui)
    train = next(call for call in ui.calls if call[0] == "button" and call[3] == "unit_list.train")
    assert train[4]["tooltip"] == "Training confirmation is unavailable."
