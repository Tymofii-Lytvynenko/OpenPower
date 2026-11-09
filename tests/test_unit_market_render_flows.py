from types import SimpleNamespace

import pytest

from src.client.ui.panels.military import unit_market_panel
from src.client.ui.panels.military.unit_market_panel import UnitMarketPanel
from src.shared.actions import ActionBuyMarketUnit


class Imgui:
    ChildFlags_ = SimpleNamespace(borders=1)
    StyleVar_ = SimpleNamespace(frame_padding=1)
    Col_ = SimpleNamespace(text=1, text_selected_bg=2)
    Key = SimpleNamespace(enter=10, keypad_enter=11, escape=12)
    InputTextFlags_ = SimpleNamespace(
        read_only=1,
        callback_char_filter=2,
        enter_returns_true=4,
        callback_always=8,
    )

    def __init__(
        self,
        *,
        clicked=(),
        opened=True,
        input_active=False,
        input_focused=False,
        input_hovered=False,
        input_activated=False,
        input_deactivated=False,
        input_changed=False,
        input_value="",
        pressed_keys=(),
    ):
        self.clicked = set(clicked)
        self.opened = opened
        self.selectables = []
        self.children = []
        self.wrapped = []
        self.style_vars = []
        self.input_calls = []
        self.popped_style_vars = 0
        self.popped_style_colors = []
        self.disabled = []
        self.input_active = input_active
        self.input_focused = input_focused
        self.input_hovered = input_hovered
        self.input_activated = input_activated
        self.input_deactivated = input_deactivated
        self.input_changed = input_changed
        self.input_value = input_value
        self.pressed_keys = set(pressed_keys)
        self.focus_offsets = []

    def begin_child(self, *args, **kwargs):
        self.children.append((args, kwargs))
        return self.opened

    def end_child(self):
        pass

    def selectable(self, label, selected, *, size, test_id):
        self.selectables.append((label, selected, size, test_id))
        return test_id in self.clicked, False

    def text_wrapped(self, value, **kwargs):
        self.wrapped.append((value, kwargs))

    def push_style_var(self, variable, value):
        self.style_vars.append((variable, value))

    def pop_style_var(self):
        self.popped_style_vars += 1

    def input_text(self, label, value, flags=None, *, test_id, gml_id, callback=None):
        self.input_calls.append((label, value, flags, test_id, gml_id))
        return self.input_changed, self.input_value if self.input_changed else value

    def push_style_color(self, color, value):
        pass

    def pop_style_color(self, count=1):
        self.popped_style_colors.append(count)

    def begin_disabled(self, disabled):
        self.disabled.append(disabled)

    def end_disabled(self):
        pass

    def is_key_pressed(self, key, repeat):
        return key in self.pressed_keys

    def is_item_focused(self):
        return self.input_focused

    def is_item_active(self):
        return self.input_active

    def is_item_hovered(self):
        return self.input_hovered

    def is_item_activated(self):
        return self.input_activated

    def is_item_deactivated(self):
        return self.input_deactivated

    def set_keyboard_focus_here(self, offset):
        self.focus_offsets.append(offset)

    @staticmethod
    def get_time():
        return 0.0


class Ui:
    def __init__(self, *, buy=False, hitboxes=None):
        self.buy = buy
        self.texts = []
        self.buttons = []
        self.status = []
        self.paths = []
        self.hitboxes = hitboxes or {}
        self.hitbox_calls = []

    def text(self, slot, value):
        self.texts.append((slot, value))

    def path(self, slot):
        self.paths.append(slot)
        return f"gml/{slot}"

    def button(self, *args, **kwargs):
        self.buttons.append((args, kwargs))
        return self.buy

    def text_at(self, *args, **kwargs):
        self.status.append((args, kwargs))

    def hitbox_state(self, slot, test_id, *, enabled, tooltip):
        self.hitbox_calls.append((slot, test_id, enabled, tooltip))
        return self.hitboxes.get(test_id, (False, False))


class Client:
    player_id = "player-1"

    def __init__(self):
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)


