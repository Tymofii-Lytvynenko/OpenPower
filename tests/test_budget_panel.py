from types import SimpleNamespace
from unittest.mock import Mock

import math
import polars as pl
import pytest

import src.client.ui.panels.budget_panel as budget_panel_module
import src.client.ui.core.primitives as primitives_module
from src.client.ui.panels.budget_panel import BudgetPanel
from src.shared.actions import ActionUpdateBudget


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
def test_budget_row_more_button_opens_its_own_details_popup(
    monkeypatch, detail_key, label, value
):
    imgui = SimpleNamespace(
        StyleVar_=SimpleNamespace(frame_padding=object()),
        Col_=SimpleNamespace(button=object()),
        text=Mock(),
        same_line=Mock(),
        push_style_var=Mock(),
        push_style_color=Mock(),
        button=Mock(return_value=True),
        open_popup=Mock(),
        pop_style_color=Mock(),
        pop_style_var=Mock(),
        begin_popup=Mock(return_value=True),
        text_wrapped=Mock(),
        end_popup=Mock(),
    )
    right_align_text = Mock()
    monkeypatch.setattr(budget_panel_module, "imgui", imgui)
    monkeypatch.setattr(primitives_module, "imgui", imgui)
    monkeypatch.setattr(budget_panel_module.Prims, "right_align_text", right_align_text)

    BudgetPanel()._draw_standard_row(label, value, has_more=True, detail_key=detail_key)

    popup_id = f"Budget details##{detail_key}"
    imgui.button.assert_called_once_with(f"more###budget.details.{detail_key}")
    imgui.open_popup.assert_called_once_with(popup_id)
    imgui.begin_popup.assert_called_once_with(popup_id)
    imgui.text_wrapped.assert_called_once_with(
        BudgetPanel()._standard_row_details(detail_key, value)
    )
    right_align_text.assert_called_once()


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

    panel._sync_with_state(state, "AAA")

    assert panel.allocations[panel.PERSONAL_INCOME_TAX_KEY] == 1.0
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
        "PERSONAL INCOME TAX RATE###budget.income_tax_rate", 20.0, 0.0, 100.0, "%.0f%%"
    )
    assert panel.draft_allocations[panel.PERSONAL_INCOME_TAX_KEY] == 0.72
