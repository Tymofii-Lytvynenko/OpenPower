from contextlib import contextmanager, nullcontext
from types import SimpleNamespace

import pytest

from src.client.ui.panels.military import unit_reserves_panel
from src.client.ui.panels.military.unit_reserves_panel import UnitReservesPanel, _capital_region_id
from src.shared.actions import ActionDispatchUnitDeployment


class Table:
    def __init__(self, rows):
        self.rows = rows

    def is_empty(self):
        return not self.rows

    def to_dicts(self):
        return self.rows


class DrawList:
    def __init__(self):
        self.filled_rectangles = []

    def add_rect_filled(self, minimum, maximum, color):
        self.filled_rectangles.append((minimum, maximum, color))


class Imgui:
    MouseButton_ = SimpleNamespace(left=0)
    Col_ = SimpleNamespace(button=0)
    StyleVar_ = SimpleNamespace(item_spacing=0)

    def __init__(self, *, clicked=False, hovered=False, active=False, dragging=False, key_shift=False, key_ctrl=False):
        self.clicked = clicked
        self.hovered = hovered
        self.active = active
        self.dragging = dragging
        self.io = SimpleNamespace(key_shift=key_shift, key_ctrl=key_ctrl)
        self.draw_list = DrawList()
        self.positions = []
        self.tooltips = []
        self.disabled_text = []
        self.style_colors = []
        self.style_vars = []

    @staticmethod
    def get_cursor_screen_pos():
        return SimpleNamespace(x=40.0, y=50.0)

    def get_window_draw_list(self):
        return self.draw_list

    @staticmethod
    def get_color_u32(color):
        return color

    def set_cursor_screen_pos(self, position):
        self.positions.append(position)

    def invisible_button(self, label, size, *, test_id):
        return self.clicked

    def is_item_hovered(self):
        return self.hovered

    def set_tooltip(self, value):
        self.tooltips.append(value)

    def text_disabled(self, value, **kwargs):
        self.disabled_text.append((value, kwargs))

    def push_style_color(self, slot, color):
        self.style_colors.append((slot, color))

    def pop_style_color(self):
        self.style_colors.pop()

    def push_style_var(self, slot, value):
        self.style_vars.append((slot, value))

    def pop_style_var(self):
        self.style_vars.pop()

    def get_io(self):
        return self.io

    def is_item_active(self):
        return self.active

    def is_mouse_dragging(self, button):
        return self.dragging


class RowUI:
    def __init__(self):
        self.calls = []

    def text(self, *args, **kwargs):
        self.calls.append(("text", args, kwargs))

    def meter(self, *args, **kwargs):
        self.calls.append(("meter", args, kwargs))

    def text_at(self, *args, **kwargs):
        self.calls.append(("text_at", args, kwargs))


class Ui:
    def __init__(self, *, clicked=(), clicked_at=()):
        self.clicked = set(clicked)
        self.clicked_at = set(clicked_at)
        self.buttons = []
        self.buttons_at = []
        self.frames = []
        self.texts = []

    def frame(self, slot):
        self.frames.append(slot)

    def text(self, *args, **kwargs):
        self.texts.append((args, kwargs))

    def button(self, slot, label, test_id, **kwargs):
        self.buttons.append((slot, label, test_id, kwargs))
        return test_id in self.clicked

    @staticmethod
    def path(slot):
        return slot

    def button_at(self, slot, label, test_id, **kwargs):
        self.buttons_at.append((slot, label, test_id, kwargs))
        return test_id in self.clicked_at


class Client:
    player_id = "player-1"

    def __init__(self):
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)


def install_imgui(monkeypatch, **kwargs):
    fake = Imgui(**kwargs)
    monkeypatch.setattr(unit_reserves_panel, "imgui", fake)
    monkeypatch.setattr(
        unit_reserves_panel.UIPrimitives,
        "fit_text",
        staticmethod(lambda value, width: value),
    )
    return fake


def install_render_harness(monkeypatch, *, opened=True, ui=None, session=None, child_open=True):
    ui = ui or Ui()
    monkeypatch.setattr(
        unit_reserves_panel,
        "WindowManager",
        SimpleNamespace(window=lambda *args, **kwargs: nullcontext(opened)),
    )
    monkeypatch.setattr(unit_reserves_panel, "GMLWidgets", lambda _root: ui)
    monkeypatch.setattr(unit_reserves_panel, "active_gml_layout", lambda: session)
    monkeypatch.setattr(
        unit_reserves_panel,
        "gml_child_frame",
        lambda *args, **kwargs: nullcontext(child_open),
    )
    return ui


