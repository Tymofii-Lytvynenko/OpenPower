from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import polars as pl
import pytest

import src.client.ui.panels.trade_panel as trade_panel_module
from src.client.ui.core.panel_context import PanelRenderContext
from src.client.ui.panels.trade_panel import TradePanel
from src.shared.actions import ActionCounterTradeDeal, ActionCreateTradeDeal


def _state(tables=None, results=None):
    return SimpleNamespace(
        tables=tables or {},
        journal=SimpleNamespace(command_results=list(results or [])),
    )


def _context(player_id="UKR"):
    actions = []
    client = SimpleNamespace(player_id=player_id, send_action=actions.append)
    return PanelRenderContext("UKR", True, net_client=client), actions


def test_request_deal_selects_requested_deal_and_deal_page():
    panel = TradePanel()

    panel.request_deal("deal-2")

    assert panel._requested_deal_id == "deal-2"
    assert panel._selected_deal_id == "deal-2"
    assert panel.active_page == "deal"


@pytest.mark.parametrize("active_page,template", [("offers", "Trade_Window"), ("proposal", "Trade_Detailed_Window")])
@pytest.mark.parametrize("open_window", [True, False])
def test_render_selects_matching_template_and_respects_window_lifecycle(
    monkeypatch, active_page, template, open_window
):
    panel = TradePanel()
    panel.active_page = active_page
    layouts = []
    contents = []
    monkeypatch.setattr(
        trade_panel_module,
        "get_gml_layout",
        lambda value: layouts.append(value) or SimpleNamespace(width=400, height=300),
    )
    monkeypatch.setattr(
        trade_panel_module.imgui,
        "get_main_viewport",
        lambda: SimpleNamespace(size=SimpleNamespace(x=1000, y=800)),
    )

    @contextmanager
    def window(*_args, **_kwargs):
        yield open_window

    monkeypatch.setattr(trade_panel_module.WindowManager, "window", window)
    panel._render_content = lambda state, context: contents.append((state, context))
    state = _state()
    context, _ = _context()

    assert panel.render(state, context) is open_window
    assert layouts == [template]
    assert len(contents) == int(open_window)


def test_country_deals_filter_and_sort_pending_then_newest_first():
    panel = TradePanel()
    state = _state(
        {
            "diplomatic_trade_deals": pl.DataFrame(
                [
                    {"id": "old", "source_country_id": "UKR", "target_country_id": "POL", "status": "pending", "created_at_minute": 5},
                    {"id": "new", "source_country_id": "POL", "target_country_id": "UKR", "status": "pending", "created_at_minute": 10},
                    {"id": "resolved", "source_country_id": "UKR", "target_country_id": "FRA", "status": "accepted", "created_at_minute": 20},
                    {"id": "other", "source_country_id": "POL", "target_country_id": "FRA", "status": "pending", "created_at_minute": 30},
                ]
            )
        }
    )

    assert [row["id"] for row in panel._country_deals(state, "UKR")] == [
        "new",
        "old",
        "resolved",
    ]


@pytest.mark.parametrize(
    ("asset", "tables", "expected"),
    [
        ({"type": "cash", "amount": "1200.5"}, {}, "Cash 1,200"),
        ({"type": "technology", "branch": "air_defense", "level": "3"}, {}, "Technology: Air Defense to level 3"),
        (
            {"type": "territory", "region_id": 2},
            {"regions": pl.DataFrame([{"id": 2, "name": "Lviv"}])},
            "Region: Lviv (2)",
        ),
        ({"type": "territory", "region_id": 9}, {}, "Region 9"),
        ({"type": "unknown", "value": 1}, {}, "{'type': 'unknown', 'value': 1}"),
    ],
)
def test_asset_label_formats_supported_and_fallback_assets(asset, tables, expected):
    assert TradePanel()._asset_label(_state(tables), asset) == expected


def test_asset_collection_helpers_deduplicate_regions_and_technology_branches():
    assets = [{"type": "territory", "region_id": 3}, {"type": "technology", "branch": "air"}]
    panel = TradePanel()

    panel._append_unique(assets, {"type": "territory", "region_id": 3, "extra": True})
    panel._append_unique(assets, {"type": "territory", "region_id": 4})
    panel._append_unique(assets, {"type": "technology", "branch": "naval"})

    assert len(panel._asset_rows(assets)) == 4
    assert [row.get("region_id", row.get("branch")) for row in assets] == [3, "air", 4, "naval"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('[{"type":"cash","amount":5}]', [{"type": "cash", "amount": 5}]),
        ("not-json", []),
        ('{"type":"cash"}', []),
        (None, []),
    ],
)
def test_asset_decoder_accepts_lists_and_rejects_invalid_payloads(raw, expected):
    assert TradePanel._decode_assets(raw) == expected


