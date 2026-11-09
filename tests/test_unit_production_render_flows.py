from contextlib import contextmanager
from types import SimpleNamespace

from src.client.ui.panels.military import unit_production_panel
from src.client.ui.panels.military.unit_production_panel import UnitProductionPanel
from src.shared.actions import (
    ActionCancelForeignUnitOrder,
    ActionDispatchUnitDeployment,
    ActionRespondForeignUnitOrder,
    ActionSetProductionPriority,
    ActionSetProductionPaused,
)


class DrawList:
    def __init__(self):
        self.rectangles = []

    def add_rect_filled(self, start, end, color):
        self.rectangles.append((start, end, color))


class Imgui:
    def __init__(self, *, changed=False, selected_index=0, hovered=False, clicked=()):
        self.changed = changed
        self.selected_index = selected_index
        self.hovered = hovered
        self.clicked = set(clicked)
        self.draw_list = DrawList()
        self.disabled = []
        self.combo_calls = []
        self.buttons = []
        self.tooltips = []
        self.texts = []
        self.separators = 0
        self.same_lines = 0

    @staticmethod
    def get_cursor_screen_pos():
        return SimpleNamespace(x=10.0, y=20.0)

    def get_window_draw_list(self):
        return self.draw_list

    @staticmethod
    def get_color_u32(color):
        return color

    def begin_disabled(self, disabled):
        self.disabled.append(disabled)

    def end_disabled(self):
        pass

    def combo(self, label, selected, options, *, test_id, gml_id):
        self.combo_calls.append((label, selected, options, test_id, gml_id))
        return self.changed, self.selected_index

    def is_item_hovered(self):
        return self.hovered

    def set_tooltip(self, value):
        self.tooltips.append(value)

    def text(self, value):
        self.texts.append(value)

    def text_disabled(self, value, **kwargs):
        self.texts.append(value)

    def text_colored(self, color, value):
        self.texts.append(value)

    def button(self, label, size, *, test_id):
        self.buttons.append((label, size, test_id))
        return test_id in self.clicked

    def same_line(self):
        self.same_lines += 1

    def separator(self):
        self.separators += 1


class RowUI:
    def __init__(self):
        self.calls = []

    def text_at(self, *args, **kwargs):
        self.calls.append(("text_at", args, kwargs))

    def text(self, *args, **kwargs):
        self.calls.append(("text", args, kwargs))

    def meter(self, *args, **kwargs):
        self.calls.append(("meter", args, kwargs))

    @staticmethod
    def path(slot):
        return f"row/{slot}"


class Client:
    player_id = "player-1"

    def __init__(self):
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)


def install_imgui(monkeypatch, **kwargs):
    fake = Imgui(**kwargs)
    monkeypatch.setattr(unit_production_panel, "imgui", fake)
    monkeypatch.setattr(
        unit_production_panel.UIPrimitives,
        "fit_text",
        staticmethod(lambda value, width: value),
    )
    return fake


def test_production_row_renders_clamped_values_and_applies_priority_choice(monkeypatch):
    fake = install_imgui(monkeypatch, changed=True, selected_index=0, hovered=True)
    row_ui = RowUI()
    row_scope = []

    @contextmanager
    def gml_row(template, row_id, *, width):
        row_scope.append((template, row_id, width))
        yield row_ui

    monkeypatch.setattr(unit_production_panel, "gml_row", gml_row)
    panel = UnitProductionPanel()
    panel._queue_priority_overrides["Q1"] = 75
    client = Client()
    context = SimpleNamespace(is_own_country=True, net_client=client)

    panel._render_production_row(
        {
            "id": "Q1",
            "quantity": -3,
            "progress": 1.5,
            "status": "paused",
            "country_id": "canada",
            "eta_days": 0,
            "blocking_reason": "awaiting resources",
        },
        {"display_name": "Interceptor", "class_name": "fighter"},
        {"CANADA": "CAN"},
        "USA",
        context,
        700.0,
    )

    assert row_scope == [("lstUnitProductionItem", "Q1", 522.0)]
    assert fake.draw_list.rectangles[0][:2] == ((10.0, 20.0), (532.0, 38.0))
    assert any(call[0] == "meter" and call[1] == ("frmProgress", 1.0, unit_production_panel.GAMETHEME.colors.positive) for call in row_ui.calls)
    assert any(call[0] == "text" and call[1][1] == "×0" for call in row_ui.calls)
    assert any(call[0] == "text_at" and call[1][1] == "N/A" for call in row_ui.calls)
    assert fake.combo_calls[0][1] == 3
    assert fake.tooltips == ["awaiting resources"]
    assert isinstance(client.actions[-2], ActionSetProductionPaused)
    assert client.actions[-2].is_paused is False
    assert isinstance(client.actions[-1], ActionSetProductionPriority)
    assert client.actions[-1].priority == 100


