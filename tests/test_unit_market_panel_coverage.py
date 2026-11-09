from types import SimpleNamespace

import pytest

from src.client.ui.panels.military import unit_market_panel
from src.client.ui.panels.military.unit_market_panel import UnitMarketPanel


class Table:
    def __init__(self, rows, columns=None):
        self.rows = rows
        self.columns = set(columns if columns is not None else (rows[0].keys() if rows else ()))

    def is_empty(self):
        return not self.rows

    def to_dicts(self):
        return self.rows


class Layout:
    def __init__(self, components):
        self.components = components

    def component(self, slot):
        return self.components.get(slot)


class Session:
    def __init__(self, components):
        self.layout = Layout(components)
        self.window_position = (100.0, 200.0)

    @staticmethod
    def rect_for(component):
        return component


class ScrolledImgui:
    def __init__(self, *, hovered=False):
        self.hovered = hovered
        self.positions = []
        self.texts = []
        self.progress = []
        self.tooltips = []

    def set_cursor_screen_pos(self, position):
        self.positions.append(position)

    @staticmethod
    def get_scroll_x():
        return 4.0

    @staticmethod
    def get_scroll_y():
        return 6.0

    def text_disabled(self, value, *, test_id):
        self.texts.append((value, test_id))

    def progress_bar(self, fraction, size, overlay, *, test_id):
        self.progress.append((fraction, size, overlay, test_id))

    def is_item_hovered(self):
        return self.hovered

    def set_tooltip(self, value):
        self.tooltips.append(value)


def test_design_lookup_handles_absent_empty_and_malformed_tables():
    assert UnitMarketPanel._designs_by_id(SimpleNamespace()) == {}
    assert UnitMarketPanel._designs_by_id(SimpleNamespace(tables={"unit_designs": None})) == {}
    assert UnitMarketPanel._designs_by_id(SimpleNamespace(
        tables={"unit_designs": Table([], columns={"id"})},
    )) == {}
    assert UnitMarketPanel._designs_by_id(SimpleNamespace(
        tables={"unit_designs": Table([{"name": "missing id"}], columns={"name"})},
    )) == {}

    rows = [{"id": "D1", "class_name": "infantry"}, {"id": None, "name": "fallback"}]
    assert UnitMarketPanel._designs_by_id(SimpleNamespace(
        tables={"unit_designs": Table(rows)},
    )) == {"D1": rows[0], "": rows[1]}


def test_listing_role_uses_design_role_then_listing_type():
    assert UnitMarketPanel._listing_role(
        {"design_id": "D1", "unit_type": "armor"},
        {"D1": {"class_name": "Infantry"}},
    ) == "infantry"
    assert UnitMarketPanel._listing_role(
        {"design_id": "missing", "unit_type": "Heavy Tank"}, {},
    ) == "heavy_tank"
    assert UnitMarketPanel._listing_role({"design_id": "D1"}, {"D1": {}}) == ""


@pytest.mark.parametrize(
    ("quantity", "expected"),
    [(0, "0"), (1234, "1 234"), (-45, "-45"), (1000000, "1 000 000")],
)
def test_market_quantity_formatting(quantity, expected):
    assert UnitMarketPanel._format_quantity(quantity) == expected


@pytest.mark.parametrize(
    ("edit_text", "available", "expected"),
    [(" 4 ", 8, 4), ("bad", 8, 1), ("99", 6, 6), ("2", 0, 1)],
)
def test_committing_quantity_text_parses_and_clamps(edit_text, available, expected):
    panel = UnitMarketPanel()
    panel._quantity_edit_text = edit_text
    panel._quantity_editing = True
    panel._request_sent = True

    panel._commit_quantity_text(available)

    assert panel._quantity == expected
    assert panel._quantity_edit_text == str(expected)
    assert panel._quantity_editing is False
    assert panel._request_sent is False