def install_imgui(monkeypatch, **kwargs):
    fake = Imgui(**kwargs)
    monkeypatch.setattr(unit_market_panel, "imgui", fake)
    return fake


def test_listing_list_selects_row_and_resets_quantity_edit_state(monkeypatch):
    fake = install_imgui(monkeypatch, clicked={"unit_market.listing.B"})
    panel = UnitMarketPanel()
    panel._selected_listing_id = "A"
    panel._quantity = 2
    panel._quantity_edit_text = "12"
    panel._quantity_editing = True
    panel._request_sent = True
    ui = Ui()

    selected = panel._render_listing_list(ui, [
        {"id": "A", "quantity": 2, "design_name": "Infantry"},
        {"id": "B", "quantity": 5000, "design_name": "Fighter"},
    ])

    assert selected["id"] == "B"
    assert panel._selected_listing_id == "B"
    assert panel._quantity == 5000
    assert panel._quantity_edit_text == "5000"
    assert panel._quantity_editing is False
    assert panel._request_sent is False
    assert fake.selectables == [
        ("2  Infantry##A", True, (0.0, 15.0), "unit_market.listing.A"),
        ("5 000  Fighter##B", False, (0.0, 15.0), "unit_market.listing.B"),
    ]


def test_listing_list_clears_stale_selection_and_shows_empty_state(monkeypatch):
    fake = install_imgui(monkeypatch)
    empty_states = []
    monkeypatch.setattr(unit_market_panel, "draw_empty_state", empty_states.append)
    panel = UnitMarketPanel()
    panel._selected_listing_id = "stale"
    panel._quantity = 9
    panel._quantity_edit_text = "9"
    panel._quantity_editing = True
    panel._request_sent = True

    selected = panel._render_listing_list(Ui(), [])

    assert selected is None
    assert empty_states == ["No eligible used units are listed for this type."]
    assert panel._selected_listing_id == ""
    assert panel._quantity == 0
    assert panel._quantity_edit_text == ""
    assert panel._quantity_editing is False
    assert panel._request_sent is False
    assert fake.selectables == []


def test_listing_list_preserves_selected_row_when_child_is_closed(monkeypatch):
    install_imgui(monkeypatch, opened=False)
    panel = UnitMarketPanel()
    panel._selected_listing_id = "A"
    panel._quantity = 4

    selected = panel._render_listing_list(Ui(), [{"id": "A", "quantity": 4}])

    assert selected == {"id": "A", "quantity": 4}
    assert panel._quantity == 4


def patch_selection_helpers(monkeypatch):
    value_fields = []
    quantities = []
    monkeypatch.setattr(
        UnitMarketPanel,
        "_render_value_field",
        staticmethod(lambda ui, slot, value, test_id: value_fields.append((slot, value, test_id))),
    )
    monkeypatch.setattr(
        UnitMarketPanel,
        "_render_quantity",
        lambda self, ui, listing, available: quantities.append((listing, available, self._quantity)),
    )
    return value_fields, quantities


def test_selection_buys_available_quantity_and_marks_request_sent(monkeypatch):
    fake = install_imgui(monkeypatch)
    value_fields, quantities = patch_selection_helpers(monkeypatch)
    panel = UnitMarketPanel()
    panel._quantity = 2
    client = Client()
    ui = Ui(buy=True)

    panel._render_selection(
        ui,
        {"id": "L1", "design_id": "D1", "quantity": 5, "seller_name": "Seller", "design_name": "Scout", "price": 12.5},
        {"D1": {"display_name": "Scout design"}},
        SimpleNamespace(target_tag=" usa ", is_own_country=True, net_client=client),
    )

    assert quantities == [({"id": "L1", "design_id": "D1", "quantity": 5, "seller_name": "Seller", "design_name": "Scout", "price": 12.5}, 5, 2)]
    assert value_fields[0][1] == "Seller"
    assert value_fields[1][1] == unit_market_panel.UnitMarketPanel._format_money(12.5)
    assert value_fields[2][1] == unit_market_panel.UnitMarketPanel._format_money(25.0)
    assert value_fields[3][1] == "Scout"
    assert fake.wrapped and fake.wrapped[0][1]["test_id"] == "unit_market.preview_unavailable"
    assert isinstance(client.actions[0], ActionBuyMarketUnit)
    assert client.actions[0].listing_id == "L1"
    assert client.actions[0].buyer_country_tag == "USA"
    assert client.actions[0].quantity == 2
    assert panel._request_sent is True
    assert ui.status[0][0][1] == "REQUEST SENT"


