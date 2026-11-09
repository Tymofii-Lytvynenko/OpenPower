from contextlib import contextmanager
from types import SimpleNamespace

import polars as pl
import pytest

import src.client.ui.panels.economy_panel as economy_panel_module
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.economy_panel import EconomyPanel


def _state(tables=None):
    tables = tables or {}
    return SimpleNamespace(tables=tables, get_table=lambda name: tables[name])


@pytest.mark.parametrize(
    ("production", "expected"),
    [
        (None, 0.0),
        (pl.DataFrame({"country_id": ["UKR"]}), 0.0),
        (pl.DataFrame([{"country_id": "POL", "domestic_production": 10.0}]), 0.0),
        (pl.DataFrame([{"country_id": "UKR", "domestic_production": 0.0}]), 0.0),
        (pl.DataFrame([{"country_id": "UKR", "domestic_production": 10.0}]), 1.0),
        (
            pl.DataFrame(
                [
                    {"country_id": "UKR", "domestic_production": 60.0, "is_gov_controlled": True},
                    {"country_id": "UKR", "domestic_production": 40.0, "is_gov_controlled": False},
                ]
            ),
            0.4,
        ),
        (
            pl.DataFrame([{"country_id": "UKR", "domestic_production": 10.0, "is_gov_controlled": True}]),
            0.0,
        ),
    ],
)
def test_market_model_value_handles_missing_zero_and_controlled_production(production, expected):
    tables = {} if production is None else {"domestic_production": production}
    assert EconomyPanel()._get_market_model_value(_state(tables), "UKR") == pytest.approx(expected)


@pytest.mark.parametrize(
    ("ledger", "expected"),
    [
        (None, 0.0),
        (pl.DataFrame({"consumption_usd": [10.0]}), 0.0),
        (pl.DataFrame([{"country_id": "POL", "consumption_usd": 10.0, "balance_usd": 0.0}]), 0.0),
        (pl.DataFrame([{"country_id": "UKR", "consumption_usd": 0.0, "balance_usd": -1.0}]), 1.0),
        (pl.DataFrame([{"country_id": "UKR", "consumption_usd": 10.0}]), 1.0),
        (
            pl.DataFrame(
                [
                    {"country_id": "UKR", "consumption_usd": 100.0, "balance_usd": -20.0},
                    {"country_id": "UKR", "consumption_usd": 50.0, "balance_usd": 15.0},
                ]
            ),
            pytest.approx(0.8666667),
        ),
        (
            pl.DataFrame([{"country_id": "UKR", "consumption_usd": 5.0, "balance_usd": -10.0}]),
            0.0,
        ),
    ],
)
def test_resource_health_handles_missing_zero_and_shortage_ledgers(ledger, expected):
    tables = {} if ledger is None else {"resource_ledger": ledger}
    assert EconomyPanel()._get_resource_health(_state(tables), "UKR") == expected


@pytest.mark.parametrize(
    ("table_name", "method_name"),
    [
        ("domestic_production", "_get_market_model_value"),
        ("resource_ledger", "_get_resource_health"),
    ],
)
def test_economy_estimates_default_when_table_access_fails(table_name, method_name):
    def fail_to_read(_name):
        raise ValueError("table snapshot is invalid")

    state = SimpleNamespace(tables={table_name: object()}, get_table=fail_to_read)

    estimate = getattr(EconomyPanel(), method_name)(state, "UKR")

    assert estimate == 0.0


class _FakeWidgets:
    button_results = {}
    last = None

    def __init__(self, path):
        self.path = path
        self.calls = []
        type(self).last = self

    def text(self, path, value, **kwargs):
        self.calls.append(("text", path, value, kwargs))

    def meter(self, path, value, color, **kwargs):
        self.calls.append(("meter", path, value, color, kwargs))

    def button(self, path, _label, test_id, **kwargs):
        self.calls.append(("button", path, test_id, kwargs))
        return kwargs.get("enabled", True) and type(self).button_results.get(test_id, False)


