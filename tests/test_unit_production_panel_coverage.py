from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.military import unit_production_panel as production_module
from src.client.ui.panels.military.unit_production_panel import UnitProductionPanel
from src.shared.actions import (
    ActionQueueUnitProduction,
    ActionRequestForeignUnitOrder,
    ActionSetForeignOrderAcceptance,
)
from tests.test_support.client_presentation import client_state


class FakeUI:
    def __init__(self, *, button_ids=(), toggle_values=None, hitbox_values=None, width=600.0):
        self.button_ids = set(button_ids)
        self.toggle_values = toggle_values or {}
        self.hitbox_values = hitbox_values or {}
        self.width = width
        self.calls = []

    def path(self, slot):
        return slot

    def rect(self, slot):
        self.calls.append(("rect", slot))
        return SimpleNamespace(width=self.width)

    def frame(self, slot):
        self.calls.append(("frame", slot))

    def text(self, *args, **kwargs):
        self.calls.append(("text", args, kwargs))

    def text_at(self, *args, **kwargs):
        self.calls.append(("text_at", args, kwargs))

    def meter(self, *args, **kwargs):
        self.calls.append(("meter", args, kwargs))

    def toggle(self, slot, selected, test_id, **kwargs):
        self.calls.append(("toggle", slot, selected, test_id, kwargs))
        return self.toggle_values.get(test_id, (False, selected))

    def hitbox_state(self, slot, test_id, **kwargs):
        return self.hitbox_values.get(test_id, (False, False))

    def button(self, slot, label, test_id, **kwargs):
        self.calls.append(("button", slot, label, test_id, kwargs))
        return test_id in self.button_ids

    def button_at(self, slot, label, test_id, **kwargs):
        self.calls.append(("button_at", slot, label, test_id, kwargs))
        return test_id in self.button_ids


class FakeImGui:
    StyleVar_ = SimpleNamespace(item_spacing="item_spacing")
    HoveredFlags_ = SimpleNamespace(allow_when_disabled="allow_when_disabled")
    TreeNodeFlags_ = SimpleNamespace(default_open="default_open")

    def __init__(self, *, combo_results=(), input_result=(False, ""), clicked=(), hovered=False,
                 tree_open=True, selectable_clicked=False):
        self.combo_results = list(combo_results)
        self.input_result = input_result
        self.clicked = set(clicked)
        self.hovered = hovered
        self.tree_open = tree_open
        self.selectable_clicked = selectable_clicked
        self.calls = []
        self.disabled = []

    def get_io(self):
        return SimpleNamespace(display_size=SimpleNamespace(x=1200.0, y=800.0))

    def get_main_viewport(self):
        return SimpleNamespace(size=SimpleNamespace(x=1200.0, y=800.0))

    def begin_disabled(self, disabled):
        self.disabled.append(disabled)

    def end_disabled(self):
        self.calls.append(("end_disabled",))

    def combo(self, *args, **kwargs):
        self.calls.append(("combo", args, kwargs))
        return self.combo_results.pop(0) if self.combo_results else (False, args[1])

    def input_text(self, *args, **kwargs):
        self.calls.append(("input_text", args, kwargs))
        return self.input_result

    def is_item_hovered(self, *args):
        return self.hovered

    def set_tooltip(self, value):
        self.calls.append(("tooltip", value))

    def get_time(self):
        return 10.0

    def push_style_var(self, *args):
        self.calls.append(("push_style_var", args))

    def pop_style_var(self):
        self.calls.append(("pop_style_var",))

    def tree_node_ex(self, *args, **kwargs):
        self.calls.append(("tree_node_ex", args, kwargs))
        return self.tree_open

    def selectable(self, *args, **kwargs):
        self.calls.append(("selectable", args, kwargs))
        return self.selectable_clicked, False

    def button(self, *args, **kwargs):
        self.calls.append(("button", args, kwargs))
        return kwargs.get("test_id") in self.clicked

    def same_line(self, *args):
        self.calls.append(("same_line", args))

    def tree_pop(self):
        self.calls.append(("tree_pop",))

    def text_disabled(self, *args, **kwargs):
        self.calls.append(("text_disabled", args, kwargs))

    def text(self, *args, **kwargs):
        self.calls.append(("text", args, kwargs))

    def text_colored(self, *args, **kwargs):
        self.calls.append(("text_colored", args, kwargs))

    def separator(self):
        self.calls.append(("separator",))

    def set_clipboard_text(self, value):
        self.calls.append(("clipboard", value))