@pytest.mark.parametrize(
    ("is_own", "client_available", "listing", "request_sent", "expected_tooltip"),
    [
        (False, True, {"id": "L", "quantity": 3, "price": 1}, False, "Purchases are available only for your country."),
        (True, False, {"id": "L", "quantity": 3, "price": 1}, False, "Connect to the game before purchasing a used unit."),
        (True, True, None, False, "Select an eligible listing first."),
        (True, True, {"id": "L", "quantity": 0, "price": 1}, False, "Choose a quantity available in this listing."),
        (True, True, {"id": "L", "quantity": 3, "price": 1}, True, "The server is validating this purchase request."),
    ],
)
def test_selection_disables_buy_with_reason(monkeypatch, is_own, client_available, listing, request_sent, expected_tooltip):
    install_imgui(monkeypatch)
    patch_selection_helpers(monkeypatch)
    panel = UnitMarketPanel()
    panel._request_sent = request_sent
    client = Client() if client_available else None
    ui = Ui()

    panel._render_selection(
        ui,
        listing,
        {},
        SimpleNamespace(target_tag="USA", is_own_country=is_own, net_client=client),
    )

    assert ui.buttons[0][1]["enabled"] is False
    assert ui.buttons[0][1]["tooltip"] == expected_tooltip
    assert not client or client.actions == []


def test_read_only_value_field_restores_style_after_render(monkeypatch):
    fake = install_imgui(monkeypatch)
    ui = Ui()

    UnitMarketPanel._render_value_field(ui, "path/to/field", "Seller", "unit_market.seller")

    assert fake.input_calls == [
        ("##unit_market.seller", "Seller", unit_market_panel.imgui.InputTextFlags_.read_only, "unit_market.seller", "gml/path/to/field"),
    ]
    assert fake.popped_style_vars == 1


def capture_quantity_draws(monkeypatch, panel):
    calls = {"mask": [], "selection": [], "text": [], "caret": [], "arrow": [], "advance": []}
    monkeypatch.setattr(panel, "_draw_quantity_mask", lambda *args: calls["mask"].append(args))
    monkeypatch.setattr(panel, "_draw_quantity_selection", lambda *args: calls["selection"].append(args))
    monkeypatch.setattr(panel, "_draw_quantity_text", lambda *args, **kwargs: calls["text"].append((args, kwargs)))
    monkeypatch.setattr(panel, "_draw_quantity_caret", lambda *args: calls["caret"].append(args))
    monkeypatch.setattr(panel, "_draw_quantity_arrow", lambda *args, **kwargs: calls["arrow"].append((args, kwargs)))
    monkeypatch.setattr(panel, "_advance_quantity_arrow", lambda *args: calls["advance"].append(args))
    return calls


def test_quantity_entry_activation_preserves_editor_and_arrow_state(monkeypatch):
    fake = install_imgui(
        monkeypatch,
        input_active=True,
        input_focused=True,
        input_hovered=True,
        input_activated=True,
    )
    panel = UnitMarketPanel()
    panel._quantity = 2
    panel._request_sent = True
    calls = capture_quantity_draws(monkeypatch, panel)
    ui = Ui(hitboxes={"unit_market.quantity.down": (True, True)})

    panel._render_quantity(ui, {"id": "L1"}, 3)

    assert panel._quantity_editing is True
    assert panel._quantity_edit_text == "2"
    assert panel._request_sent is True
    assert calls["mask"]
    assert calls["selection"] == [(ui, f"{unit_market_panel._LIST_SLOT}/frmUpdatableValue1/edtText", "2")]
    assert calls["caret"]
    assert calls["text"][0][1]["test_id"] == "unit_market.quantity.edit_display"
    assert fake.popped_style_colors == [2]
    assert ui.hitbox_calls[0][2] is True
    assert calls["advance"][0][1:4] == (True, True, -1)