def test_quantity_slots_and_group_categorization_cover_all_domains():
    assert UnitReservesPanel._quantity_slots() == (
        "frmInner/txtQty",
        "frmInner/txtQty1",
        "frmInner/txtQty2",
        "frmInner/txtQty3",
    )
    rows = [
        {"unit_id": "g", "unit_type": "tank"},
        {"unit_id": "a", "unit_domain": "AIR"},
        {"unit_id": "n", "unit_type": "submarine"},
        {"unit_id": "s", "unit_type": "nuclear_bomber"},
    ]

    assert [[row["unit_id"] for row in bucket] for bucket in UnitReservesPanel._categorize(rows)] == [
        ["g"], ["a"], ["n"], ["s"],
    ]


def test_capital_lookup_handles_absence_invalid_data_and_normalized_country():
    assert _capital_region_id(SimpleNamespace(tables={}), "USA") is None
    assert _capital_region_id(SimpleNamespace(tables={"country_governments": Table([])}), "USA") is None
    assert _capital_region_id(SimpleNamespace(tables={
        "country_governments": Table([{"country_id": "CAN", "capital_region_id": 8}]),
    }), "USA") is None
    assert _capital_region_id(SimpleNamespace(tables={
        "country_governments": Table([{"country_id": " usa ", "capital_region_id": "13"}]),
    }), "USA") == 13
    assert _capital_region_id(SimpleNamespace(tables={
        "country_governments": Table([{"country_id": "USA", "capital_region_id": "bad"}]),
    }), "USA") is None
    assert _capital_region_id(SimpleNamespace(tables={
        "country_governments": Table([{"country_id": "USA", "capital_region_id": 0}]),
    }), "USA") is None


def test_selection_supports_plain_toggle_and_shift_ranges(monkeypatch):
    fake = install_imgui(monkeypatch, key_ctrl=True)
    panel = UnitReservesPanel()
    visible = ["A", "B", "C", "D"]

    panel._selected_unit_ids = {"A"}
    panel._selection_anchor_unit_id = "A"
    panel._update_selection("C", visible)
    assert panel._selected_unit_ids == {"A", "C"}
    assert panel._selection_anchor_unit_id == "C"

    panel._update_selection("C", visible)
    assert panel._selected_unit_ids == {"A"}

    fake.io.key_ctrl = False
    fake.io.key_shift = True
    panel._selection_anchor_unit_id = "A"
    panel._update_selection("C", visible)
    assert panel._selected_unit_ids == {"A", "B", "C"}

    fake.io.key_shift = False
    panel._update_selection("D", visible)
    assert panel._selected_unit_ids == {"D"}
    assert panel._selection_anchor_unit_id == "D"


def test_category_counts_write_all_four_count_labels():
    ui = Ui()
    groups = ([{"id": 1}], [], [{"id": 2}, {"id": 3}], [])

    UnitReservesPanel()._render_category_counts(groups, ui)

    assert len(ui.frames) == 4
    assert [entry[0][1] for entry in ui.texts] == [1, 0, 2, 0]
    assert [entry[1]["test_id"] for entry in ui.texts] == [
        "unit_reserves.count.ground",
        "unit_reserves.count.air",
        "unit_reserves.count.naval",
        "unit_reserves.count.strategic",
    ]


def test_group_row_renders_training_status_and_suppresses_drag(monkeypatch):
    fake = install_imgui(monkeypatch, clicked=True, hovered=True, active=True, dragging=True)
    row_ui = RowUI()

    @contextmanager
    def gml_row(template, row_id):
        yield row_ui

    monkeypatch.setattr(unit_reserves_panel, "gml_row", gml_row)
    dragged = []
    panel = UnitReservesPanel()
    groups = [
        {"unit_id": "U1", "unit_type": "fighter", "quantity": 2500, "design_name": "Falcon", "lifecycle": "training", "training_progress": 0.4},
        {"unit_id": "U2", "unit_type": "tank", "quantity": 1},
    ]

    panel._render_group_row(
        groups[0],
        groups,
        SimpleNamespace(on_deployment_drag_start=dragged.append),
    )

    assert any(call[0] == "text" and call[1][1] == "2 500 Falcon" for call in row_ui.calls)
    assert any(call[0] == "meter" and call[1] == ("frmProgress", 0.4, unit_reserves_panel.GAMETHEME.colors.positive) for call in row_ui.calls)
    assert any(call[0] == "text_at" and call[1][1] == "Training 40%" for call in row_ui.calls)
    assert fake.tooltips == ["2 500 Falcon · Training 40%"]
    assert dragged == []
    assert fake.positions[-1] == (40.0, 68.0)