class Client:
    player_id = "player-1"

    def __init__(self):
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)


def install_child_frame(monkeypatch, opened=True):
    @contextmanager
    def child_frame(*args, **kwargs):
        yield opened

    monkeypatch.setattr(production_module, "gml_child_frame", child_frame)


def test_render_composes_panel_sections_and_centers_window(monkeypatch):
    fake_imgui = FakeImGui()
    monkeypatch.setattr(production_module, "imgui", fake_imgui)
    ui = FakeUI(width=520.0)
    monkeypatch.setattr(production_module, "GMLWidgets", lambda _root: ui)
    window_calls = []

    @contextmanager
    def window(*args, **kwargs):
        window_calls.append((args, kwargs))
        yield True

    monkeypatch.setattr(production_module.WindowManager, "window", window)
    panel = UnitProductionPanel()
    panel._presenter = Mock()
    panel._presenter.designs_for_country.return_value = [{"id": "D1", "branch": "land"}]
    panel._presenter.foreign_designs_for_country.return_value = [{"country_id": "CAN", "id": "D2"}]
    panel._fit_right_pane_to_window = Mock()
    panel._draw_source_frames = Mock()
    panel._render_category_filters = Mock()
    panel._render_builder_selector = Mock()
    panel._render_design_tree = Mock(return_value={"id": "D1"})
    panel._render_design_details = Mock()
    panel._render_accept_foreign_toggle = Mock()
    panel._render_right_page = Mock()
    panel._selected_builder_country = "MEX"
    state = object()
    context = PanelRenderContext(target_tag=" usa ", is_own_country=True)

    assert panel.render(state, context) is True

    assert window_calls[0][1]["x"] == 179.0
    assert window_calls[0][1]["y"] == 169.0
    assert panel._presenter.designs_for_country.call_args.args == (state, "USA")
    assert panel._selected_builder_country == "USA"
    panel._fit_right_pane_to_window.assert_called_once_with(ui)
    panel._render_design_details.assert_called_once_with(state, {"id": "D1"}, "USA", ui, context)
    panel._render_right_page.assert_called_once_with(state, "USA", ui, context, 520.0)


def test_render_skips_widget_construction_when_window_is_closed(monkeypatch):
    monkeypatch.setattr(production_module, "imgui", FakeImGui())

    @contextmanager
    def window(*args, **kwargs):
        yield False

    monkeypatch.setattr(production_module.WindowManager, "window", window)
    widgets = Mock()
    monkeypatch.setattr(production_module, "GMLWidgets", widgets)
    panel = UnitProductionPanel()
    panel._presenter = Mock()
    panel._presenter.designs_for_country.return_value = []
    panel._presenter.foreign_designs_for_country.return_value = []

    assert panel.render(object(), PanelRenderContext(target_tag="USA", is_own_country=True)) is False
    widgets.assert_not_called()


def test_render_falls_back_to_main_viewport_when_io_size_is_empty(monkeypatch):
    fake_imgui = FakeImGui()
    fake_imgui.get_io = lambda: SimpleNamespace(display_size=SimpleNamespace(x=0.0, y=0.0))
    fake_imgui.get_main_viewport = lambda: SimpleNamespace(size=SimpleNamespace(x=1000.0, y=700.0))
    monkeypatch.setattr(production_module, "imgui", fake_imgui)
    monkeypatch.setattr(production_module, "GMLWidgets", lambda _root: FakeUI())
    window = []

    @contextmanager
    def open_window(*args, **kwargs):
        window.append(kwargs)
        yield True

    monkeypatch.setattr(production_module.WindowManager, "window", open_window)
    panel = UnitProductionPanel()
    panel._presenter = Mock()
    panel._presenter.designs_for_country.return_value = []
    panel._presenter.foreign_designs_for_country.return_value = []
    for name in (
        "_fit_right_pane_to_window", "_draw_source_frames", "_render_category_filters",
        "_render_builder_selector", "_render_design_details", "_render_accept_foreign_toggle",
        "_render_right_page",
    ):
        setattr(panel, name, Mock())
    panel._render_design_tree = Mock(return_value=None)

    assert panel.render(object(), PanelRenderContext(target_tag="USA", is_own_country=True)) is True
    assert window[0]["x"] == 79.0
    assert window[0]["y"] == 119.0


