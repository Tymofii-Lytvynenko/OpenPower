from contextlib import contextmanager
from types import SimpleNamespace

import polars as pl
import pytest

import src.client.ui.panels.economic_health_panel as economic_panel_module
from src.client.ui.components.shared.dirty_close_confirmation import CloseDecision
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.economic_health_panel import EconomicHealthPanel
from src.shared.actions import (
    ActionChangeEconomicPolicy,
    ActionRequestDebtContract,
    ActionRequestDebtRestructuring,
    ActionResolveDebtContract,
    ActionSetTax,
)


def _state(tables=None, globals_=None):
    tables = tables or {}
    return SimpleNamespace(
        tables=tables,
        globals=globals_ or {},
        get_table=lambda name: tables[name],
    )


def _context(*, client=True, own=True, target="UKR"):
    actions = []
    net_client = (
        SimpleNamespace(player_id="player-1", send_action=actions.append)
        if client
        else None
    )
    return PanelRenderContext(target, own, net_client=net_client), actions


@pytest.mark.parametrize(
    ("reserves", "expenses", "expected"),
    [(200, 100, 1.0), (50, 100, 0.5), (-10, 100, 0.0), (0, 0, 1.0), (-1, 0, 0.0)],
)
def test_reserve_coverage_bounds_ratio_and_handles_no_expenses(reserves, expenses, expected):
    assert EconomicHealthPanel()._reserve_coverage(reserves, expenses) == expected


@pytest.mark.parametrize(
    ("ledger", "expected"),
    [
        (None, 0.0),
        (pl.DataFrame([{"country_id": "POL", "consumption_usd": 10, "balance_usd": 0}]), 0.0),
        (pl.DataFrame([{"country_id": "UKR", "balance_usd": -1}]), 0.0),
        (pl.DataFrame([{"country_id": "UKR", "consumption_usd": 0, "balance_usd": -1}]), 1.0),
        (pl.DataFrame([{"country_id": "UKR", "consumption_usd": 10}]), 1.0),
        (
            pl.DataFrame(
                [
                    {"country_id": "UKR", "consumption_usd": 100, "balance_usd": -20},
                    {"country_id": "UKR", "consumption_usd": 50, "balance_usd": 15},
                ]
            ),
            pytest.approx(0.8666667),
        ),
        (pl.DataFrame([{"country_id": "UKR", "consumption_usd": 5, "balance_usd": -10}]), 0.0),
    ],
)
def test_resource_coverage_handles_missing_zero_and_shortage_ledgers(ledger, expected):
    tables = {} if ledger is None else {"resource_ledger": ledger}
    assert EconomicHealthPanel()._resource_coverage(_state(tables), "UKR") == expected


def test_country_population_sums_age_bands_and_rejects_missing_or_zero_data():
    panel = EconomicHealthPanel()
    assert panel._country_population(_state(), "UKR") is None
    assert panel._country_population(
        _state({"regions": pl.DataFrame({"owner": ["UKR"], "pop_14": [1]})}), "UKR"
    ) is None
    assert panel._country_population(
        _state(
            {
                "regions": pl.DataFrame(
                    [
                        {"owner": "UKR", "pop_14": 10, "pop_15_64": 80, "pop_65": 10},
                        {"owner": "UKR", "pop_14": None, "pop_15_64": 5, "pop_65": 0},
                        {"owner": "POL", "pop_14": 100, "pop_15_64": 100, "pop_65": 100},
                    ]
                )
            }
        ),
        "UKR",
    ) == 105.0


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.25, 0.25), ("0.75", 0.75), ("bad", 0.0), (float("inf"), 0.0), (None, 0.0)],
)
def test_finite_rate_rejects_invalid_and_infinite_values(value, expected):
    assert EconomicHealthPanel._finite_rate(value) == expected


def test_read_float_uses_defaults_for_missing_rows_columns_and_null_values():
    panel = EconomicHealthPanel()
    assert panel._read_float(None, "rate", 0.2) == 0.2
    assert panel._read_float(pl.DataFrame({"other": [1]}), "rate", 0.2) == 0.2
    assert panel._read_float(pl.DataFrame({"rate": [None]}), "rate", 0.2) == 0.2
    assert panel._read_float(pl.DataFrame({"rate": ["0.35"]}), "rate", 0.2) == 0.35


@pytest.mark.parametrize(
    ("terms", "expected"),
    [
        ({}, (0.0, 0.5)),
        ({"min_interest_rate": 0.02, "max_interest_rate": 0.25}, (0.02, 0.25)),
        ({"min_interest_rate": "bad"}, (0.0, 0.5)),
        ({"min_interest_rate": float("nan")}, (0.0, 0.5)),
        ({"min_interest_rate": 0.4, "max_interest_rate": 0.3}, (0.0, 0.5)),
    ],
)
def test_policy_rate_bounds_reject_invalid_terms_and_keep_valid_limits(terms, expected):
    state = _state(globals_={"economic_health_terms": terms})
    assert EconomicHealthPanel()._policy_rate_bounds(state, "interest_rate") == expected


@pytest.mark.parametrize(
    ("value", "terms", "expected"),
    [
        (0.1, {"min_interest_rate": 0.2, "max_interest_rate": 0.4}, 0.2),
        (0.9, {"min_interest_rate": 0.2, "max_interest_rate": 0.4}, 0.4),
        ("bad", {}, 0.0),
        (float("inf"), {}, 0.0),
    ],
)
def test_policy_rate_clamping_handles_limits_and_bad_values(value, terms, expected):
    state = _state(globals_={"economic_health_terms": terms})
    assert EconomicHealthPanel()._clamp_policy_rate(state, "interest_rate", value) == expected


