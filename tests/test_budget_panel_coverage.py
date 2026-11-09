from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import polars as pl
import pytest

import src.client.ui.panels.budget_panel as budget_panel_module
from src.client.ui.components.shared.dirty_close_confirmation import CloseDecision
from src.client.ui.panels.budget_panel import BudgetPanel
from src.shared.actions import ActionUpdateBudget


class Client:
    player_id = "player-1"

    def __init__(self):
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)


def _state(tables=None):
    tables = tables or {}
    return SimpleNamespace(tables=tables, get_table=lambda name: tables[name])


def _context(client=None, *, own=True):
    return SimpleNamespace(
        target_tag="AAA",
        is_own_country=own,
        net_client=client,
        save_confirmation_preferences=None,
    )


def test_render_applies_changes_and_handles_clean_or_discarded_closes(monkeypatch):
    panel = BudgetPanel()
    panel._sync_target_allocations = Mock()
    panel._render_content = Mock()
    panel.close_confirmation.render = Mock(return_value=None)
    panel.close_confirmation.request_close = Mock(return_value=CloseDecision.DISCARD)
    client = Client()
    opened = [True, True, False, False]
    windows = []

    @contextmanager
    def window(*args, **kwargs):
        windows.append((args, kwargs))
        yield opened.pop(0)

    monkeypatch.setattr(budget_panel_module.WindowManager, "window", window)
    imgui = SimpleNamespace(
        Col_=SimpleNamespace(button=1),
        begin_disabled=Mock(),
        push_style_color=Mock(),
        pop_style_color=Mock(),
        end_disabled=Mock(),
    )
    monkeypatch.setattr(budget_panel_module, "imgui", imgui)
    button = Mock(return_value=True)
    monkeypatch.setattr(budget_panel_module.Prims, "button", button)

    assert panel.render(_state(), _context(client)) is True
    panel._render_content.assert_called_once()
    button.assert_called_once()
    assert client.actions == []

    panel.draft_allocations["budget_health_ratio"] = 0.75
    assert panel.render(_state(), _context(client)) is True
    assert len(client.actions) == 1
    assert isinstance(client.actions[0], ActionUpdateBudget)
    assert panel.draft_allocations == panel.allocations

    panel._render_content.reset_mock()
    assert panel.render(_state(), _context(client)) is False
    panel.close_confirmation.request_close.assert_not_called()
    panel._render_content.assert_not_called()

    panel.draft_allocations["budget_health_ratio"] = 0.25
    assert panel.render(_state(), _context(client)) is False
    panel.close_confirmation.request_close.assert_called_once()
    assert panel.draft_allocations == panel.allocations
    assert windows[0][0] == ("BUDGET MENU",)


def test_render_content_builds_income_expense_fixed_cost_and_balance_rows(monkeypatch):
    panel = BudgetPanel()
    panel._draw_gml_text = Mock()
    panel._draw_more_button = Mock()
    panel._draw_income_tax_slider = Mock()
    panel._draw_gml_expense_slider = Mock()
    countries = pl.DataFrame([{
        "id": "AAA",
        "revenue_tax": 100.0,
        "trade_income": 50.0,
        "tourism_income": 25.0,
        "budget_imf_ratio": 20.0,
        "total_annual_revenue": 195.0,
        "expense_corruption": 5.0,
        "security_upkeep": 10.0,
        "diplomacy_upkeep": 15.0,
        "trade_expense": 20.0,
        "expense_military_upkeep": 25.0,
        "expense_debt_interest": 30.0,
        "money_reserves": 200.0,
    }])
    ledger = pl.DataFrame([{"country_id": "AAA", "consumption_usd": 1000.0}])
    state = _state({"countries": countries, "resource_ledger": ledger})

    panel._render_content(state, "AAA", True)

    calls = panel._draw_gml_text.call_args_list
    assert call_by_slot(calls, "frmIncome", "txtTotal").args[2] == "$ 195"
    assert call_by_slot(calls, "frmFixedExpenses", "txtTotal").args[2] == "$ 105"
    assert call_by_slot(calls, "frmBalance", "txtAmount").args[2] == panel._fmt_money(
        195.0 - 105.0 - sum(
            1000.0 * panel.K_BUDGET * panel.M_SECTOR_WEIGHTS[key] * panel.draft_allocations[key]
            for key in panel.M_SECTOR_LABELS
        )
    )
    assert call_by_slot(calls, "frmAvailable", "txtAmount").args[2] == "$ 200"
    assert panel._draw_gml_expense_slider.call_count == 10
    assert panel._draw_more_button.call_count == 6
    panel._draw_income_tax_slider.assert_called_once_with(True)