@pytest.mark.parametrize(
    ("wars", "expected"),
    [
        ([{"status": "active", "side_a": ["ukr"], "side_b": ["pol"]}], True),
        ([{"status": "ended", "side_a": ["UKR"], "side_b": ["POL"]}], False),
        ([{"side_a": ["UKR"], "side_b": ["POL"]}], True),
        ([{"status": "active", "side_a": ["UKR"], "side_b": ["FRA"]}], False),
        ([], False),
    ],
)
def test_country_at_war_only_matches_active_opposing_sides(wars, expected):
    assert TradePanel()._country_at_war(
        _state({"countries_wars": pl.DataFrame(wars)}), "UKR", "POL"
    ) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("3.5", 3.5), ("invalid", 0.0), (float("inf"), 0.0), (None, 0.0)],
)
def test_number_conversion_rejects_invalid_and_nonfinite_values(value, expected):
    assert TradePanel._number(value) == expected


def test_reset_package_clears_draft_fields_and_can_preserve_counter_link():
    panel = TradePanel()
    panel.offered_assets.append({"type": "cash", "amount": 10})
    panel.requested_assets.append({"type": "territory", "region_id": 2})
    panel.offer_cash = panel.request_cash = 10
    panel.offer_region_idx = panel.request_region_idx = 2
    panel.offer_technology_idx = panel.request_technology_idx = 1
    panel.offer_technology_level = panel.request_technology_level = 3
    panel.counter_to_deal_id = "deal-1"

    panel._reset_package(keep_counter=True)

    assert panel.offered_assets == []
    assert panel.requested_assets == []
    assert panel.offer_cash == panel.request_cash == 0.0
    assert panel.offer_region_idx == panel.request_region_idx == 0
    assert panel.offer_technology_idx == panel.request_technology_idx == 0
    assert panel.offer_technology_level == panel.request_technology_level == 0
    assert panel.counter_to_deal_id == "deal-1"
    panel._reset_package()
    assert panel.counter_to_deal_id == ""


def test_send_proposal_dispatches_create_action_and_resets_the_draft():
    panel = TradePanel()
    panel.offered_assets = [{"type": "cash", "amount": 50}]
    panel.requested_assets = [{"type": "territory", "region_id": 8}]
    panel.expiry_days = 14
    context, actions = _context()

    panel._send_proposal(context, "UKR", "POL")

    assert len(actions) == 1
    assert isinstance(actions[0], ActionCreateTradeDeal)
    assert actions[0].offered_assets == [{"type": "cash", "amount": 50}]
    assert actions[0].requested_assets == [{"type": "territory", "region_id": 8}]
    assert actions[0].expires_after_days == 14
    assert panel.offered_assets == []
    assert panel.active_page == "offers"


def test_latest_action_result_is_scoped_to_the_current_player_and_trade_actions():
    state = _state(
        results=[
            {"player_id": "other", "action_type": "ActionCreateTradeDeal", "status": "applied"},
            {"player_id": "UKR", "action_type": "ActionSetCountryCapital", "status": "applied"},
            {"player_id": "UKR", "action_type": "ActionRespondTradeDeal", "status": "rejected", "reason": "Deal expired"},
        ]
    )
    context, _ = _context()

    assert TradePanel()._latest_action_result(state, context) == state.journal.command_results[-1]
    assert TradePanel()._latest_action_result(state, None) is None


class _FakeWidgets:
    button_results = {}
    last = None

    def __init__(self, path):
        self.root = path
        self.calls = []
        type(self).last = self

    def path(self, name):
        return f"{self.root}/{name}"

    def text(self, *args, **kwargs):
        self.calls.append(("text", args, kwargs))

    def meter(self, *args, **kwargs):
        self.calls.append(("meter", args, kwargs))

    def button(self, _path, _label, test_id, **kwargs):
        self.calls.append(("button", test_id, kwargs))
        return kwargs.get("enabled", True) and type(self).button_results.get(test_id, False)


class _FakeImGui:
    StyleVar_ = SimpleNamespace(frame_padding="frame_padding")

    def __init__(self, *, cash_result=(False, 0.0), combo_results=None):
        self.cash_result = cash_result
        self.combo_results = combo_results or {}
        self.calls = []

    def push_style_var(self, *args):
        self.calls.append(("push", args))

    def pop_style_var(self, *args):
        self.calls.append(("pop", args))

    def begin_disabled(self, *args):
        self.calls.append(("begin_disabled", args))

    def end_disabled(self):
        self.calls.append(("end_disabled",))

    def input_float(self, *_args, **kwargs):
        self.calls.append(("input_float", kwargs))
        return self.cash_result

    def combo(self, _label, index, _items, *, test_id, **_kwargs):
        self.calls.append(("combo", test_id, index))
        return self.combo_results.get(test_id, (False, index))