@pytest.mark.parametrize(
    ("position", "expected"),
    [
        (0.0, (0.0, 0.0, 0.0, 1.0)),
        (0.5, (0.5, 0.5, 0.5, 1.0)),
        (1.5, (1.0, 1.0, 1.0, 1.0)),
    ],
)
def test_gradient_color_interpolates_stops_and_returns_last_color_after_range(position, expected):
    stops = [(0.0, (0.0, 0.0, 0.0, 1.0)), (1.0, (1.0, 1.0, 1.0, 1.0))]
    assert EconomicHealthPanel._gradient_color(position, stops) == expected


def test_health_color_uses_three_threshold_bands():
    panel = EconomicHealthPanel()
    assert panel._health_color(0.75) == economic_panel_module.GAMETHEME.colors.positive
    assert panel._health_color(0.45) == economic_panel_module.GAMETHEME.colors.warning
    assert panel._health_color(0.44) == economic_panel_module.GAMETHEME.colors.negative


def test_initialize_policy_draft_reads_snapshot_and_only_resets_for_new_country():
    panel = EconomicHealthPanel()
    row = pl.DataFrame(
        [{"personal_income_tax_rate": 0.15, "budget_health_ratio": 0.65}]
    )
    view = SimpleNamespace(minimum_wage=1200.0, interest_rate=0.08)

    panel._initialize_policy_draft(row, view, "UKR")

    assert panel._current_policy_values() == {
        "minimum_wage": 1200.0,
        "interest_rate": 0.08,
        "personal_income_tax_rate": 0.15,
        "budget_health_ratio": 0.65,
    }
    panel._draft_minimum_wage = 1500.0
    panel._initialize_policy_draft(row, SimpleNamespace(minimum_wage=900.0, interest_rate=0.03), "UKR")
    assert panel._draft_minimum_wage == 1500.0
    panel._initialize_policy_draft(row, SimpleNamespace(minimum_wage=900.0, interest_rate=0.03), "POL")
    assert panel._draft_minimum_wage == 900.0
    assert panel._policy_baseline["minimum_wage"] == 900.0


def test_apply_policy_changes_dispatches_only_values_that_differ_from_baseline():
    panel = EconomicHealthPanel()
    panel._draft_minimum_wage = 1000.0
    panel._draft_interest_rate = 0.08
    panel._draft_tax_rate = 0.25
    panel._draft_health_spending = 0.5
    panel._policy_baseline = {
        "minimum_wage": 1000.0,
        "interest_rate": 0.05,
        "personal_income_tax_rate": 0.2,
        "budget_health_ratio": 0.5,
    }
    context, actions = _context()

    panel._apply_policy_changes(context)

    assert [type(action) for action in actions] == [ActionChangeEconomicPolicy, ActionSetTax]
    assert actions[0].policy_name == "interest_rate"
    assert actions[0].target_value == 0.08
    assert actions[1].new_tax_rate == 0.25
    assert panel._policy_baseline["interest_rate"] == 0.08
    assert panel._policy_baseline["personal_income_tax_rate"] == 0.25
    no_client, no_actions = _context(client=False)
    panel._apply_policy_changes(no_client)
    assert no_actions == []


def test_finish_close_discard_restores_baseline_and_apply_dispatches_changes():
    panel = EconomicHealthPanel()
    panel._policy_baseline = {
        "minimum_wage": 1000.0,
        "interest_rate": 0.05,
        "personal_income_tax_rate": 0.2,
        "budget_health_ratio": 0.5,
    }
    panel._draft_minimum_wage = 1500.0
    panel._draft_interest_rate = 0.1
    panel._draft_tax_rate = 0.3
    panel._draft_health_spending = 0.7
    context, actions = _context()

    panel._finish_close(CloseDecision.DISCARD, context)

    assert panel._current_policy_values() == panel._policy_baseline
    panel._draft_interest_rate = 0.08
    panel._finish_close(CloseDecision.APPLY, context)
    assert len(actions) == 1
    assert isinstance(actions[0], ActionChangeEconomicPolicy)


def test_policy_change_detection_uses_small_epsilon():
    panel = EconomicHealthPanel()
    panel._draft_minimum_wage = 1000.0
    panel._draft_interest_rate = 0.05
    panel._draft_tax_rate = 0.2
    panel._draft_health_spending = 0.5
    panel._policy_baseline = panel._current_policy_values()
    assert not panel._has_policy_changes()
    panel._draft_interest_rate += 1e-6
    assert panel._has_policy_changes()


def test_get_country_row_handles_missing_table_unknown_country_and_data(monkeypatch):
    panel = EconomicHealthPanel()
    assert panel._get_country_row(_state(), "UKR") is None
    state = _state({"countries": pl.DataFrame([{"id": "UKR", "name": "Ukraine"}])})
    assert panel._get_country_row(state, "UKR").item(0, "name") == "Ukraine"
    assert panel._get_country_row(state, "POL") is None
    broken = SimpleNamespace(tables={"countries": object()}, get_table=lambda _name: (_ for _ in ()).throw(RuntimeError()))
    assert panel._get_country_row(broken, "UKR") is None