def test_right_pane_fit_scales_only_when_available_width_is_smaller(monkeypatch):
    ui = FakeUI()
    session = SimpleNamespace(
        window_size=(700.0, 500.0),
        rect_for=Mock(return_value=SimpleNamespace(x=300.0, width=500.0)),
        scale_subtree_x=Mock(),
    )
    monkeypatch.setattr(production_module, "active_gml_layout", lambda: session)

    UnitProductionPanel._fit_right_pane_to_window(ui)

    session.scale_subtree_x.assert_called_once_with("frmRight", 0.8)
    session.window_size = (900.0, 500.0)
    UnitProductionPanel._fit_right_pane_to_window(ui)
    assert session.scale_subtree_x.call_count == 1
    monkeypatch.setattr(production_module, "active_gml_layout", lambda: None)
    UnitProductionPanel._fit_right_pane_to_window(ui)
    assert session.scale_subtree_x.call_count == 1


def test_source_frames_and_category_selection_are_applied():
    ui = FakeUI()
    UnitProductionPanel._draw_source_frames(ui)
    assert len([call for call in ui.calls if call[0] == "frame"]) == 12

    panel = UnitProductionPanel()
    panel._selected_design_id = "D1"
    ui = FakeUI(toggle_values={"unit_production.category.air": (True, False)})

    panel._render_category_filters(ui)

    assert panel._category == "air"
    assert panel._selected_design_id == ""
    assert len([call for call in ui.calls if call[0] == "toggle"]) == 4


def test_builder_selector_changes_country_and_resets_design(monkeypatch):
    fake_imgui = FakeImGui(combo_results=[(True, 1)])
    monkeypatch.setattr(production_module, "imgui", fake_imgui)
    panel = UnitProductionPanel()
    panel._selected_builder_country = "USA"
    panel._selected_design_id = "D1"
    ui = FakeUI()
    game = SimpleNamespace(tables={"countries": None})

    panel._render_builder_selector(
        game,
        "USA",
        ["USA", "CAN"],
        [],
        ui,
        PanelRenderContext(target_tag="USA", is_own_country=True),
    )

    assert panel._selected_builder_country == "CAN"
    assert panel._selected_design_id == ""
    assert fake_imgui.disabled == [False]
    assert fake_imgui.calls[0][0] == "combo"


def test_design_tree_handles_closed_empty_group_selection_and_info(monkeypatch):
    fake_imgui = FakeImGui(clicked={"unit_production.view_design.D1"}, selectable_clicked=True)
    monkeypatch.setattr(production_module, "imgui", fake_imgui)
    monkeypatch.setattr(production_module.UIPrimitives, "fit_text", staticmethod(lambda value, _width: value))
    install_child_frame(monkeypatch, opened=False)
    panel = UnitProductionPanel(open_design_cb=Mock())
    panel._selected_design_id = "D1"
    row = {"id": "D1", "display_name": "Tank", "class_name": "tank"}
    assert panel._render_design_tree([row], FakeUI()) == row

    install_child_frame(monkeypatch, opened=True)
    assert panel._render_design_tree([], FakeUI()) is None
    assert any(call[0] == "text_disabled" for call in fake_imgui.calls)

    selected = panel._render_design_tree([row], FakeUI())
    assert selected == row
    assert panel._selected_design_id == "D1"
    panel._open_design_cb.assert_called_once_with("D1")
    assert fake_imgui.calls[-1][0] == "pop_style_var"


def test_design_tree_skips_collapsed_groups(monkeypatch):
    fake_imgui = FakeImGui(tree_open=False)
    monkeypatch.setattr(production_module, "imgui", fake_imgui)
    install_child_frame(monkeypatch, opened=True)
    panel = UnitProductionPanel()

    assert panel._render_design_tree([{"id": "D1", "class_name": "tank"}], FakeUI()) is None
    assert not any(call[0] == "tree_pop" for call in fake_imgui.calls)