class _FlowWidgets:
    button_results = {}
    last = None

    def __init__(self, root):
        self.root = root
        self.calls = []
        type(self).last = self

    def path(self, slot):
        return f"{self.root}/{slot}"

    def text(self, *args, **kwargs):
        self.calls.append(("text", args, kwargs))

    def text_at(self, *args, **kwargs):
        self.calls.append(("text_at", args, kwargs))

    def meter(self, *args, **kwargs):
        self.calls.append(("meter", args, kwargs))

    def rect(self, slot):
        self.calls.append(("rect", slot))
        return SimpleNamespace(x=4.0, y=5.0, width=210.0, height=20.0)

    def button(self, _path, _label, test_id, **kwargs):
        self.calls.append(("button", test_id, kwargs))
        return kwargs.get("enabled", True) and type(self).button_results.get(test_id, False)


def test_proposal_content_resets_country_draft_and_routes_partner_availability(monkeypatch, trade_ui):
    panel = TradePanel()
    panel._draft_country = "POL"
    panel.offered_assets.append({"type": "cash", "amount": 50})
    panel.counter_to_deal_id = "old-deal"
    panel._draw_title_action_icon = Mock()
    panel._render_country_header = Mock()
    panel._render_package_editor = Mock()
    panel._render_balance = Mock()
    monkeypatch.setattr(trade_panel_module, "draw_gml_separator", Mock())
    monkeypatch.setattr(panel, "_country_options", lambda *_args: [("POL", "Poland")])
    monkeypatch.setattr(panel, "_country_at_war", lambda *_args: False)
    monkeypatch.setattr(trade_panel_module, "imgui", _FakeImGui())
    state = _state()
    context, _actions = _context()

    panel._render_content(state, context)

    assert panel._draft_country == "UKR"
    assert panel.offered_assets == []
    assert panel.counter_to_deal_id == ""
    assert panel.partner_tag == "POL"
    panel._render_package_editor.assert_called_once_with(state, context, "UKR", "POL")

    panel.partner_tag = ""
    monkeypatch.setattr(panel, "_country_options", lambda *_args: [])
    panel._render_content(state, context)
    assert panel._render_balance.call_args.args[1] == "No trade partners are available."


def test_proposal_content_discards_counteroffer_when_server_resolves_it(monkeypatch, trade_ui):
    panel = TradePanel()
    panel._draft_country = "UKR"
    panel.counter_to_deal_id = "deal-1"
    panel.partner_tag = "POL"
    panel._render_country_header = Mock()
    panel._render_balance = Mock()
    panel._render_trade_offer_list = Mock()
    panel._render_package_editor = Mock()
    panel._draw_title_action_icon = Mock()
    monkeypatch.setattr(trade_panel_module, "draw_gml_separator", Mock())
    monkeypatch.setattr(panel, "_country_options", lambda *_args: [("POL", "Poland")])
    monkeypatch.setattr(trade_panel_module, "imgui", _FakeImGui())
    state = _state({"diplomatic_trade_deals": pl.DataFrame([{
        "id": "deal-1", "status": "accepted", "expires_at_minute": 100,
    }])})
    state.time = SimpleNamespace(total_minutes=10)
    context, _actions = _context()

    panel._render_content(state, context)

    assert panel.active_page == "offers"
    assert panel.counter_to_deal_id == ""
    panel._render_balance.assert_called_once_with(
        state, "The original offer is no longer pending.", context
    )
    panel._render_trade_offer_list.assert_not_called()


def test_country_header_selects_asset_category_from_gml_layout(monkeypatch):
    panel = TradePanel()
    panel.asset_category = "invalid"
    ui = _FlowWidgets("Trade_Detailed_Window/frmInner/frmSideA")
    monkeypatch.setattr(trade_panel_module, "GMLWidgets", lambda _root: ui)
    layout = SimpleNamespace(window_position=(100.0, 200.0))
    monkeypatch.setattr(trade_panel_module, "active_gml_layout", lambda: layout)
    imgui = SimpleNamespace(
        set_cursor_screen_pos=Mock(),
        set_next_item_width=Mock(),
        combo=Mock(return_value=(True, 1)),
    )
    monkeypatch.setattr(trade_panel_module, "imgui", imgui)

    panel._render_country_header(_state(), "UKR", SimpleNamespace())

    assert ui.calls[0] == ("text", ("txtCountry", "YOU GIVE · UKR"), {"test_id": "trade.offer.country"})
    imgui.set_cursor_screen_pos.assert_called_once_with((254.0, 205.0))
    imgui.set_next_item_width.assert_called_once_with(80.0)
    assert panel.asset_category == "region"