class _FakeImGui:
    StyleVar_ = SimpleNamespace(item_spacing="item_spacing")

    def __init__(
        self,
        *,
        buttons=None,
        sliders=None,
        small_buttons=None,
        popups_open=False,
        menu_items=None,
        combo_open=False,
        selectables=None,
    ):
        self.buttons = buttons or {}
        self.sliders = sliders or {}
        self.small_buttons = small_buttons or {}
        self.popups_open = popups_open
        self.menu_items = menu_items or {}
        self.combo_open = combo_open
        self.selectables = selectables or {}
        self.calls = []
        self.draw_calls = []

    def __getattr__(self, name):
        if name in {"push_style_var", "pop_style_var", "push_text_wrap_pos", "pop_text_wrap_pos", "dummy", "text", "text_disabled", "text_wrapped", "text_colored", "same_line", "set_next_item_width", "end_disabled", "set_cursor_screen_pos", "end_combo"}:
            return lambda *args, **kwargs: self.calls.append((name, args, kwargs))
        if name in {"open_popup", "close_current_popup", "end_popup"}:
            return lambda *args, **kwargs: self.calls.append((name, args, kwargs))
        if name == "begin_popup":
            return lambda *args, **kwargs: self.popups_open
        if name == "menu_item":
            return lambda *_args, test_id=None, **_kwargs: (self.menu_items.get(test_id, False), False)
        if name in {"get_scroll_x", "get_scroll_y"}:
            return lambda: 0.0
        if name == "get_mouse_pos":
            return lambda: SimpleNamespace(x=150.0, y=0.0)
        if name == "get_color_u32":
            return lambda color: color
        if name == "get_window_draw_list":
            return lambda: SimpleNamespace(add_rect_filled=lambda *args: self.draw_calls.append(args))
        if name == "get_time":
            return lambda: 1.0
        raise AttributeError(name)

    def slider_float(self, label, value, *_args, test_id=None, **_kwargs):
        return self.sliders.get(test_id, (False, value))

    def button(self, _label, *_args, test_id=None, **_kwargs):
        return self.buttons.get(test_id, False)

    def begin_disabled(self, *args):
        self.calls.append(("begin_disabled", args))

    def end_disabled(self):
        self.calls.append(("end_disabled",))

    def same_line(self, *args, **kwargs):
        self.calls.append(("same_line", args, kwargs))

    def get_window_pos(self):
        return SimpleNamespace(x=10.0, y=20.0)

    def get_window_size(self):
        return SimpleNamespace(x=400.0, y=300.0)

    def calc_text_size(self, text):
        return SimpleNamespace(x=float(len(text) * 5))

    def begin_combo(self, *_args, **_kwargs):
        return self.combo_open

    def input_float(self, _label, value, *_args, **_kwargs):
        return False, value

    def selectable(self, label, *_args, **_kwargs):
        return self.selectables.get(label, False), False

    def small_button(self, label):
        return self.small_buttons.get(label, False)


def _country_row():
    return pl.DataFrame(
        [
            {
                "id": "UKR",
                "personal_income_tax_rate": 0.2,
                "budget_health_ratio": 0.5,
                "economic_health": 0.7,
                "tax_fairness_factor": 0.8,
                "total_annual_revenue": 100.0,
                "total_annual_expense": 80.0,
                "money_reserves": 40.0,
                "gdp": 1000.0,
            }
        ]
    )


def test_render_content_shows_empty_state_without_profile(monkeypatch):
    panel = EconomicHealthPanel()
    messages = []
    monkeypatch.setattr(economic_panel_module, "draw_empty_state", messages.append)
    panel._get_country_row = lambda *_args: None

    panel._render_content(_state(), PanelRenderContext("UKR", True))

    assert messages == ["No economic profile is available for this country."]


def test_render_content_routes_policy_page_and_restores_imgui_stacks(monkeypatch):
    panel = EconomicHealthPanel()
    panel._active_page = "policy"
    calls = []
    imgui = _FakeImGui()
    monkeypatch.setattr(economic_panel_module, "imgui", imgui)
    panel._get_country_row = lambda *_args: _country_row()
    panel._presenter.present = lambda *_args: object()
    panel._render_page_navigation = lambda: False
    panel._render_policy_controls = lambda *args: calls.append(args)

    panel._render_content(_state(), PanelRenderContext("UKR", True))

    assert len(calls) == 1
    assert calls[0][0].tables == {}
    assert calls[0][1].target_tag == "UKR"
    assert [call[0] for call in imgui.calls if call[0] in {"push_style_var", "pop_style_var", "push_text_wrap_pos", "pop_text_wrap_pos"}] == [
        "push_style_var",
        "push_text_wrap_pos",
        "pop_text_wrap_pos",
        "pop_style_var",
    ]


def test_policy_controls_dispatches_requested_wage_change(monkeypatch):
    panel = EconomicHealthPanel()
    imgui = _FakeImGui(buttons={"economic_health.schedule_wage": True})
    monkeypatch.setattr(economic_panel_module, "imgui", imgui)
    monkeypatch.setattr(economic_panel_module.Prims, "header", lambda *_args, **_kwargs: None)
    row = _country_row()
    state = _state(globals_={"economic_health_terms": {"max_minimum_wage": 2000.0}})
    view = SimpleNamespace(
        minimum_wage=1000.0,
        interest_rate=0.05,
        active_policies=[],
    )
    context, actions = _context()

    panel._render_policy_controls(state, context, view, row)

    assert len(actions) == 1
    assert isinstance(actions[0], ActionChangeEconomicPolicy)
    assert actions[0].policy_name == "minimum_wage"
    assert actions[0].target_value == 1000.0
    assert any(call[0] == "end_disabled" for call in imgui.calls)