def test_production_row_uses_fallback_design_and_disables_completed_order(monkeypatch):
    fake = install_imgui(monkeypatch)
    row_ui = RowUI()

    @contextmanager
    def gml_row(template, row_id, *, width):
        yield row_ui

    monkeypatch.setattr(unit_production_panel, "gml_row", gml_row)
    panel = UnitProductionPanel()
    context = SimpleNamespace(is_own_country=True, net_client=Client())

    panel._render_production_row(
        {"id": "Q2", "design_id": "unknown-design", "quantity": 4, "progress": -1, "status": "complete", "eta_days": 8},
        {},
        {},
        "USA",
        context,
        None,
    )

    assert fake.draw_list.rectangles[0][1] == (532.0, 38.0)
    assert any(call[0] == "text_at" and call[1][1] == "G" for call in row_ui.calls)
    assert any(call[0] == "text_at" and call[1][1] == "8d" for call in row_ui.calls)
    assert any(call[0] == "meter" and call[1] == ("frmProgress", 0.0, unit_production_panel.GAMETHEME.colors.positive) for call in row_ui.calls)
    assert fake.disabled == [True]


def test_foreign_contract_accepts_and_cancels_a_pending_contract(monkeypatch):
    fake = install_imgui(monkeypatch, clicked={
        "unit_production.foreign.accept.C1",
        "unit_production.foreign.cancel.C1",
    })
    panel = UnitProductionPanel()
    client = Client()

    panel._render_foreign_contract(
        {
            "id": "C1",
            "buyer_country_id": "usa",
            "seller_country_id": "usa",
            "design_name": "Transport",
            "quantity": 3,
            "status": "pending_seller_acceptance",
            "price": 125.0,
        },
        "USA",
        SimpleNamespace(is_own_country=True, net_client=client),
    )

    assert [button[2] for button in fake.buttons] == [
        "unit_production.foreign.accept.C1",
        "unit_production.foreign.reject.C1",
        "unit_production.foreign.cancel.C1",
    ]
    assert isinstance(client.actions[0], ActionRespondForeignUnitOrder)
    assert client.actions[0].accept is True
    assert isinstance(client.actions[1], ActionCancelForeignUnitOrder)


def test_foreign_contract_viewer_without_control_does_not_render_actions(monkeypatch):
    fake = install_imgui(monkeypatch)
    panel = UnitProductionPanel()

    panel._render_foreign_contract(
        {"id": "C2", "status": "accepted"},
        "USA",
        SimpleNamespace(is_own_country=False, net_client=Client()),
    )

    assert fake.buttons == []


def test_deployment_orders_dispatch_and_split_selected_region(monkeypatch):
    fake = install_imgui(monkeypatch, clicked={
        "unit_production.deployments.dispatch.D1",
        "unit_production.deployments.split.D1",
    })
    panel = UnitProductionPanel()
    panel._presenter.deployment_orders_for_country = lambda state, tag: [{
        "id": "D1",
        "unit_id": "U1",
        "unit_type": "infantry",
        "quantity": 5,
        "status": "blocked",
        "origin_name": "Origin",
        "destination_name": "Frontier",
        "blocking_reason": "Waiting for transport",
    }]
    client = Client()

    panel._render_deployment_orders(
        object(),
        "USA",
        SimpleNamespace(
            is_own_country=True,
            net_client=client,
            selected_region_id=42,
        ),
    )

    assert [button[2] for button in fake.buttons] == [
        "unit_production.deployments.dispatch.D1",
        "unit_production.deployments.split.D1",
    ]
    assert all(isinstance(action, ActionDispatchUnitDeployment) for action in client.actions)
    assert len(client.actions) == 2
    assert fake.separators == 1


def test_empty_deployment_orders_show_empty_message(monkeypatch):
    fake = install_imgui(monkeypatch)
    panel = UnitProductionPanel()
    panel._presenter.deployment_orders_for_country = lambda state, tag: []

    panel._render_deployment_orders(
        object(),
        "USA",
        SimpleNamespace(is_own_country=True, net_client=Client(), selected_region_id=42),
    )

    assert fake.texts == ["Completed groups will appear here until dispatched."]
    assert fake.buttons == []