def test_balance_displays_cash_totals_and_latest_action_reason(monkeypatch):
    panel = TradePanel()
    panel.offered_assets = [{"type": "cash", "amount": 125.0}, {"type": "territory", "region_id": 1}]
    panel.requested_assets = [{"type": "cash", "amount": 75.0}]
    monkeypatch.setattr(trade_panel_module, "GMLWidgets", _FlowWidgets)
    context, _actions = _context()
    state = _state(results=[{
        "player_id": "UKR", "action_type": "ActionCreateTradeDeal",
        "status": "rejected", "reason": "The target has no funds.",
    }])

    panel._render_balance(state, context=context)

    texts = [call for call in _FlowWidgets.last.calls if call[0] == "text"]
    assert texts[0][1] == ("lblBalance", "Last action: rejected")
    assert texts[0][2]["tooltip"] == "The target has no funds."
    assert texts[1][1] == ("txtPriceA", "−$125")
    assert texts[2][1] == ("txtPriceB", "+$75")
    meter = next(call for call in _FlowWidgets.last.calls if call[0] == "meter")
    assert meter[1][1] == 0.625


def test_package_editor_clamps_expiry_and_sends_only_a_nonempty_package(monkeypatch):
    panel = TradePanel()
    panel.expiry_days = 400.0
    panel.offered_assets = [{"type": "cash", "amount": 100.0}]
    panel._render_asset_side = Mock()
    panel._render_balance = Mock()
    panel._send_proposal = Mock()
    _FlowWidgets.button_results = {"trade.send": True}
    monkeypatch.setattr(trade_panel_module, "GMLWidgets", _FlowWidgets)
    layout = SimpleNamespace(
        window_position=(100.0, 200.0),
        rect_for=Mock(return_value=SimpleNamespace(x=20.0, y=30.0)),
    )
    monkeypatch.setattr(trade_panel_module, "active_gml_layout", lambda: layout)
    imgui = SimpleNamespace(
        set_cursor_screen_pos=Mock(),
        set_next_item_width=Mock(),
        text_disabled=Mock(),
        input_int=Mock(return_value=(True, 450)),
    )
    monkeypatch.setattr(trade_panel_module, "imgui", imgui)
    context, _actions = _context()

    panel._render_package_editor(_state(), context, "UKR", "POL")

    assert panel.expiry_days == 365.0
    panel._send_proposal.assert_called_once_with(context, "UKR", "POL")
    assert imgui.input_int.call_args.kwargs["test_id"] == "trade.expiry_days"
    assert imgui.set_cursor_screen_pos.call_args_list[0].args == ((31.0, 188.0),)


def test_asset_list_selects_then_removes_or_clears_items(monkeypatch):
    panel = TradePanel()
    assets = [
        {"type": "cash", "amount": 10.0},
        {"type": "cash", "amount": 20.0},
    ]
    panel._selected_asset_index["offer"] = 1
    monkeypatch.setattr(panel, "_asset_label", lambda _state, asset: str(asset["amount"]))
    imgui = MagicMock()
    imgui.begin_child.return_value = True
    imgui.selectable.return_value = (False, False)
    imgui.button.side_effect = [True, False]
    monkeypatch.setattr(trade_panel_module, "imgui", imgui)

    panel._render_asset_list(_state(), assets, "offer", "root")

    assert assets == [{"type": "cash", "amount": 10.0}]
    assert panel._selected_asset_index["offer"] == 0

    imgui.button.side_effect = [False, True]
    panel._render_asset_list(_state(), assets, "offer", "root")
    assert assets == []
    assert panel._selected_asset_index["offer"] == 0


@pytest.mark.parametrize(
    ("source", "target", "button_id", "expected_action", "result_page"),
    [
        ("POL", "UKR", "trade.deal.d1.accept", "accept", "offers"),
        ("POL", "UKR", "trade.deal.d1.reject", "reject", "offers"),
        ("POL", "UKR", "trade.deal.d1.counter", "counter", "proposal"),
        ("UKR", "POL", "trade.deal.d1.withdraw", "withdraw", "offers"),
    ],
)
def test_deal_detail_dispatches_state_specific_actions(
    monkeypatch, source, target, button_id, expected_action, result_page
):
    panel = TradePanel()
    panel._requested_deal_id = "d1"
    _FlowWidgets.button_results = {button_id: True}
    monkeypatch.setattr(trade_panel_module, "GMLWidgets", _FlowWidgets)
    panel._render_deal_asset_slot = Mock()
    context, actions = _context()
    state = _state({"diplomatic_trade_deals": pl.DataFrame([{
        "id": "d1",
        "source_country_id": source,
        "target_country_id": target,
        "status": "pending",
        "offered_assets_json": '[{"type":"cash","amount":10}]',
        "requested_assets_json": '[{"type":"territory","region_id":2}]',
    }])})

    panel._render_trade_deal_detail(state, context, "UKR")

    assert panel.active_page == result_page
    if expected_action in {"accept", "reject"}:
        assert actions[0].accept is (expected_action == "accept")
    elif expected_action == "withdraw":
        assert actions[0].__class__.__name__ == "ActionWithdrawTradeDeal"
    else:
        assert actions == []
        assert panel.counter_to_deal_id == "d1"
        assert panel.offered_assets == [{"type": "territory", "region_id": 2}]
        assert panel.requested_assets == [{"type": "cash", "amount": 10}]