def test_debt_controls_requests_financing_and_uses_a_valid_other_country(monkeypatch):
    panel = EconomicHealthPanel()
    imgui = _FakeImGui(buttons={"economic_health.request_financing": True})
    monkeypatch.setattr(economic_panel_module, "imgui", imgui)
    monkeypatch.setattr(economic_panel_module, "suspend_gml_layout", lambda: None)
    monkeypatch.setattr(economic_panel_module, "resume_gml_layout", lambda _token: None)
    state = _state(
        {
            "countries": pl.DataFrame([{"id": "UKR"}, {"id": "POL"}]),
            "debt_contracts": pl.DataFrame(
                schema={"id": pl.String, "creditor_country_id": pl.String, "status": pl.String}
            ),
        }
    )
    context, actions = _context()

    panel._render_debt_controls(state, context, SimpleNamespace(obligations=[]))

    assert len(actions) == 1
    assert isinstance(actions[0], ActionRequestDebtContract)
    assert actions[0].creditor_country_id == "POL"
    assert actions[0].principal == 1_000_000.0


def test_debt_controls_dispatches_creditor_decision_for_pending_request(monkeypatch):
    panel = EconomicHealthPanel()
    imgui = _FakeImGui(small_buttons={"Approve##request-1": True})
    monkeypatch.setattr(economic_panel_module, "imgui", imgui)
    monkeypatch.setattr(economic_panel_module, "suspend_gml_layout", lambda: None)
    monkeypatch.setattr(economic_panel_module, "resume_gml_layout", lambda _token: None)
    state = _state(
        {
            "countries": pl.DataFrame([{"id": "UKR"}, {"id": "POL"}]),
            "debt_contracts": pl.DataFrame(
                [
                    {
                        "id": "request-1",
                        "debtor_country_id": "POL",
                        "creditor_country_id": "UKR",
                        "principal_original": 500.0,
                        "status": "pending",
                    }
                ]
            ),
        }
    )
    context, actions = _context()

    panel._render_debt_controls(state, context, SimpleNamespace(obligations=[]))

    assert len(actions) == 1
    assert isinstance(actions[0], ActionResolveDebtContract)
    assert actions[0].contract_id == "request-1"
    assert actions[0].accept is True


class _FakeGMLWidgets:
    input_results = {}
    arrow_results = {}
    button_results = {}
    menu_button = False
    last = None

    def __init__(self, _layout):
        self.calls = []
        type(self).last = self

    def frame(self, *args, **kwargs):
        self.calls.append(("frame", args, kwargs))

    def text(self, *args, **kwargs):
        self.calls.append(("text", args, kwargs))

    def rule(self, *args, **kwargs):
        self.calls.append(("rule", args, kwargs))

    def input_float(self, path, label, value, test_id, **kwargs):
        self.calls.append(("input_float", test_id, value, kwargs))
        return type(self).input_results.get(test_id, (False, value))

    def arrow_button_state(self, path, direction, test_id, **kwargs):
        self.calls.append(("arrow", test_id, kwargs))
        return type(self).arrow_results.get(test_id, (False, False))

    def button(self, _path, _label, test_id, **kwargs):
        self.calls.append(("button", test_id, kwargs))
        return type(self).button_results.get(test_id, False)

    def button_at(self, *args, **kwargs):
        self.calls.append(("button_at", args, kwargs))
        return type(self).menu_button

    def rect(self, _path):
        return None


@pytest.fixture
def economic_ui(monkeypatch):
    _FakeGMLWidgets.input_results = {}
    _FakeGMLWidgets.arrow_results = {}
    _FakeGMLWidgets.button_results = {}
    _FakeGMLWidgets.menu_button = False
    monkeypatch.setattr(economic_panel_module, "GMLWidgets", _FakeGMLWidgets)
    return _FakeGMLWidgets


def test_source_rate_control_clamps_snapshot_value_and_tracks_both_repeat_buttons(monkeypatch, economic_ui):
    panel = EconomicHealthPanel()
    panel._draft_interest_rate = 0.9
    state = _state(globals_={"economic_health_terms": {"min_interest_rate": 0.02, "max_interest_rate": 0.25}})
    context, _ = _context()
    imgui = _FakeImGui()
    monkeypatch.setattr(economic_panel_module, "imgui", imgui)
    ui = economic_ui("rate")

    panel._render_source_rate_control(
        ui,
        state,
        context,
        value_name="interest_rate",
        label="Interest rate",
        test_prefix="rate",
        value_path="frmInterest",
    )

    assert panel._draft_interest_rate == 0.25
    assert [call[1] for call in ui.calls if call[0] == "arrow"] == ["rate.down", "rate.up"]


def test_source_content_formats_metrics_applies_rate_edits_and_opens_selected_page(
    monkeypatch, economic_ui
):
    panel = EconomicHealthPanel()
    imgui = _FakeImGui(
        buttons={"economic_health.apply": True},
        popups_open=True,
        menu_items={"economic_health.more.debt": True},
    )
    monkeypatch.setattr(economic_panel_module, "imgui", imgui)
    _FakeGMLWidgets.input_results = {
        "economic_health.interest.value": (True, 60.0),
        "economic_health.tax.value": (True, 35.0),
    }
    _FakeGMLWidgets.button_results = {"economic_health.apply": True}
    _FakeGMLWidgets.menu_button = True
    panel._draw_population_meter = lambda *_args: None
    panel._draw_inflation_meter = lambda *_args: None
    apply_calls = []
    panel._apply_policy_changes = lambda context: apply_calls.append(context)
    row = _country_row()
    state = _state(
        {"regions": pl.DataFrame([{"owner": "UKR", "pop_14": 10, "pop_15_64": 80, "pop_65": 10}])},
        {"economic_health_terms": {"max_interest_rate": 0.5, "max_personal_income_tax_rate": 0.4}},
    )
    view = SimpleNamespace(unemployment_rate=0.1, poverty_rate=0.2, inflation_rate=0.03)
    context, _ = _context()

    panel._render_source_content(state, context, row, view)

    assert panel._draft_interest_rate == 0.5
    assert panel._draft_tax_rate == 0.35
    assert apply_calls == [context]
    assert panel._active_page == "debt"
    capita = next(
        call for call in economic_ui.last.calls
        if call[0] == "text" and call[2].get("test_id") == "economic_health.gdp_per_capita"
    )
    assert capita[1][1] == "$ 10"
    assert any(call[0] == "close_current_popup" for call in imgui.calls)