def call_by_slot(calls, section, component):
    return next(call for call in calls if call.args[:2] == (section, component))


def test_render_content_handles_missing_tables_and_missing_country_row():
    panel = BudgetPanel()
    panel._draw_gml_text = Mock()
    panel._draw_more_button = Mock()
    panel._draw_income_tax_slider = Mock()
    panel._draw_gml_expense_slider = Mock()

    panel._render_content(_state(), "AAA", False)
    panel._render_content(_state({"countries": pl.DataFrame({"id": ["BBB"]})}), "AAA", False)

    assert panel._draw_gml_expense_slider.call_count == 20
    assert panel._draw_gml_text.call_count > 0


@pytest.mark.parametrize(
    ("own", "allocation", "active", "mouse_x", "expected", "fill_count"),
    [
        (True, 0.2, False, 10.0, 0.2, 4),
        (True, 0.8, False, 10.0, 0.8, 4),
        (True, 0.1, True, 60.0, 0.5, 3),
        (False, 0.5, False, 10.0, 0.5, 3),
    ],
)
def test_expense_slider_draws_threshold_and_updates_only_active_input(
    monkeypatch, own, allocation, active, mouse_x, expected, fill_count
):
    panel = BudgetPanel()
    panel.draft_allocations["budget_health_ratio"] = allocation
    panel._draw_gml_text = Mock()
    imgui = MagicMock()
    imgui.get_item_rect_min.return_value = SimpleNamespace(x=10.0, y=20.0)
    imgui.get_item_rect_max.return_value = SimpleNamespace(x=110.0, y=36.0)
    imgui.is_item_active.return_value = active
    imgui.get_io.return_value.mouse_pos = SimpleNamespace(x=mouse_x)
    imgui.get_window_draw_list.return_value = MagicMock()
    monkeypatch.setattr(budget_panel_module, "imgui", imgui)
    invisible = Mock()
    monkeypatch.setattr(budget_panel_module.Prims, "invisible_button", invisible)

    panel._draw_gml_expense_slider(
        "budget_health_ratio", "HEALTH CARE", 500.0, own,
        "lblHealthCare", "frmMeterHealthCare", "txtHealthCare",
    )

    assert panel.draft_allocations["budget_health_ratio"] == expected
    assert imgui.get_window_draw_list.return_value.add_rect_filled.call_count == fill_count
    assert invisible.call_args.kwargs["enabled"] is own
    assert imgui.begin_disabled.call_count == (0 if own else 1)
    assert imgui.end_disabled.call_count == (0 if own else 1)
    last_text = panel._draw_gml_text.call_args_list[-1]
    assert last_text.args == ("frmExpenses", "txtHealthCare", panel._fmt_short_money(500.0))
    assert last_text.kwargs == {"align": "right"}


def test_income_tax_slider_uses_active_layout_and_disables_remote_edit(monkeypatch):
    panel = BudgetPanel()
    imgui = SimpleNamespace(
        set_cursor_screen_pos=Mock(),
        set_next_item_width=Mock(),
        begin_disabled=Mock(),
        end_disabled=Mock(),
    )
    monkeypatch.setattr(budget_panel_module, "imgui", imgui)
    slider = Mock(return_value=(False, 80.0))
    monkeypatch.setattr(budget_panel_module.Prims, "slider_float", slider)
    session = SimpleNamespace(
        layout=SimpleNamespace(component=Mock(return_value=object())),
        rect_for=Mock(return_value=SimpleNamespace(x=4.0, y=5.0)),
        window_position=(100.0, 200.0),
    )
    monkeypatch.setattr(budget_panel_module, "active_gml_layout", lambda: session)

    panel._draw_income_tax_slider(is_own=False)

    imgui.set_cursor_screen_pos.assert_called_once_with((153.0, 205.0))
    imgui.begin_disabled.assert_called_once_with()
    imgui.end_disabled.assert_called_once_with()
    assert panel.draft_allocations[panel.PERSONAL_INCOME_TAX_KEY] == 0.2
    assert slider.call_args.kwargs["enabled"] is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [(-12.0, "$ - 12"), (1_500_000.0, "$ 1.5 M"), (2_500_000_000.0, "$ 2.5 B")],
)
def test_short_currency_format_uses_readable_million_and_billion_units(value, expected):
    assert BudgetPanel()._fmt_short_money(value) == expected