def test_numeric_stepper_clamps_down_and_draws_both_directions(monkeypatch):
    layout = SimpleNamespace(
        layout=SimpleNamespace(component=Mock(return_value=object())),
        rect_for=Mock(return_value=SimpleNamespace(x=4.0, y=6.0, width=20.0, height=10.0)),
        window_position=(100.0, 200.0),
    )
    monkeypatch.setattr(trade_panel_module, "active_gml_layout", lambda: layout)
    imgui = MagicMock()
    imgui.invisible_button.return_value = True
    imgui.get_window_draw_list.return_value = MagicMock()
    monkeypatch.setattr(trade_panel_module, "imgui", imgui)

    changed, decreased = TradePanel._render_numeric_stepper("path", "minus", -1, 0.0)
    _, increased = TradePanel._render_numeric_stepper("path", "plus", 1, 2.0)

    assert changed is True
    assert decreased == 0.0
    assert increased == 3.0
    assert imgui.get_window_draw_list.return_value.add_line.call_count == 4


@pytest.mark.parametrize(
    ("active_page", "button_id", "expected_page"),
    [
        ("offers", "trade.page.proposal", "proposal"),
        ("proposal", "trade.page.offers", "offers"),
        ("deal", "trade.page.offers", "offers"),
    ],
)
def test_title_navigation_changes_page_without_rendering_stale_content(
    monkeypatch, trade_ui, active_page, button_id, expected_page
):
    panel = TradePanel()
    panel.active_page = active_page
    trade_ui.button_results = {button_id: True}

    panel._render_content(_state(), _context()[0])

    assert panel.active_page == expected_page


def test_partner_selection_resets_asset_draft_and_routes_to_new_partner(
    monkeypatch, trade_ui
):
    panel = TradePanel()
    panel.partner_tag = "POL"
    panel.offered_assets.append({"type": "cash", "amount": 25})
    panel._draw_title_action_icon = Mock()
    panel._render_country_header = Mock()
    panel._render_package_editor = Mock()
    panel._render_balance = Mock()
    monkeypatch.setattr(trade_panel_module, "draw_gml_separator", Mock())
    monkeypatch.setattr(panel, "_country_options", lambda *_args: [
        ("POL", "Poland"), ("FRA", "France"),
    ])
    monkeypatch.setattr(panel, "_country_at_war", lambda *_args: False)
    monkeypatch.setattr(
        trade_panel_module,
        "imgui",
        _FakeImGui(combo_results={"trade.partner": (True, 1)}),
    )
    context, _actions = _context()
    state = _state()

    panel._render_content(state, context)

    assert panel.partner_tag == "FRA"
    assert panel.offered_assets == []
    panel._render_package_editor.assert_called_once_with(state, context, "UKR", "FRA")
    assert trade_panel_module.imgui.calls[-1] == ("pop", ())


@pytest.mark.parametrize(
    ("is_owner", "at_war", "expected_message"),
    [
        (False, False, "Control your own country to negotiate or respond to offers."),
        (True, True, "Countries at war must use the peace-deal editor."),
    ],
)
def test_proposal_content_explains_when_negotiation_is_unavailable(
    monkeypatch, trade_ui, is_owner, at_war, expected_message
):
    panel = TradePanel()
    panel._draw_title_action_icon = Mock()
    panel._render_country_header = Mock()
    panel._render_balance = Mock()
    panel._render_package_editor = Mock()
    monkeypatch.setattr(trade_panel_module, "draw_gml_separator", Mock())
    monkeypatch.setattr(panel, "_country_options", lambda *_args: [("POL", "Poland")])
    monkeypatch.setattr(panel, "_country_at_war", lambda *_args: at_war)
    monkeypatch.setattr(trade_panel_module, "imgui", _FakeImGui())
    owned_context, _actions = _context()
    context = PanelRenderContext(
        "UKR", is_owner,
        net_client=owned_context.net_client if is_owner else None,
    )
    state = _state()

    panel._render_content(state, context)

    panel._render_balance.assert_called_once_with(state, expected_message, context)
    panel._render_package_editor.assert_not_called()


def test_package_editor_clear_button_resets_both_sides(monkeypatch, trade_ui):
    panel = TradePanel()
    panel.offered_assets.append({"type": "cash", "amount": 25})
    panel.requested_assets.append({"type": "territory", "region_id": 3})
    panel._render_asset_side = Mock()
    panel._render_balance = Mock()
    trade_ui.button_results = {"trade.cancel": True}
    monkeypatch.setattr(trade_panel_module, "active_gml_layout", lambda: None)

    panel._render_package_editor(_state(), _context()[0], "UKR", "POL")

    assert panel.offered_assets == []
    assert panel.requested_assets == []