def test_source_content_shows_na_when_population_is_missing(monkeypatch, economic_ui):
    panel = EconomicHealthPanel()
    monkeypatch.setattr(economic_panel_module, "imgui", _FakeImGui())
    panel._draw_population_meter = lambda *_args: None
    panel._draw_inflation_meter = lambda *_args: None
    panel._render_source_rate_control = lambda *_args, **_kwargs: None

    panel._render_source_content(
        _state(),
        PanelRenderContext("UKR", True),
        _country_row(),
        SimpleNamespace(unemployment_rate=0.1, poverty_rate=0.2, inflation_rate=0.03),
    )

    capita = next(
        call for call in economic_ui.last.calls
        if call[0] == "text" and call[2].get("test_id") == "economic_health.gdp_per_capita"
    )
    assert capita[1][1] == "N/A"


@pytest.mark.parametrize("page", ["policy", "debt"])
def test_render_content_routes_extended_pages_and_balances_imgui_stacks(monkeypatch, page):
    panel = EconomicHealthPanel()
    panel._active_page = page
    imgui = _FakeImGui()
    monkeypatch.setattr(economic_panel_module, "imgui", imgui)
    panel._get_country_row = lambda *_args: _country_row()
    panel._presenter.present = lambda *_args: object()
    panel._render_page_navigation = lambda: False
    routes = []
    panel._render_policy_controls = lambda *args: routes.append(("policy", args))
    panel._render_debt_controls = lambda *args: routes.append(("debt", args))

    panel._render_content(_state(), PanelRenderContext("UKR", True))

    assert routes[0][0] == page
    assert [call[0] for call in imgui.calls if call[0] in {"push_style_var", "pop_style_var", "push_text_wrap_pos", "pop_text_wrap_pos"}] == [
        "push_style_var",
        "push_text_wrap_pos",
        "pop_text_wrap_pos",
        "pop_style_var",
    ]


def test_render_content_overview_renders_trends_obligations_and_recent_causes(monkeypatch):
    panel = EconomicHealthPanel()
    imgui = _FakeImGui()
    monkeypatch.setattr(economic_panel_module, "imgui", imgui)
    monkeypatch.setattr(economic_panel_module.Prims, "header", lambda *_args, **_kwargs: None)
    panel._get_country_row = lambda *_args: _country_row()
    panel._presenter.present = lambda *_args: SimpleNamespace(
        minimum_wage=1000.0,
        interest_rate=0.05,
        inflation_rate=0.02,
        employment_rate=0.8,
        unemployment_rate=0.1,
        underemployment_rate=0.05,
        poverty_rate=0.2,
        labor_supply=100.0,
        employed_population=80.0,
        underemployed_population=5.0,
        nominal_income_index=1.1,
        real_income_index=1.0,
        migration_pressure=0.03,
        indicator_trends=[SimpleNamespace(indicator="economic_health", direction="up", delta=0.02)],
        domestic_debt=10.0,
        foreign_debt=20.0,
        annual_debt_service=5.0,
        arrears=1.0,
        distress_status="watch",
        recovery_condition="stable",
        fiscal_balance=20.0,
        risk_thresholds=[("reserve_coverage", 0.3)],
        obligations=[
            SimpleNamespace(
                contract_id="loan-1",
                creditor_country_id="POL",
                principal_remaining=10.0,
                next_payment_date="2027-01-01",
                maturity_date="2028-01-01",
                annual_interest_rate=0.05,
                arrears_amount=0.0,
                status="active",
            )
        ],
        top_causes=[SimpleNamespace(indicator="employment", delta=0.01, reason="Hiring improved")],
    )
    panel._render_page_navigation = lambda: False
    panel._draw_meter = lambda *_args: None
    panel._draw_money_row = lambda *_args: None

    panel._render_content(_state(), PanelRenderContext("UKR", True))

    text = [call[1][0] for call in imgui.calls if call[0] == "text"]
    disabled = [call[1][0] for call in imgui.calls if call[0] == "text_disabled"]
    assert any("Economic Health trend: up" in item for item in disabled)
    assert any("loan-1" in item for item in text)
    assert any("Hiring improved" in item for item in text)
    assert imgui.calls[-1][0] == "pop_style_var"


def test_page_navigation_clears_source_cursor_and_resumes_layout(monkeypatch):
    panel = EconomicHealthPanel()
    panel._population_cursor_values["poverty"] = (0.2, 0.5)
    imgui = _FakeImGui(buttons={"economic_health.page.source": True})
    monkeypatch.setattr(economic_panel_module, "imgui", imgui)
    monkeypatch.setattr(economic_panel_module, "active_gml_layout", lambda: None)
    resumed = []
    monkeypatch.setattr(economic_panel_module, "suspend_gml_layout", lambda: "token")
    monkeypatch.setattr(economic_panel_module, "resume_gml_layout", resumed.append)

    assert panel._render_page_navigation() is True

    assert panel._active_page == "source"
    assert panel._population_cursor_values == {}
    assert resumed == ["token"]