def test_group_row_starts_drag_for_selected_non_training_group(monkeypatch):
    install_imgui(monkeypatch, clicked=True, active=True, dragging=True)
    row_ui = RowUI()

    @contextmanager
    def gml_row(template, row_id):
        yield row_ui

    monkeypatch.setattr(unit_reserves_panel, "gml_row", gml_row)
    panel = UnitReservesPanel()
    dragged = []
    row = {"unit_id": "U1", "unit_type": "tank", "lifecycle": "ready"}

    panel._render_group_row(
        row,
        [row],
        SimpleNamespace(on_deployment_drag_start=dragged.append),
    )

    assert dragged == [["U1"]]


def test_group_row_skips_missing_id_and_marks_selected_rows(monkeypatch):
    fake = install_imgui(monkeypatch)
    panel = UnitReservesPanel()
    panel._selected_unit_ids = {"U1"}
    visible = [{"unit_id": "U1", "unit_type": "infantry", "quantity": -4, "training_level": "Veteran", "status": "ready_to_deploy"}]
    row_ui = RowUI()

    @contextmanager
    def gml_row(template, row_id):
        yield row_ui

    monkeypatch.setattr(unit_reserves_panel, "gml_row", gml_row)
    panel._render_group_row({}, visible, SimpleNamespace(on_deployment_drag_start=None))
    assert not row_ui.calls

    panel._render_group_row(visible[0], visible, SimpleNamespace(on_deployment_drag_start=None))
    assert fake.draw_list.filled_rectangles
    assert any(call[0] == "meter" and call[1][1] == 1.0 for call in row_ui.calls)
    assert any(call[0] == "text_at" and call[1][1] == "Ready To Deploy" for call in row_ui.calls)


def test_render_actions_dispatches_ready_group_and_clears_successful_training_selection(monkeypatch):
    fake = install_imgui(monkeypatch)
    monkeypatch.setattr(
        unit_reserves_panel,
        "training_offer",
        lambda state, unit_id, country: {"unit_id": unit_id} if unit_id == "U1" else None,
    )
    panel = UnitReservesPanel(open_train_cb=lambda state, ids: True)
    panel._selected_unit_ids = {"U1", "U2"}
    client = Client()
    ui = Ui(clicked={"unit_reserves.deploy_capital", "unit_reserves.train"})
    state = SimpleNamespace(tables={
        "country_governments": Table([{"country_id": "USA", "capital_region_id": 5}]),
    })
    groups = [
        {"unit_id": "U1", "lifecycle": "ready"},
        {"unit_id": "U2", "lifecycle": "training"},
    ]

    panel._render_actions(
        state,
        "USA",
        groups,
        ui,
        SimpleNamespace(net_client=client),
    )

    assert len(client.actions) == 1
    assert isinstance(client.actions[0], ActionDispatchUnitDeployment)
    assert client.actions[0].unit_id == "U1"
    assert panel._selected_unit_ids == {"U2"}
    assert ui.buttons[0][3]["enabled"] is True
    assert ui.buttons[0][3]["tooltip"] == "Dispatch selected groups to your capital."
    assert ui.buttons[1][3]["enabled"] is True
    assert fake.tooltips == []


@pytest.mark.parametrize(
    ("active_category", "capital", "selected", "expected_tooltip"),
    [
        (3, 9, {"U1"}, "REFERENCE disables capital deployment for strategic missile groups."),
        (0, None, {"U1"}, "The current country snapshot does not identify a capital region."),
        (0, 9, set(), "Select one or more groups first."),
        (0, 9, {"U1"}, "Groups in training cannot be dispatched."),
    ],
)
def test_deployment_action_tooltip_explains_disabled_state(monkeypatch, active_category, capital, selected, expected_tooltip):
    install_imgui(monkeypatch)
    panel = UnitReservesPanel()
    panel._active_category = active_category
    panel._selected_unit_ids = set(selected)
    government_rows = [] if capital is None else [{"country_id": "USA", "capital_region_id": capital}]
    state = SimpleNamespace(tables={"country_governments": Table(government_rows)})
    groups = [{"unit_id": "U1", "lifecycle": "training"}]
    ui = Ui()

    panel._render_actions(state, "USA", groups, ui, SimpleNamespace(net_client=Client()))

    assert ui.buttons[0][3]["enabled"] is False
    assert ui.buttons[0][3]["tooltip"] == expected_tooltip