def test_render_content_reads_economy_metrics_and_dispatches_enabled_shortcuts(monkeypatch):
    callbacks = []
    panel = EconomyPanel(
        toggle_resources_cb=lambda: callbacks.append("resources"),
        toggle_budget_cb=lambda: callbacks.append("budget"),
        toggle_health_cb=lambda: callbacks.append("health"),
        toggle_trade_cb=lambda: callbacks.append("trade"),
    )
    _FakeWidgets.button_results = {
        "economy.health_btn": True,
        "economy.budget_btn": True,
        "economy.resources_btn": True,
        "economy.trade_btn": True,
    }
    monkeypatch.setattr(economy_panel_module, "GMLWidgets", _FakeWidgets)
    tooltips = []
    monkeypatch.setattr(
        economy_panel_module,
        "imgui",
        SimpleNamespace(is_item_hovered=lambda: True, set_tooltip=tooltips.append),
    )
    state = _state(
        {
            "countries": pl.DataFrame(
                [
                    {
                        "id": "UKR",
                        "total_annual_revenue": 100.0,
                        "total_annual_expense": 120.0,
                        "money_reserves": 50.0,
                        "economic_health": None,
                    }
                ]
            ),
            "domestic_production": pl.DataFrame(
                [
                    {"country_id": "UKR", "domestic_production": 60.0, "is_gov_controlled": True},
                    {"country_id": "UKR", "domestic_production": 40.0, "is_gov_controlled": False},
                ]
            ),
            "resource_ledger": pl.DataFrame(
                [{"country_id": "UKR", "consumption_usd": 100.0, "balance_usd": -30.0}]
            ),
        }
    )

    panel._render_content(state, "UKR", True)

    assert callbacks == ["health", "budget", "resources", "trade"]
    texts = [call for call in _FakeWidgets.last.calls if call[0] == "text"]
    assert any(call[1] == "frmEconomicHealth/txtValue" and call[2] == "84%" for call in texts)
    assert any(call[1] == "frmResources/txtValue" and call[2] == "70%" for call in texts)
    assert any(call[1] == "frmBudget/lblAvailable" and call[2] == "FUNDS" for call in texts)
    assert any(call[1] == "frmBudget/txtBalance" and call[2] == "$ -20" for call in texts)
    assert tooltips == ["State-controlled model", "Free-market model", "Available country reserves"]


def test_render_content_uses_defaults_for_missing_country_or_invalid_snapshot(monkeypatch):
    panel = EconomyPanel()
    monkeypatch.setattr(economy_panel_module, "GMLWidgets", _FakeWidgets)
    monkeypatch.setattr(
        economy_panel_module,
        "imgui",
        SimpleNamespace(is_item_hovered=lambda: False, set_tooltip=lambda _text: None),
    )
    panel._render_content(_state(), "UKR", False)
    texts = [call for call in _FakeWidgets.last.calls if call[0] == "text"]
    assert any(call[1] == "frmBudget/txtIncome" and call[2] == "$ 0" for call in texts)
    bad_state = _state({"countries": pl.DataFrame({"name": ["Ukraine"]})})
    panel._render_content(bad_state, "UKR", False)
    texts = [call for call in _FakeWidgets.last.calls if call[0] == "text"]
    assert any(call[1] == "frmEconomicHealth/txtValue" and call[2] == "0%" for call in texts)


@pytest.mark.parametrize("open_window", [True, False])
def test_render_respects_window_state_and_uses_right_anchored_layout(monkeypatch, open_window):
    panel = EconomyPanel()
    positions = []
    calls = []
    monkeypatch.setattr(economy_panel_module, "main_pillar_position", lambda name: positions.append(name) or (11, 22))
    monkeypatch.setattr(
        economy_panel_module,
        "imgui",
        SimpleNamespace(
            WindowFlags_=SimpleNamespace(no_resize=1, no_scrollbar=2, no_scroll_with_mouse=4)
        ),
    )

    @contextmanager
    def window(*args, **kwargs):
        calls.append((args, kwargs))
        yield open_window

    monkeypatch.setattr(economy_panel_module.WindowManager, "window", window)
    panel._render_content = lambda *args: calls.append(("content", args))
    context = PanelRenderContext("UKR", True)

    assert panel.render(_state(), context) is open_window

    assert positions == ["economy"]
    assert calls[0][0][0] == "ECONOMY"
    assert calls[0][1]["horizontal_anchor"] == "right"
    assert len(calls) == (2 if open_window else 1)