def test_page_navigation_changes_extended_page_without_closing_window(monkeypatch):
    panel = EconomicHealthPanel()
    imgui = _FakeImGui(buttons={"economic_health.page.policy": True})
    monkeypatch.setattr(economic_panel_module, "imgui", imgui)
    monkeypatch.setattr(economic_panel_module, "active_gml_layout", lambda: None)
    monkeypatch.setattr(economic_panel_module, "suspend_gml_layout", lambda: None)
    monkeypatch.setattr(economic_panel_module, "resume_gml_layout", lambda _token: None)

    assert panel._render_page_navigation() is False
    assert panel._active_page == "policy"


def test_population_meter_tracks_cursor_only_while_dragged(monkeypatch):
    panel = EconomicHealthPanel()
    track = SimpleNamespace(x=10.0, y=5.0, width=108.0, height=10.0)
    ui = SimpleNamespace(
        rect=lambda _path: track,
        hitbox_state=lambda *_args, **_kwargs: (False, True),
    )
    session = SimpleNamespace(window_position=(100.0, 200.0))
    imgui = _FakeImGui()
    monkeypatch.setattr(economic_panel_module, "active_gml_layout", lambda: session)
    monkeypatch.setattr(economic_panel_module, "imgui", imgui)

    panel._draw_population_meter(ui, "meter", 0.4, "poverty")

    assert panel._population_cursor_values["poverty"] == (0.4, pytest.approx(0.4))
    assert len(imgui.draw_calls) == 2


def test_inflation_meter_draws_gradient_and_clamps_marker_position(monkeypatch):
    panel = EconomicHealthPanel()
    marker_path = "frmInner/frmInflation/picDelimiter"

    class Layout:
        window_position = (100.0, 200.0)

        def __init__(self):
            self.rects = {
                "frmInner/frmInflation/frmInflation/picGradient": SimpleNamespace(x=0.0, y=0.0, width=120.0, height=12.0),
                marker_path: SimpleNamespace(x=5.0, y=2.0, width=4.0, height=14.0),
                "frmInner/frmInflation": SimpleNamespace(x=3.0),
            }

        def move_component(self, path, *, x):
            self.rects[path].x = x

    session = Layout()
    ui = SimpleNamespace(rect=lambda path: session.rects.get(path))
    imgui = _FakeImGui()
    monkeypatch.setattr(economic_panel_module, "active_gml_layout", lambda: session)
    monkeypatch.setattr(economic_panel_module, "imgui", imgui)

    panel._draw_inflation_meter(ui, 1.0)

    assert len(imgui.draw_calls) == 13
    assert session.rects[marker_path].x > 0.0


def test_render_routes_source_page_through_window_and_clears_cursor_when_closed(monkeypatch):
    panel = EconomicHealthPanel()
    panel._population_cursor_values["unemployment"] = (0.1, 0.4)
    panel._get_country_row = lambda *_args: None
    panel._presenter.present = lambda *_args: None
    window_arguments = {}

    from contextlib import contextmanager

    @contextmanager
    def window(*args, **kwargs):
        window_arguments["args"] = args
        window_arguments.update(kwargs)
        yield False

    monkeypatch.setattr(economic_panel_module.WindowManager, "window", window)
    panel._has_policy_changes = lambda: False
    panel._close_confirmation.render = lambda *_args, **_kwargs: None

    assert panel.render(_state(), PanelRenderContext("UKR", True)) is False

    assert window_arguments["test_id"] == "economic_health.panel"
    assert panel._population_cursor_values == {}


def test_render_extended_page_routes_overview_and_returns_to_source_after_close(monkeypatch):
    panel = EconomicHealthPanel()
    panel._active_page = "overview"
    contents = []

    from contextlib import contextmanager

    @contextmanager
    def window(*_args, **_kwargs):
        yield True

    monkeypatch.setattr(economic_panel_module.WindowManager, "window", window)
    panel._render_content = lambda *args: contents.append(args)
    panel._close_confirmation.render = lambda *_args, **_kwargs: None
    context = PanelRenderContext("UKR", True)

    assert panel.render(_state(), context) is True
    assert len(contents) == 1
    panel._active_page = "policy"

    @contextmanager
    def closed_window(*_args, **_kwargs):
        yield False

    monkeypatch.setattr(economic_panel_module.WindowManager, "window", closed_window)
    assert panel._render_extended_window(_state(), context, navigation_close=False) is True
    assert panel._active_page == "source"


def _install_window(monkeypatch, opened):
    @contextmanager
    def window(*_args, **_kwargs):
        yield opened

    monkeypatch.setattr(economic_panel_module.WindowManager, "window", window)


def test_source_window_initializes_draft_renders_and_handles_both_close_decisions(monkeypatch):
    state = _state({"countries": _country_row()})
    context, _ = _context()
    view = SimpleNamespace(minimum_wage=1000.0, interest_rate=0.05)

    panel = EconomicHealthPanel()
    panel._presenter.present = lambda *_args: view
    content_calls = []
    panel._render_source_content = lambda *args: content_calls.append(args)
    panel._close_confirmation.render = lambda *_args, **_kwargs: None
    _install_window(monkeypatch, True)

    assert panel._render_source_window(state, context, navigation_close=False) is True
    assert panel._draft_country_id == "UKR"
    assert len(content_calls) == 1

    panel = EconomicHealthPanel()
    panel._initialize_policy_draft(_country_row(), view, "UKR")
    panel._presenter.present = lambda *_args: view
    panel._draft_interest_rate += 0.1
    finish_calls = []
    panel._finish_close = lambda *args: finish_calls.append(args)
    panel._close_confirmation.request_close = lambda *_args, **_kwargs: CloseDecision.DISCARD
    _install_window(monkeypatch, False)

    assert panel._render_source_window(state, context, navigation_close=False) is False
    assert finish_calls[0][0] is CloseDecision.DISCARD

    panel._draft_interest_rate += 0.1
    panel._close_confirmation.request_close = lambda *_args, **_kwargs: None
    panel._close_confirmation.render = lambda *_args, **_kwargs: CloseDecision.APPLY
    _install_window(monkeypatch, True)

    assert panel._render_source_window(state, context, navigation_close=True) is False
    assert finish_calls[-1][0] is CloseDecision.APPLY