def test_render_handles_closed_and_restricted_windows(monkeypatch):
    ui = install_render_harness(monkeypatch, opened=False)
    panel = UnitReservesPanel()
    assert panel.render(SimpleNamespace(), SimpleNamespace(is_own_country=True)) is False
    assert ui.frames == []

    install_render_harness(monkeypatch, opened=True, ui=ui)
    assert panel.render(SimpleNamespace(), SimpleNamespace(is_own_country=False)) is True
    assert ui.texts[0][1]["test_id"] == "unit_reserves.restricted"
    assert [entry[0][1] for entry in ui.texts[1:]] == ["—"] * 4


def test_render_own_country_uses_selected_category_and_panel_sections(monkeypatch):
    session = SimpleNamespace(apply_tab_page_runtime_geometry=lambda path: None)
    ui = install_render_harness(monkeypatch, opened=True, session=session, child_open=False)
    panel = UnitReservesPanel()
    panel._active_category = 1
    panel._selected_unit_ids = {"AIR-1"}
    panel._presenter = SimpleNamespace(
        reserve_units_for_country=lambda state, country: [
            {"unit_id": "GROUND-1", "unit_type": "infantry"},
            {"unit_id": "AIR-1", "unit_domain": "air"},
        ]
    )
    action_calls = []
    monkeypatch.setattr(panel, "_render_actions", lambda *args: action_calls.append(args))

    assert panel.render(
        SimpleNamespace(),
        SimpleNamespace(is_own_country=True, target_tag=" usa ", net_client=None),
    ) is True

    assert "1 group(s) selected" in ui.texts[0][0][1]
    assert [entry[0][1] for entry in ui.texts[1:]] == [1, 1, 0, 0]
    assert len(action_calls) == 1
    assert action_calls[0][1:3] == ("USA", [{"unit_id": "AIR-1", "unit_domain": "air"}])


def test_category_tabs_skip_missing_rectangles_and_clear_selection_on_change(monkeypatch):
    install_imgui(monkeypatch)
    panel = UnitReservesPanel()
    panel._selected_unit_ids = {"U1"}
    panel._selection_anchor_unit_id = "U1"
    rect = lambda x, y, width=30.0, height=18.0: SimpleNamespace(x=x, y=y, width=width, height=height)

    class Session:
        def apply_tab_page_runtime_geometry(self, path):
            assert path == "frmInner/tabGroups"
            return object()

        @staticmethod
        def rect_for(path):
            assert path == "frmInner/tabGroups"
            return rect(10.0, 20.0)

        @staticmethod
        def tab_button_rect(path, index):
            if index == 1:
                return None
            return rect(10.0 + index * 32.0, 20.0)

    ui = Ui(clicked_at={"unit_reserves.category.naval"})
    monkeypatch.setattr(unit_reserves_panel, "active_gml_layout", lambda: Session())

    panel._render_category_tabs(([], [], [{"unit_id": "N1"}], []), ui)

    assert len(ui.buttons_at) == 3
    assert ui.buttons_at[0][3]["offset"] == (0.0, 0.0)
    assert panel._active_category == 2
    assert panel._selected_unit_ids == set()
    assert panel._selection_anchor_unit_id is None


def test_group_list_handles_closed_empty_and_populated_frames(monkeypatch):
    fake = install_imgui(monkeypatch)
    panel = UnitReservesPanel()
    context = SimpleNamespace(on_deployment_drag_start=None)
    ui = Ui()

    install_render_harness(monkeypatch, child_open=False, ui=ui)
    panel._render_group_list([], ui, context)
    assert fake.disabled_text == []

    install_render_harness(monkeypatch, child_open=True, ui=ui)
    panel._render_group_list([], ui, context)
    assert "No ground groups" in fake.disabled_text[-1][0]

    row_ui = RowUI()

    @contextmanager
    def gml_row(template, row_id):
        yield row_ui

    monkeypatch.setattr(unit_reserves_panel, "gml_row", gml_row)
    panel._render_group_list([{"unit_id": "U1", "unit_type": "tank"}], ui, context)
    assert any(call[0] == "text" for call in row_ui.calls)
    assert fake.style_vars == []
