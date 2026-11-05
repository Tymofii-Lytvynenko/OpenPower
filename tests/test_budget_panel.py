from types import SimpleNamespace
from unittest.mock import Mock

import math
import polars as pl
import pytest

import src.client.ui.panels.budget_panel as budget_panel_module
import src.client.ui.core.primitives as primitives_module
from src.client.ui.panels.budget_panel import BudgetPanel
from modules.base.systems.economy.budget_system import BudgetSystem
from src.shared.actions import ActionUpdateBudget


def test_budget_preview_uses_the_same_sector_weights_as_simulation():
    panel = BudgetPanel()
    assert set(panel.M_SECTOR_LABELS) == set(BudgetSystem.M_SECTOR)
    assert panel.M_SECTOR_WEIGHTS == BudgetSystem.M_SECTOR
    assert panel.K_BUDGET == BudgetSystem.K_BUDGET
    panel.M_SECTOR_WEIGHTS["budget_health_ratio"] = 0.0
    assert BudgetSystem.M_SECTOR["budget_health_ratio"] == 0.25


@pytest.mark.parametrize(
    ("detail_key", "label", "value"),
    [
        ("income-tax", "PERSONAL INCOME TAX", 1200.0),
        ("income-trade", "TRADE", 800.0),
        ("fixed-security", "SECURITY", 50.0),
        ("fixed-diplomacy", "DIPLOMACY", 25.0),
        ("fixed-trade", "TRADE", 200.0),
        ("fixed-military-upkeep", "MILITARY UPKEEP", 500.0),
    ],
)
def test_budget_row_more_button_routes_to_its_registered_destination(monkeypatch, detail_key, label, value):
    callback = Mock()
    panel = BudgetPanel()
    panel._navigation_callbacks[detail_key] = callback
    button = Mock(return_value=True)
    tooltip = Mock()
    monkeypatch.setattr(budget_panel_module.Prims, "button", button)
    monkeypatch.setattr(budget_panel_module, "imgui", SimpleNamespace(is_item_hovered=lambda: True, set_tooltip=tooltip))
    # These controls now navigate to their source destination; a legacy popup
    # assertion would test a renderer that was removed during the GML transfer.
    panel._draw_more_button(detail_key, "frmIncome", "btnMore", value)
    button.assert_called_once_with("more", test_id=f"budget.navigate.{detail_key}",
                                   size=(37.0, 12.0), gml_id="Budget_Window/frmInner/frmIncome/btnMore")
    callback.assert_called_once_with()
    tooltip.assert_called_once_with(panel._standard_row_details(detail_key, value))


def test_budget_row_details_handle_unknown_key_without_losing_the_amount():
    details = BudgetPanel()._standard_row_details("unknown", 42.0)

    assert "Additional information is not available" in details
    assert "$ 42" in details


def test_budget_sync_loads_and_bounds_personal_tax_rate():
    panel = BudgetPanel()
    state = SimpleNamespace(
        tables={
            "countries": pl.DataFrame(
                {"id": ["AAA"], "personal_income_tax_rate": [1.4]}
            )
        },
    )
    state.get_table = lambda name: state.tables[name]

    assert panel._sync_with_state(state, "AAA")

    assert panel.allocations[panel.PERSONAL_INCOME_TAX_KEY] == 1.0
    assert panel.draft_allocations == panel.allocations


def test_budget_sync_retries_missing_country_without_reusing_previous_allocations():
    panel = BudgetPanel()
    state = SimpleNamespace(
        tables={
            "countries": pl.DataFrame(
                [{"id": "AAA", "budget_health_ratio": 0.15, "budget_edu_ratio": 0.9}]
            )
        },
    )
    state.get_table = lambda name: state.tables[name]

    panel._sync_target_allocations(state, "AAA")
    assert panel.allocations["budget_health_ratio"] == 0.15
    panel.draft_allocations["budget_health_ratio"] = 0.95

    panel._sync_target_allocations(state, "BBB")

    assert panel.current_tag == "BBB"
    assert panel._needs_state_sync
    assert panel.allocations["budget_health_ratio"] == 0.5
    assert panel.draft_allocations == panel.allocations

    state.tables["countries"] = pl.DataFrame(
        [{"id": "BBB", "budget_health_ratio": 0.7}]
    )
    panel._sync_target_allocations(state, "BBB")

    assert not panel._needs_state_sync
    assert panel.allocations["budget_health_ratio"] == 0.7
    assert panel.allocations["budget_edu_ratio"] == 0.5
    assert panel.draft_allocations == panel.allocations


def test_budget_action_dispatch_includes_clamped_sector_and_tax_ratios():
    panel = BudgetPanel()
    panel.allocations["budget_health_ratio"] = 0.25
    panel.draft_allocations.update(
        {
            "personal_income_tax_rate": 1.5,
            "budget_health_ratio": -0.4,
            "budget_edu_ratio": math.nan,
        }
    )
    client = SimpleNamespace(player_id="player-1", send_action=Mock())

    panel._dispatch_budget_update(client, "AAA")

    action = client.send_action.call_args.args[0]
    assert isinstance(action, ActionUpdateBudget)
    assert action.country_tag == "AAA"
    assert action.allocations["personal_income_tax_rate"] == 1.0
    assert action.allocations["budget_health_ratio"] == 0.0
    assert action.allocations["budget_edu_ratio"] == 0.5
    assert all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in action.allocations.values())
    assert panel.draft_allocations == action.allocations


def test_personal_tax_slider_displays_and_stores_percent_while_action_uses_ratio(monkeypatch):
    panel = BudgetPanel()
    imgui = SimpleNamespace(
        set_next_item_width=Mock(),
        slider_float=Mock(return_value=(True, 72.0)),
    )
    monkeypatch.setattr(budget_panel_module, "imgui", imgui)
    monkeypatch.setattr(primitives_module, "imgui", imgui)

    panel._draw_income_tax_slider(is_own=True)

    imgui.slider_float.assert_called_once_with(
        "##income-tax-rate###budget.income_tax_rate", 20.0, 0.0, 100.0, "%.0f%%", gml_id=None
    )
    assert panel.draft_allocations[panel.PERSONAL_INCOME_TAX_KEY] == 0.72