def test_extended_window_applies_close_confirmation_and_resets_to_source(monkeypatch):
    context, _ = _context()
    panel = EconomicHealthPanel()
    panel._active_page = "debt"
    panel._policy_baseline = panel._current_policy_values()
    panel._draft_interest_rate += 0.1
    finish_calls = []
    panel._finish_close = lambda *args: finish_calls.append(args)
    panel._close_confirmation.request_close = lambda *_args, **_kwargs: CloseDecision.DISCARD
    _install_window(monkeypatch, False)

    assert panel._render_extended_window(_state(), context, navigation_close=False) is False
    assert panel._active_page == "source"
    assert finish_calls[0][0] is CloseDecision.DISCARD

    panel = EconomicHealthPanel()
    panel._active_page = "policy"
    panel._finish_close = lambda *args: finish_calls.append(args)
    panel._close_confirmation.render = lambda *_args, **_kwargs: CloseDecision.DISCARD
    _install_window(monkeypatch, False)

    assert panel._render_extended_window(_state(), context, navigation_close=False) is False
    assert panel._active_page == "source"
    assert finish_calls[-1][0] is CloseDecision.DISCARD


def test_source_content_reports_missing_profile_and_routes_each_extended_menu_item(
    monkeypatch, economic_ui
):
    panel = EconomicHealthPanel()
    empty_messages = []
    monkeypatch.setattr(economic_panel_module, "draw_empty_state", empty_messages.append)
    panel._render_source_content(_state(), PanelRenderContext("UKR", True), None, None)
    assert empty_messages == ["No economic profile is available for this country."]

    menu_pages = (
        ("economic_health.more.overview", "overview"),
        ("economic_health.more.policy", "policy"),
        ("economic_health.more.debt", "debt"),
    )
    for menu_id, page in menu_pages:
        panel = EconomicHealthPanel()
        panel._render_source_rate_control = lambda *_args, **_kwargs: None
        panel._draw_population_meter = lambda *_args: None
        panel._draw_inflation_meter = lambda *_args: None
        _FakeGMLWidgets.menu_button = True
        monkeypatch.setattr(
            economic_panel_module,
            "imgui",
            _FakeImGui(popups_open=True, menu_items={menu_id: True}),
        )
        panel._render_source_content(
            _state(),
            PanelRenderContext("UKR", True),
            _country_row(),
            SimpleNamespace(unemployment_rate=0.1, poverty_rate=0.2, inflation_rate=0.03),
        )
        assert panel._active_page == page


def test_source_rate_control_applies_tax_arrow_adjustment(monkeypatch, economic_ui):
    panel = EconomicHealthPanel()
    panel._draft_tax_rate = 0.2
    _FakeGMLWidgets.arrow_results = {"tax.down": (True, False)}
    monkeypatch.setattr(economic_panel_module, "imgui", _FakeImGui())

    panel._render_source_rate_control(
        economic_ui("rate"),
        _state(),
        _context()[0],
        value_name="personal_income_tax_rate",
        label="Personal income tax",
        test_prefix="tax",
        value_path="frmTax",
    )

    assert panel._draft_tax_rate == pytest.approx(0.199)

    panel._draft_interest_rate = 0.05
    _FakeGMLWidgets.arrow_results = {"interest.up": (True, False)}
    panel._render_source_rate_control(
        economic_ui("rate"),
        _state(),
        _context()[0],
        value_name="interest_rate",
        label="Interest rate",
        test_prefix="interest",
        value_path="frmInterest",
    )
    assert panel._draft_interest_rate == pytest.approx(0.051)


def test_meter_helpers_and_missing_layout_guards(monkeypatch):
    panel = EconomicHealthPanel()
    imgui = _FakeImGui()
    monkeypatch.setattr(economic_panel_module, "imgui", imgui)
    monkeypatch.setattr(economic_panel_module, "active_gml_layout", lambda: None)
    panel._draw_population_meter(SimpleNamespace(rect=lambda _path: None), "meter", 0.4, "poverty")
    panel._draw_inflation_meter(SimpleNamespace(rect=lambda _path: None), 0.2)

    meter_calls = []
    money_calls = []
    monkeypatch.setattr(economic_panel_module.Prims, "meter", lambda *args: meter_calls.append(args))
    monkeypatch.setattr(
        economic_panel_module.Prims,
        "right_align_text",
        lambda *args: money_calls.append(args),
    )
    color = (0.2, 0.3, 0.4, 1.0)
    panel._draw_meter("Health", 1.5, color)
    panel._draw_money_row("Revenue", 12.0, color)

    assert meter_calls == [("", 100.0, color)]
    assert money_calls[0][1] == color
    assert any(call[0] == "text_colored" for call in imgui.calls)