@pytest.mark.parametrize("action", ["offers", "proposal"])
def test_title_action_icon_draws_the_matching_glyph(monkeypatch, action):
    draw = Mock()
    monkeypatch.setattr(
        trade_panel_module,
        "active_gml_layout",
        lambda: SimpleNamespace(window_position=(100.0, 200.0)),
    )
    monkeypatch.setattr(
        trade_panel_module,
        "GAMETHEME",
        SimpleNamespace(colors=SimpleNamespace(text_main=(1.0, 1.0, 1.0, 1.0))),
    )
    monkeypatch.setattr(
        trade_panel_module,
        "imgui",
        SimpleNamespace(
            get_window_draw_list=Mock(return_value=draw),
            get_color_u32=Mock(return_value="white"),
        ),
    )
    ui = SimpleNamespace(rect=Mock(return_value=SimpleNamespace(x=4.0, y=6.0)))

    TradePanel._draw_title_action_icon(ui, "btnApply", action)

    assert draw.add_line.call_count == 3
    if action == "offers":
        assert [call.args[:2] for call in draw.add_line.call_args_list] == [
            ((109.0, 211.0), (116.0, 211.0)),
            ((109.0, 214.0), (116.0, 214.0)),
            ((109.0, 217.0), (116.0, 217.0)),
        ]
    else:
        assert draw.add_line.call_args_list[1].args[:2] == ((109.0, 214.0), (113.0, 211.0))


def test_technology_asset_side_shows_unavailable_without_transferable_levels(
    monkeypatch, trade_ui
):
    panel = TradePanel()
    panel.asset_category = "technology"
    panel._technology_options = Mock(return_value=[])
    panel._render_numeric_stepper = Mock(return_value=(False, 0.0))
    panel._render_asset_list = Mock()

    panel._render_asset_side(_state(), [], "UKR", "POL", "offer")

    assert any(
        call[0] == "text" and call[1][1] == "UNAVAILABLE"
        for call in trade_ui.last.calls
    )
    add_button = next(
        call for call in trade_ui.last.calls
        if call[0] == "button" and call[1] == "trade.offer.add_technology"
    )
    assert add_button[2]["enabled"] is False


def test_asset_list_selects_then_removes_and_clears_assets(monkeypatch):
    panel = TradePanel()
    assets = [
        {"type": "cash", "amount": 10.0},
        {"type": "cash", "amount": 20.0},
    ]
    panel._asset_label = lambda _state, asset: str(asset["amount"])
    imgui = MagicMock()
    imgui.begin_child.return_value = True
    imgui.selectable.return_value = (True, False)
    imgui.button.side_effect = [True, True]
    monkeypatch.setattr(trade_panel_module, "imgui", imgui)

    panel._render_asset_list(_state(), assets, "offer", "root")

    assert assets == []
    assert panel._selected_asset_index["offer"] == 0
    assert imgui.selectable.call_count == 2


def test_trade_offer_list_draws_rows_and_opens_the_clicked_deal(monkeypatch):
    panel = TradePanel()
    panel._selected_deal_id = "stale"
    rectangles = {
        "Trade_Window/frmInner/frmList/lstTrade": SimpleNamespace(
            x=10.0, y=20.0, width=300.0, height=180.0,
        ),
        "Trade_Window/frmInner/frmList/lblProposer": SimpleNamespace(x=30.0),
        "Trade_Window/frmInner/frmList/lblRecipient": SimpleNamespace(x=120.0),
        "Trade_Window/frmInner/frmList/lblStatus": SimpleNamespace(x=220.0),
    }
    session = SimpleNamespace(
        window_position=(100.0, 200.0),
        rect_for=lambda path: rectangles[path],
    )
    monkeypatch.setattr(trade_panel_module, "active_gml_layout", lambda: session)
    monkeypatch.setattr(trade_panel_module, "suspend_gml_layout", lambda: "layout-token")
    monkeypatch.setattr(trade_panel_module, "resume_gml_layout", Mock())
    imgui = MagicMock()
    imgui.begin_child.return_value = True
    imgui.get_cursor_screen_pos.return_value = SimpleNamespace(x=1.0, y=2.0)
    imgui.get_item_rect_min.return_value = SimpleNamespace(x=150.0, y=250.0)
    imgui.selectable.return_value = (True, False)
    monkeypatch.setattr(trade_panel_module, "imgui", imgui)
    _FlowWidgets.button_results = {"trade.deal.view": True}
    monkeypatch.setattr(trade_panel_module, "GMLWidgets", _FlowWidgets)
    state = _state({"diplomatic_trade_deals": pl.DataFrame([{
        "id": "deal-2", "source_country_id": "POL", "target_country_id": "UKR",
        "status": "pending", "created_at_minute": 20,
    }])})

    panel._render_trade_offer_list(_state(), "UKR")
    assert panel._selected_deal_id == ""
    assert imgui.text_disabled.call_args.args == ("No bilateral trade offers yet.",)

    panel._render_trade_offer_list(state, "UKR")

    assert panel._selected_deal_id == "deal-2"
    assert panel._requested_deal_id == "deal-2"
    assert panel.active_page == "deal"
    assert imgui.text.call_args_list == [
        (("POL",), {}), (("UKR",), {}), (("PENDING",), {}),
    ]
    assert imgui.end_child.call_count == 2