def test_budget_demand_returns_zero_for_missing_or_unmatched_ledger():
    panel = BudgetPanel()
    assert panel._get_player_total_demand(_state(), "AAA") == 0.0
    assert panel._get_player_total_demand(
        _state({"resource_ledger": pl.DataFrame({"country_id": ["BBB"], "consumption_usd": [500.0]})}),
        "AAA",
    ) == 0.0
    assert panel._get_player_total_demand(
        _state({"resource_ledger": pl.DataFrame({"country_id": ["AAA"], "consumption_usd": [500.0]})}),
        "AAA",
    ) == 500.0


def test_render_finishes_close_decision_returned_by_confirmation(monkeypatch):
    panel = BudgetPanel()
    panel._sync_target_allocations = Mock()
    panel._render_content = Mock()
    panel.close_confirmation.render = Mock(return_value=CloseDecision.DISCARD)

    @contextmanager
    def opened_window(*_args, **_kwargs):
        yield True

    monkeypatch.setattr(budget_panel_module.WindowManager, "window", opened_window)
    monkeypatch.setattr(
        budget_panel_module,
        "imgui",
        SimpleNamespace(
            Col_=SimpleNamespace(button=1),
            begin_disabled=Mock(),
            push_style_color=Mock(),
            pop_style_color=Mock(),
            end_disabled=Mock(),
        ),
    )
    monkeypatch.setattr(budget_panel_module.Prims, "button", Mock(return_value=False))

    assert panel.render(_state(), _context(Client())) is False
    panel._render_content.assert_called_once()
    assert panel.draft_allocations == panel.allocations


def test_budget_sync_rejects_missing_tables_and_unusable_country_allocations(monkeypatch):
    panel = BudgetPanel()
    assert not panel._sync_with_state(_state(), "AAA")

    monkeypatch.setattr(
        budget_panel_module,
        "country_budget_allocations",
        Mock(return_value=None),
    )
    state = _state({"countries": pl.DataFrame({"id": ["AAA"]})})

    assert not panel._sync_with_state(state, "AAA")


def test_finish_close_dispatches_apply_decision():
    panel = BudgetPanel()
    client = Client()

    panel._finish_close(CloseDecision.APPLY, client, "AAA")

    assert len(client.actions) == 1
    assert isinstance(client.actions[0], ActionUpdateBudget)


def test_gml_text_uses_plain_and_colored_imgui_calls(monkeypatch):
    imgui = SimpleNamespace(text=Mock(), text_colored=Mock())
    monkeypatch.setattr(budget_panel_module, "imgui", imgui)
    panel = BudgetPanel()

    panel._draw_gml_text("frmIncome", "txtTotal", "$ 10")
    panel._draw_gml_text("frmBalance", "txtAmount", "$ 5", color=(1, 2, 3, 4), align="right")

    imgui.text.assert_called_once_with(
        "$ 10",
        gml_id="Budget_Window/frmInner/frmIncome/txtTotal",
        gml_align=None,
    )
    imgui.text_colored.assert_called_once_with(
        (1, 2, 3, 4),
        "$ 5",
        gml_id="Budget_Window/frmInner/frmBalance/txtAmount",
        gml_align="right",
    )


def test_more_button_without_registered_destination_is_not_drawn(monkeypatch):
    panel = BudgetPanel()
    button = Mock()
    monkeypatch.setattr(budget_panel_module.Prims, "button", button)

    panel._draw_more_button("unknown", "frmIncome", "btnMore", 10.0)

    button.assert_not_called()