def test_design_details_queues_domestic_order_and_updates_quantity(monkeypatch):
    fake_imgui = FakeImGui(
        combo_results=[(True, 1), (False, 0)],
        input_result=(True, "75"),
        hovered=True,
    )
    monkeypatch.setattr(production_module, "imgui", fake_imgui)
    client = Client()
    panel = UnitProductionPanel()
    panel._selected_builder_country = "USA"
    panel._presenter = Mock()
    panel._presenter.production_orders_for_country.return_value = []
    ui = FakeUI(button_ids={"unit_production.build"})
    design = {"id": "D1", "display_name": "Interceptor", "class_name": "fighter", "cost": 1200}

    panel._render_design_details(
        client_state(tables={}),
        design,
        "USA",
        ui,
        PanelRenderContext(target_tag="USA", is_own_country=True, net_client=client),
    )

    assert panel._quantity == 75
    assert panel._build_priority_index == 1
    assert len(client.actions) == 1
    assert isinstance(client.actions[0], ActionQueueUnitProduction)
    assert client.actions[0].design_id == "D1"
    assert client.actions[0].quantity == 75
    assert client.actions[0].priority == 50
    assert ui.calls[-1][4]["enabled"] is True
    assert any(call[0] == "tooltip" for call in fake_imgui.calls)


def test_design_details_without_selection_shows_build_hint_and_sends_nothing(monkeypatch):
    monkeypatch.setattr(production_module, "imgui", FakeImGui())
    panel = UnitProductionPanel()
    panel._selected_builder_country = "USA"
    panel._presenter = Mock()
    panel._presenter.production_orders_for_country.return_value = []
    ui = FakeUI(button_ids={"unit_production.build"})
    client = Client()

    panel._render_design_details(
        client_state(tables={}), None, "USA", ui,
        PanelRenderContext(target_tag="USA", is_own_country=True, net_client=client),
    )

    build = next(call for call in ui.calls if call[0] == "button")
    assert build[2] == "BUILD"
    assert build[4]["tooltip"] == "Select a design from the list first."
    assert build[4]["enabled"] is False
    assert client.actions == []


def test_design_details_requests_accepted_foreign_design_and_disables_unaccepted(monkeypatch):
    fake_imgui = FakeImGui(combo_results=[(False, 0), (False, 0)], input_result=(False, "50"))
    monkeypatch.setattr(production_module, "imgui", fake_imgui)
    client = Client()
    panel = UnitProductionPanel()
    panel._selected_builder_country = "CAN"
    panel._presenter = Mock()
    panel._presenter.production_orders_for_country.return_value = []
    ui = FakeUI(button_ids={"unit_production.build"})
    design = {
        "id": "D2", "display_name": "Foreign Fighter", "class_name": "fighter",
        "cost": 4000, "seller_accepts_orders": True,
    }

    panel._render_design_details(
        client_state(tables={}), design, "USA", ui,
        PanelRenderContext(target_tag="USA", is_own_country=True, net_client=client),
    )

    assert isinstance(client.actions[0], ActionRequestForeignUnitOrder)
    assert client.actions[0].seller_country_tag == "CAN"
    assert client.actions[0].design_id == "D2"

    client.actions.clear()
    design["seller_accepts_orders"] = False
    ui = FakeUI()
    panel._render_design_details(
        client_state(tables={}), design, "USA", ui,
        PanelRenderContext(target_tag="USA", is_own_country=True, net_client=client),
    )
    build = next(call for call in ui.calls if call[0] == "button")
    assert build[2] == "REQUEST"
    assert build[4]["enabled"] is False
    assert client.actions == []


def test_design_details_shows_infantry_population_and_queue_limit(monkeypatch):
    fake_imgui = FakeImGui(input_result=(False, "50"))
    monkeypatch.setattr(production_module, "imgui", fake_imgui)
    panel = UnitProductionPanel()
    panel._selected_builder_country = "USA"
    panel._working_age_population = Mock(return_value=None)
    panel._presenter = Mock()
    panel._presenter.production_orders_for_country.return_value = [{}] * production_module.MAX_PRODUCTION_QUEUE_ORDERS
    ui = FakeUI()
    design = {"id": "INF", "display_name": "Infantry", "class_name": "infantry", "cost": 100}

    panel._render_design_details(
        client_state(tables={}), design, "USA", ui,
        PanelRenderContext(target_tag="USA", is_own_country=True, net_client=Client()),
    )

    manpower = next(call for call in ui.calls if call[0] == "text" and call[2].get("test_id") == "unit_production.manpower.value")
    assert manpower[1][1] == "N/A"
    assert "not an enlistment allowance" in next(call[2]["tooltip"] for call in ui.calls if call[0] == "text" and call[1][1] == "POP. 15-64")
    build = next(call for call in ui.calls if call[0] == "button")
    assert build[2] == "ENROLL"
    assert build[4]["enabled"] is False
    assert "limited to" in build[4]["tooltip"]