def test_deal_asset_slot_draws_assets_and_empty_state(monkeypatch):
    panel = TradePanel()
    component = object()
    session = SimpleNamespace(
        window_position=(100.0, 200.0),
        layout=SimpleNamespace(component=Mock(return_value=component)),
        rect_for=Mock(return_value=SimpleNamespace(x=10.0, y=20.0, width=180.0, height=80.0)),
    )
    monkeypatch.setattr(trade_panel_module, "active_gml_layout", lambda: session)
    monkeypatch.setattr(trade_panel_module, "suspend_gml_layout", lambda: "layout-token")
    monkeypatch.setattr(trade_panel_module, "resume_gml_layout", Mock())
    imgui = MagicMock()
    imgui.begin_child.return_value = True
    monkeypatch.setattr(trade_panel_module, "imgui", imgui)
    state = _state()

    panel._render_deal_asset_slot(
        state, [{"type": "cash", "amount": 12}], "frmSideA", "OFFER", "trade.offer",
    )
    panel._render_deal_asset_slot(state, [], "frmSideB", "REQUEST", "trade.request")

    assert imgui.text_disabled.call_args_list == [(("OFFER",), {}), (("REQUEST",), {}), (("None",), {})]
    imgui.text_wrapped.assert_called_once_with("Cash 12", test_id="trade.offer.0")
    assert imgui.end_child.call_count == 2


@pytest.mark.parametrize("active_page", ["offers", "deal"])
def test_content_routes_to_the_selected_trade_page(monkeypatch, trade_ui, active_page):
    panel = TradePanel()
    panel.active_page = active_page
    panel._draw_title_action_icon = Mock()
    panel._render_trade_offer_list = Mock()
    panel._render_trade_deal_detail = Mock()
    state = _state()
    context, _actions = _context()

    panel._render_content(state, context)

    if active_page == "offers":
        panel._render_trade_offer_list.assert_called_once_with(state, "UKR")
        panel._render_trade_deal_detail.assert_not_called()
    else:
        panel._render_trade_deal_detail.assert_called_once_with(state, context, "UKR")
        panel._render_trade_offer_list.assert_not_called()


def test_country_header_returns_without_layout_and_skips_proposal_controls(monkeypatch):
    panel = TradePanel()
    monkeypatch.setattr(trade_panel_module, "active_gml_layout", lambda: None)
    panel._render_country_header(_state(), "UKR", _context()[0])

    ui = _FlowWidgets("Trade_Detailed_Window/frmInner/frmSideA")
    monkeypatch.setattr(trade_panel_module, "active_gml_layout", lambda: SimpleNamespace())
    monkeypatch.setattr(trade_panel_module, "GMLWidgets", lambda _root: ui)
    panel.active_page = "offers"

    panel._render_country_header(_state(), "UKR", _context()[0])

    assert ui.calls == [(
        "text", ("txtCountry", "OPEN OFFERS"), {"test_id": "trade.offer.country"},
    )]


@pytest.mark.parametrize("layout_kind", ["missing", "without_component"])
def test_numeric_stepper_returns_unchanged_without_layout_component(monkeypatch, layout_kind):
    if layout_kind == "missing":
        layout = None
    else:
        layout = SimpleNamespace(layout=SimpleNamespace(component=Mock(return_value=None)))
    monkeypatch.setattr(trade_panel_module, "active_gml_layout", lambda: layout)

    assert TradePanel._render_numeric_stepper("path", "minus", -1, 3.0) == (False, 3.0)


@pytest.mark.parametrize("layout_state", ["missing", "missing_component"])
def test_title_action_icon_skips_drawing_without_geometry(monkeypatch, layout_state):
    if layout_state == "missing":
        layout = None
        rect = SimpleNamespace(x=1.0, y=2.0)
    else:
        layout = SimpleNamespace(window_position=(0.0, 0.0))
        rect = None
    draw_list = Mock()
    monkeypatch.setattr(trade_panel_module, "active_gml_layout", lambda: layout)
    monkeypatch.setattr(
        trade_panel_module,
        "imgui",
        SimpleNamespace(get_window_draw_list=Mock(return_value=draw_list)),
    )

    TradePanel._draw_title_action_icon(SimpleNamespace(rect=lambda _slot: rect), "slot", "offers")

    draw_list.add_line.assert_not_called()