def test_quantity_focus_without_activation_starts_editor(monkeypatch):
    install_imgui(monkeypatch, input_focused=True)
    panel = UnitMarketPanel()
    panel._quantity = 3
    calls = capture_quantity_draws(monkeypatch, panel)
    ui = Ui()

    panel._render_quantity(ui, {"id": "L1"}, 5)

    assert panel._quantity_editing is True
    assert panel._quantity_edit_text == "3"
    assert calls["selection"] == [(ui, f"{unit_market_panel._LIST_SLOT}/frmUpdatableValue1/edtText", "3")]
    assert calls["text"][0][1]["test_id"] == "unit_market.quantity.edit_display"


def test_quantity_deactivation_commits_and_clamps_existing_buffer(monkeypatch):
    install_imgui(monkeypatch, input_deactivated=True)
    panel = UnitMarketPanel()
    panel._quantity = 2
    panel._quantity_edit_text = "8"
    panel._quantity_editing = True
    panel._request_sent = True
    capture_quantity_draws(monkeypatch, panel)

    panel._render_quantity(Ui(), {"id": "L1"}, 4)

    assert panel._quantity == 4
    assert panel._quantity_edit_text == "4"
    assert panel._quantity_editing is False
    assert panel._request_sent is False


def test_quantity_enter_commits_clamped_buffer_and_returns_focus(monkeypatch):
    fake = install_imgui(
        monkeypatch,
        input_focused=True,
        pressed_keys={Imgui.Key.enter},
    )
    panel = UnitMarketPanel()
    panel._quantity = 2
    panel._quantity_edit_text = "6"
    panel._quantity_editing = True
    calls = capture_quantity_draws(monkeypatch, panel)
    ui = Ui()

    panel._render_quantity(ui, {"id": "L1"}, 5)

    assert panel._quantity == 5
    assert panel._quantity_edit_text == "5"
    assert panel._quantity_editing is False
    assert fake.focus_offsets == [0]
    assert calls["selection"] == []
    assert calls["text"][0][1]["test_id"] == "unit_market.quantity.display"
    assert calls["text"][0][0][2] == "5"


def test_quantity_escape_restores_existing_buffer_instead_of_input_value(monkeypatch):
    fake = install_imgui(
        monkeypatch,
        pressed_keys={Imgui.Key.escape},
    )
    panel = UnitMarketPanel()
    panel._quantity = 2
    panel._quantity_edit_text = "2"
    panel._quantity_editing = True
    capture_quantity_draws(monkeypatch, panel)

    panel._render_quantity(Ui(), {"id": "L1"}, 9)

    assert panel._quantity == 2
    assert panel._quantity_editing is False
    assert panel._quantity_edit_text == "2"
    assert fake.focus_offsets == [0]


def test_quantity_changed_text_commits_on_deactivation_and_clears_request(monkeypatch):
    fake = install_imgui(
        monkeypatch,
        input_changed=True,
        input_value="8",
        input_deactivated=True,
    )
    panel = UnitMarketPanel()
    panel._quantity = 1
    panel._request_sent = True
    capture_quantity_draws(monkeypatch, panel)

    panel._render_quantity(Ui(), {"id": "L1"}, 4)

    assert panel._quantity == 4
    assert panel._quantity_edit_text == "4"
    assert panel._quantity_editing is False
    assert panel._request_sent is False
    assert fake.popped_style_colors == [2]


def test_quantity_without_listing_disables_arrows_and_omits_value_draws(monkeypatch):
    fake = install_imgui(monkeypatch)
    panel = UnitMarketPanel()
    calls = capture_quantity_draws(monkeypatch, panel)
    ui = Ui()

    panel._render_quantity(ui, None, 0)

    assert fake.disabled == [True]
    assert panel._quantity_editing is False
    assert calls["mask"] == []
    assert calls["selection"] == []
    assert calls["text"] == []
    assert all(not call[2] for call in ui.hitbox_calls)