def test_foreign_acceptance_toggle_and_capacity_show_snapshot_state():
    panel = UnitProductionPanel()
    client = Client()
    ui = FakeUI(toggle_values={"unit_production.accept_foreign": (True, True)})
    panel._render_accept_foreign_toggle(
        SimpleNamespace(tables={"seller_acceptance_profiles": None}),
        "USA", ui,
        PanelRenderContext(target_tag="USA", is_own_country=True, net_client=client),
    )
    assert isinstance(client.actions[0], ActionSetForeignOrderAcceptance)
    assert client.actions[0].is_accepting is True

    ui = FakeUI()
    panel._capacity_ratio = lambda _state, _tag: None
    panel._render_capacity(object(), "USA", ui)
    assert any(call[0] == "text" and call[1][1] == "N/A" for call in ui.calls)
    assert next(call for call in ui.calls if call[0] == "meter")[1][1] == 0.0

    ui = FakeUI()
    panel._capacity_ratio = lambda _state, _tag: 0.4
    panel._render_capacity(object(), "USA", ui)
    assert any(call[0] == "text" and call[1][1] == "40%" for call in ui.calls)


def test_right_page_switches_to_deployments_and_capacity_after_child(monkeypatch):
    install_child_frame(monkeypatch, opened=True)
    panel = UnitProductionPanel()
    ui = FakeUI(button_ids={"unit_production.page.deployments"})
    panel._render_deployment_orders = Mock()
    panel._render_capacity = Mock()
    context = PanelRenderContext(target_tag="USA", is_own_country=True)
    state = object()

    panel._render_right_page(state, "USA", ui, context, 500.0)

    assert panel._right_page == "deployments"
    panel._render_deployment_orders.assert_called_once_with(state, "USA", context)
    panel._render_capacity.assert_called_once()


def test_right_page_renders_queue_headings_and_routes_to_queue(monkeypatch):
    install_child_frame(monkeypatch, opened=True)
    panel = UnitProductionPanel()
    panel._render_production_queue = Mock()
    panel._render_capacity = Mock()
    ui = FakeUI()
    state = object()
    context = PanelRenderContext(target_tag="USA", is_own_country=True)

    panel._render_right_page(state, "USA", ui, context, 400.0)

    panel._render_production_queue.assert_called_once_with(state, "USA", context, 400.0)
    panel._render_capacity.assert_called_once()
    headings = [call[1][1] for call in ui.calls if call[0] == "text"]
    assert headings == ["PRODUCTION QUEUE", "QTY", "FROM", "TO", "PRIORITY"]


def test_right_page_routes_to_foreign_orders_and_skips_capacity_if_child_closed(monkeypatch):
    panel = UnitProductionPanel()
    panel._render_foreign_orders = Mock()
    panel._render_capacity = Mock()
    ui = FakeUI(button_ids={"unit_production.page.foreign"})
    state = object()
    context = PanelRenderContext(target_tag="USA", is_own_country=True)

    install_child_frame(monkeypatch, opened=True)
    panel._render_right_page(state, "USA", ui, context, None)
    panel._render_foreign_orders.assert_called_once_with(state, "USA", context)
    panel._render_capacity.assert_called_once()

    panel._render_capacity.reset_mock()
    install_child_frame(monkeypatch, opened=False)
    panel._render_right_page(state, "USA", FakeUI(), context, None)
    panel._render_capacity.assert_not_called()