def test_render_content_returns_after_navigation_and_handles_no_recent_causes(monkeypatch):
    panel = EconomicHealthPanel()
    imgui = _FakeImGui()
    monkeypatch.setattr(economic_panel_module, "imgui", imgui)
    panel._get_country_row = lambda *_args: _country_row()
    panel._presenter.present = lambda *_args: SimpleNamespace()
    panel._render_page_navigation = lambda: True

    panel._render_content(_state(), PanelRenderContext("UKR", True))

    assert [call[0] for call in imgui.calls] == ["push_style_var", "pop_style_var"]

    panel._render_page_navigation = lambda: False
    panel._presenter.present = lambda *_args: SimpleNamespace(
        minimum_wage=1000.0,
        interest_rate=0.05,
        inflation_rate=0.02,
        employment_rate=0.8,
        unemployment_rate=0.1,
        underemployment_rate=0.05,
        poverty_rate=0.2,
        labor_supply=100.0,
        employed_population=80.0,
        underemployed_population=5.0,
        nominal_income_index=1.1,
        real_income_index=1.0,
        migration_pressure=0.03,
        indicator_trends=[],
        domestic_debt=10.0,
        foreign_debt=20.0,
        annual_debt_service=5.0,
        arrears=1.0,
        distress_status="watch",
        recovery_condition="stable",
        fiscal_balance=20.0,
        risk_thresholds=[],
        obligations=[],
        top_causes=[],
    )
    monkeypatch.setattr(economic_panel_module.Prims, "header", lambda *_args, **_kwargs: None)
    panel._draw_meter = lambda *_args: None
    panel._draw_money_row = lambda *_args: None

    panel._render_content(_state(), PanelRenderContext("UKR", True))

    assert any(
        call[0] == "text_disabled" and call[1][0] == "No recorded economic changes yet."
        for call in imgui.calls
    )


def test_policy_controls_dispatches_all_policy_types_and_lists_active_policies(monkeypatch):
    panel = EconomicHealthPanel()
    imgui = _FakeImGui(
        buttons={
            "economic_health.schedule_interest": True,
            "economic_health.schedule_tax": True,
            "economic_health.schedule_health": True,
        }
    )
    monkeypatch.setattr(economic_panel_module, "imgui", imgui)
    monkeypatch.setattr(economic_panel_module.Prims, "header", lambda *_args, **_kwargs: None)
    view = SimpleNamespace(
        minimum_wage=1000.0,
        interest_rate=0.05,
        active_policies=[
            SimpleNamespace(policy_name="interest_rate", target_value=0.06, transition_cost=10.0, effective_date="2027-01-01")
        ],
    )
    context, actions = _context()

    panel._render_policy_controls(_state(), context, view, _country_row())

    assert [type(action) for action in actions] == [
        ActionChangeEconomicPolicy,
        ActionSetTax,
        ActionChangeEconomicPolicy,
    ]
    assert [action.policy_name for action in actions if isinstance(action, ActionChangeEconomicPolicy)] == [
        "interest_rate",
        "budget_health_ratio",
    ]
    assert any(call[0] == "text_wrapped" for call in imgui.calls)


def test_debt_controls_selects_creditor_restructures_and_handles_unavailable_actions(monkeypatch):
    panel = EconomicHealthPanel()
    panel._creditor_country_id = "POL"
    imgui = _FakeImGui(
        combo_open=True,
        selectables={"CZE": True},
        small_buttons={"Request restructure##loan-1": True},
    )
    monkeypatch.setattr(economic_panel_module, "imgui", imgui)
    monkeypatch.setattr(economic_panel_module, "suspend_gml_layout", lambda: None)
    monkeypatch.setattr(economic_panel_module, "resume_gml_layout", lambda _token: None)
    state = _state({"countries": pl.DataFrame([{"id": "UKR"}, {"id": "POL"}, {"id": "CZE"}])})
    context, actions = _context()
    obligation = SimpleNamespace(
        status="arrears",
        contract_id="loan-1",
        annual_interest_rate=0.08,
        principal_remaining=2400.0,
    )

    panel._render_debt_controls(state, context, SimpleNamespace(obligations=[obligation]))

    assert panel._creditor_country_id == "CZE"
    assert len(actions) == 1
    assert isinstance(actions[0], ActionRequestDebtRestructuring)

    panel._render_debt_controls(_state(), context, SimpleNamespace(obligations=[]))
    assert len(imgui.calls) > 0


def test_debt_controls_rejects_pending_credit_request(monkeypatch):
    imgui = _FakeImGui(small_buttons={"Reject##request-2": True})
    monkeypatch.setattr(economic_panel_module, "imgui", imgui)
    monkeypatch.setattr(economic_panel_module, "suspend_gml_layout", lambda: None)
    monkeypatch.setattr(economic_panel_module, "resume_gml_layout", lambda _token: None)
    state = _state(
        {
            "countries": pl.DataFrame([{"id": "UKR"}, {"id": "POL"}]),
            "debt_contracts": pl.DataFrame(
                [
                    {
                        "id": "request-2",
                        "debtor_country_id": "POL",
                        "creditor_country_id": "UKR",
                        "principal_original": 500.0,
                        "status": "pending",
                    }
                ]
            ),
        }
    )
    context, actions = _context()

    EconomicHealthPanel()._render_debt_controls(state, context, SimpleNamespace(obligations=[]))

    assert len(actions) == 1
    assert isinstance(actions[0], ActionResolveDebtContract)
    assert actions[0].accept is False


def test_population_and_resource_coverage_fail_safely_on_bad_snapshots():
    panel = EconomicHealthPanel()

    class BrokenRegions:
        columns = ("owner", "pop_14", "pop_15_64", "pop_65")

        @staticmethod
        def filter(*_args, **_kwargs):
            raise RuntimeError("invalid region snapshot")

    assert panel._country_population(SimpleNamespace(tables={"regions": BrokenRegions()}), "UKR") is None

    state = _state({"resource_ledger": pl.DataFrame([{"country_id": "UKR"}])})
    state.get_table = lambda _name: (_ for _ in ()).throw(RuntimeError("invalid ledger"))
    assert panel._resource_coverage(state, "UKR") == 0.0