def test_deal_detail_shows_unavailable_message_for_removed_offer(monkeypatch, trade_ui):
    wrapped = Mock()
    monkeypatch.setattr(
        trade_panel_module,
        "imgui",
        SimpleNamespace(text_wrapped=wrapped),
    )
    panel = TradePanel()
    panel._requested_deal_id = "removed"

    panel._render_trade_deal_detail(_state(), _context()[0], "UKR")

    wrapped.assert_called_once_with(
        "The selected offer is unavailable.", test_id="trade.selected_deal.unavailable",
    )


def test_deal_asset_slot_returns_when_layout_or_list_rect_is_missing(monkeypatch):
    panel = TradePanel()
    monkeypatch.setattr(trade_panel_module, "active_gml_layout", lambda: None)
    panel._render_deal_asset_slot(_state(), [], "frmSideA", "Offer", "offer")

    session = SimpleNamespace(
        layout=SimpleNamespace(component=Mock(return_value=None)),
        rect_for=Mock(),
    )
    monkeypatch.setattr(trade_panel_module, "active_gml_layout", lambda: session)
    panel._render_deal_asset_slot(_state(), [], "frmSideA", "Offer", "offer")

    session.rect_for.assert_not_called()


def test_counterproposal_dispatches_counter_action_and_resets_draft():
    panel = TradePanel()
    panel.counter_to_deal_id = "deal-1"
    panel.offered_assets = [{"type": "cash", "amount": 20}]
    panel.requested_assets = [{"type": "territory", "region_id": 4}]
    panel.expiry_days = 7
    context, actions = _context()

    panel._send_proposal(context, "UKR", "POL")

    assert len(actions) == 1
    assert isinstance(actions[0], ActionCounterTradeDeal)
    assert actions[0].deal_id == "deal-1"
    assert actions[0].offered_assets == [{"type": "cash", "amount": 20}]
    assert actions[0].requested_assets == [{"type": "territory", "region_id": 4}]
    assert actions[0].expires_after_days == 7
    assert panel.counter_to_deal_id == ""
    assert panel.active_page == "offers"


@pytest.fixture
def trade_ui(monkeypatch):
    _FakeWidgets.button_results = {}
    monkeypatch.setattr(trade_panel_module, "GMLWidgets", _FakeWidgets)
    monkeypatch.setattr(trade_panel_module, "imgui", _FakeImGui())
    return _FakeWidgets


@pytest.mark.parametrize("add_asset", [True, False])
def test_render_cash_asset_side_clamps_input_and_adds_only_positive_amounts(
    monkeypatch, trade_ui, add_asset
):
    panel = TradePanel()
    panel.asset_category = "cash"
    assets = []
    monkeypatch.setattr(panel, "_render_numeric_stepper", lambda _path, _id, _direction, value: (False, value))
    monkeypatch.setattr(panel, "_render_asset_list", lambda *_args: None)
    trade_panel_module.imgui.cash_result = (True, 25.0)
    trade_ui.button_results = {"trade.offer.add_cash": add_asset}

    panel._render_asset_side(_state(), assets, "UKR", "POL", "offer")

    assert assets == ([{"type": "cash", "amount": 25.0}] if add_asset else [])
    assert panel.offer_cash == (0.0 if add_asset else 25.0)
    assert trade_panel_module.imgui.calls[-1][0] == "pop"


def test_render_region_asset_side_adds_selected_region_once(monkeypatch, trade_ui):
    panel = TradePanel()
    panel.asset_category = "region"
    assets = [{"type": "territory", "region_id": 2}]
    monkeypatch.setattr(panel, "_regions_for_owner", lambda *_args: [(2, "Lviv"), (3, "Odesa")])
    monkeypatch.setattr(panel, "_render_asset_list", lambda *_args: None)
    trade_panel_module.imgui.combo_results = {"trade.offer.region": (True, 1)}
    trade_ui.button_results = {"trade.offer.add_region": True}

    panel._render_asset_side(_state(), assets, "UKR", "POL", "offer")

    assert assets == [
        {"type": "territory", "region_id": 2},
        {"type": "territory", "region_id": 3},
    ]
    assert panel.offer_region_idx == 1


def test_render_technology_asset_side_selects_transferable_level(monkeypatch, trade_ui):
    panel = TradePanel()
    panel.asset_category = "technology"
    assets = []
    monkeypatch.setattr(panel, "_technology_options", lambda *_args: [("air", 3, 1)])
    monkeypatch.setattr(panel, "_render_asset_list", lambda *_args: None)
    trade_panel_module.imgui.combo_results = {
        "trade.offer.technology_level": (True, 0),
    }
    trade_ui.button_results = {"trade.offer.add_technology": True}

    panel._render_asset_side(_state(), assets, "UKR", "POL", "offer")

    assert assets == [{"type": "technology", "branch": "air", "level": 2}]
    assert panel.offer_technology_level == 2
    assert any(call[0] == "combo" and call[1] == "trade.offer.technology_level" for call in trade_panel_module.imgui.calls)