def test_empty_production_queue_renders_explicit_empty_state(monkeypatch):
    fake_imgui = FakeImGui()
    monkeypatch.setattr(production_module, "imgui", fake_imgui)
    panel = UnitProductionPanel()
    panel._presenter.production_orders_for_country = Mock(return_value=[])

    panel._render_production_queue(SimpleNamespace(tables={}), "USA", PanelRenderContext(target_tag="USA", is_own_country=True), 500.0)

    assert any(call[0] == "text_disabled" and call[1][0] == "No production orders are queued." for call in fake_imgui.calls)


def test_production_queue_renders_rows_and_restores_imgui_style(monkeypatch):
    fake_imgui = FakeImGui()
    monkeypatch.setattr(production_module, "imgui", fake_imgui)
    panel = UnitProductionPanel()
    order = {"id": "O1", "design_id": "D1"}
    panel._presenter.production_orders_for_country = Mock(return_value=[order])
    panel._render_production_row = Mock()
    designs = SimpleNamespace(to_dicts=lambda: [{"id": "D1", "display_name": "Armor"}])

    panel._render_production_queue(
        SimpleNamespace(tables={"unit_designs": designs}), "USA",
        PanelRenderContext(target_tag="USA", is_own_country=True), 500.0,
    )

    panel._render_production_row.assert_called_once_with(
        order, {"id": "D1", "display_name": "Armor"}, {}, "USA",
        panel._render_production_row.call_args.args[4], 500.0,
    )
    assert fake_imgui.calls[-1][0] == "pop_style_var"


def test_foreign_orders_show_eligible_requests_and_empty_contract_state(monkeypatch):
    fake_imgui = FakeImGui(clicked={"unit_production.foreign.request.D1"})
    monkeypatch.setattr(production_module, "imgui", fake_imgui)
    monkeypatch.setattr(production_module.UIPrimitives, "fit_text", staticmethod(lambda value, _width: value))
    panel = UnitProductionPanel()
    panel._quantity = 4
    panel._presenter.foreign_designs_for_country = Mock(return_value=[
        {"id": "D1", "country_id": "CAN", "display_name": "Tank", "cost": 100, "seller_accepts_orders": True},
        {"id": "D2", "country_id": "MEX", "display_name": "Ship", "cost": 200, "seller_accepts_orders": False},
    ])
    panel._presenter.foreign_orders_for_country = Mock(return_value=[])
    client = Client()

    panel._render_foreign_orders(
        object(), "USA", PanelRenderContext(target_tag="USA", is_own_country=True, net_client=client),
    )

    assert len(client.actions) == 1
    assert isinstance(client.actions[0], ActionRequestForeignUnitOrder)
    assert client.actions[0].quantity == 4
    assert fake_imgui.disabled == [False, True]
    assert any(call[0] == "text_disabled" and call[1][0] == "No foreign unit contracts are active or recently completed." for call in fake_imgui.calls)


def test_foreign_orders_without_designs_still_renders_existing_contracts(monkeypatch):
    fake_imgui = FakeImGui()
    monkeypatch.setattr(production_module, "imgui", fake_imgui)
    panel = UnitProductionPanel()
    panel._presenter.foreign_designs_for_country = Mock(return_value=[])
    panel._presenter.foreign_orders_for_country = Mock(return_value=[{"id": "O1"}])
    panel._render_foreign_contract = Mock()

    panel._render_foreign_orders(
        object(), "USA", PanelRenderContext(target_tag="USA", is_own_country=False),
    )

    assert any(call[0] == "text_disabled" and call[1][0] == "No foreign designs are eligible for inspection." for call in fake_imgui.calls)
    panel._render_foreign_contract.assert_called_once_with({"id": "O1"}, "USA", panel._render_foreign_contract.call_args.args[2])


def test_foreign_contract_rejection_sends_negative_response(monkeypatch):
    fake_imgui = FakeImGui(clicked={"unit_production.foreign.reject.C1"})
    monkeypatch.setattr(production_module, "imgui", fake_imgui)
    monkeypatch.setattr(production_module.UIPrimitives, "fit_text", staticmethod(lambda value, _width: value))
    panel = UnitProductionPanel()
    client = Client()

    panel._render_foreign_contract(
        {"id": "C1", "seller_country_id": "USA", "status": "pending_seller_acceptance"},
        "USA",
        PanelRenderContext(target_tag="USA", is_own_country=True, net_client=client),
    )

    assert len(client.actions) == 1
    assert client.actions[0].order_id == "C1"
    assert client.actions[0].accept is False