def test_market_quantity_stepper_resets_request_state_only_when_value_changes(monkeypatch):
    monkeypatch.setattr(
        unit_market_panel,
        "imgui",
        SimpleNamespace(get_time=lambda: 0.0),
    )
    panel = UnitMarketPanel()
    panel._quantity = 2
    panel._request_sent = True

    panel._advance_quantity_arrow("up", active=True, clicked=True, direction=1, available=3)
    assert panel._quantity == 3
    assert panel._request_sent is False

    panel._request_sent = True
    panel._advance_quantity_arrow("up", active=True, clicked=True, direction=1, available=3)
    assert panel._quantity == 3
    assert panel._request_sent is True


def test_quantity_cursor_filters_characters_and_clamps_selection_positions(monkeypatch):
    monkeypatch.setattr(
        unit_market_panel,
        "imgui",
        SimpleNamespace(InputTextFlags_=SimpleNamespace(callback_char_filter=4)),
    )
    panel = UnitMarketPanel()

    assert panel._capture_quantity_cursor(SimpleNamespace(event_flag=4, event_char=ord("7"))) == 0
    assert panel._capture_quantity_cursor(SimpleNamespace(event_flag=4, event_char=ord("x"))) == 1
    assert panel._capture_quantity_cursor(SimpleNamespace(
        event_flag=0,
        cursor_pos=-2,
        selection_start=3,
        selection_end=-1,
    )) == 0
    assert (panel._quantity_cursor_pos, panel._quantity_selection_start, panel._quantity_selection_end) == (0, 3, 0)


def test_quantity_text_geometry_clips_to_field_and_centers_vertically(monkeypatch):
    monkeypatch.setattr(
        unit_market_panel,
        "imgui",
        SimpleNamespace(calc_text_size=lambda value: SimpleNamespace(x=30.0, y=12.0)),
    )

    assert UnitMarketPanel._quantity_text_geometry(
        SimpleNamespace(width=20.0, height=10.0), "123456789",
    ) == (3.0, 0.0, 14.0)


def test_blend_color_alpha_composites_rgb_and_returns_opaque_result():
    assert UnitMarketPanel._blend_color(
        (0.8, 0.4, 0.2, 0.25), (0.0, 0.2, 0.6, 0.1),
    ) == pytest.approx((0.2, 0.25, 0.5, 1.0))


def test_scrolled_text_and_capability_skip_missing_slots(monkeypatch):
    fake = ScrolledImgui()
    monkeypatch.setattr(unit_market_panel, "imgui", fake)
    session = Session({})

    UnitMarketPanel._draw_scrolled_text(session, "missing", "value", "text.id")
    UnitMarketPanel._draw_scrolled_capability(session, "missing", "armor", 12.0)

    assert fake.positions == []
    assert fake.texts == []
    assert fake.progress == []


def test_scrolled_text_offsets_by_window_and_scroll_position(monkeypatch):
    fake = ScrolledImgui()
    monkeypatch.setattr(unit_market_panel, "imgui", fake)
    session = Session({"label": SimpleNamespace(x=13.0, y=20.0, width=100.0, height=10.0)})

    UnitMarketPanel._draw_scrolled_text(
        session,
        "label",
        "Armor",
        "unit_market.capability.armor.label",
    )

    assert fake.positions == [(109.0, 214.0)]
    assert fake.texts == [("Armor", "unit_market.capability.armor.label")]


@pytest.mark.parametrize("key,value,expected_fraction,expected_tooltip", [
    ("armor", None, 0.0, "This design has no saved OpenPower capability value."),
    ("speed", 75.0, 0.0, "OpenPower stores speed and maneuverability separately; the source combines them."),
    ("unknown", 9.0, 0.0, "OpenPower value: 9"),
])
def test_scrolled_capability_handles_unavailable_speed_and_unknown_values(
    monkeypatch, key, value, expected_fraction, expected_tooltip,
):
    fake = ScrolledImgui(hovered=True)
    monkeypatch.setattr(unit_market_panel, "imgui", fake)
    rect = SimpleNamespace(x=10.0, y=20.0, width=80.0, height=12.0)
    session = Session({"meter": rect})

    UnitMarketPanel._draw_scrolled_capability(session, "meter", key, value)

    assert fake.positions == [(106.0, 214.0)]
    assert fake.progress == [(expected_fraction, (80.0, 12.0), "N/A" if value is None or key == "speed" else "9", f"unit_market.capability.{key}")]
    assert fake.tooltips == [expected_tooltip]
