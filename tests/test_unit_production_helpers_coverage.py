from types import SimpleNamespace

import pytest

from modules.base.systems.military.production_policy import MAX_UNIT_PRODUCTION_QUANTITY
from src.client.ui.panels.military.unit_production_panel import UnitProductionPanel
from src.shared.actions import (
    ActionCancelProductionOrder,
    ActionSetProductionPaused,
    ActionSetProductionPriority,
)


class Table:
    def __init__(self, rows):
        self.rows = rows

    def to_dicts(self):
        return self.rows


class Client:
    player_id = "player-1"

    def __init__(self):
        self.actions = []

    def send_action(self, action):
        self.actions.append(action)


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"domain": "missile forces"}, "strategic"),
        ({"branch": "naval"}, "naval"),
        ({"unit_type": "Fighter"}, "air"),
        ({"class_name": "Infantry"}, "ground"),
        ({}, "ground"),
    ],
)
def test_design_category_uses_domain_tokens(row, expected):
    assert UnitProductionPanel._design_category(row) == expected


def test_visible_designs_selects_domestic_or_selected_foreign_builder_and_category():
    panel = UnitProductionPanel()
    domestic = [
        {"id": "D1", "class_name": "infantry"},
        {"id": "D2", "class_name": "fighter"},
    ]
    foreign = [
        {"id": "F1", "country_id": "CAN", "unit_type": "infantry"},
        {"id": "F2", "country_id": "MEX", "unit_type": "infantry"},
        {"id": "F3", "country_id": "CAN", "unit_type": "fighter"},
    ]

    panel._selected_builder_country = "USA"
    panel._category = "ground"
    assert panel._visible_designs("USA", domestic, foreign) == [domestic[0]]

    panel._selected_builder_country = "CAN"
    assert panel._visible_designs("USA", domestic, foreign) == [foreign[0]]

    panel._category = "air"
    assert panel._visible_designs("USA", domestic, foreign) == [foreign[2]]


def test_builder_tags_normalize_deduplicate_and_sort_foreign_countries():
    assert UnitProductionPanel._builder_tags("usa", [
        {"country_id": "mex"},
        {"country_id": "CAN"},
        {"country_id": "can"},
        {"country_id": "  "},
    ]) == ["usa", "CAN", "MEX"]
    assert UnitProductionPanel._builder_tags("", [{"country_id": "mex"}]) == ["MEX"]


def test_country_names_and_codes_normalize_rows_and_handle_missing_table():
    state = SimpleNamespace(tables={
        "countries": Table([
            {"id": "usa", "name": "United States", "code": "usaxy"},
            {"id": "can", "name": None, "code": None},
        ]),
    })

    assert UnitProductionPanel._country_names(state) == {
        "USA": "United States",
        "CAN": "can",
    }
    assert UnitProductionPanel._country_codes(state) == {"USA": "USA", "CAN": "CAN"}
    assert UnitProductionPanel._country_names(SimpleNamespace(tables={})) == {}
    assert UnitProductionPanel._country_codes(SimpleNamespace(tables={})) == {}


@pytest.mark.parametrize(
    ("priority", "status", "expected"),
    [(100, "queued", 0), (75, "queued", 0), (50, "queued", 1), (25, "queued", 1), (1, "queued", 2), (100, "paused", 3)],
)
def test_queue_priority_index_maps_status_and_thresholds(priority, status, expected):
    assert UnitProductionPanel._queue_priority_index(priority, status) == expected


def test_priority_color_has_fallback_for_unknown_index():
    assert UnitProductionPanel._priority_color(0) == (0.91, 0.39, 0.39, 1.0)
    assert UnitProductionPanel._priority_color(3) == (0.62, 0.62, 0.62, 1.0)
    assert UnitProductionPanel._priority_color(99) == (0.25, 0.27, 0.3, 1.0)


@pytest.mark.parametrize(
    ("value", "fallback", "expected"),
    [("quantity 14", 3, 14), ("1.25", 3, 125), ("no digits", 7, 7), ("9999999", 2, MAX_UNIT_PRODUCTION_QUANTITY)],
)
def test_parse_quantity_extracts_digits_and_applies_bounds(value, fallback, expected):
    assert UnitProductionPanel._parse_quantity(value, fallback) == expected


@pytest.mark.parametrize("value,expected", [(0, "0"), (-3, "0"), (12345, "12 345")])
def test_format_count_clamps_and_groups_thousands(value, expected):
    assert UnitProductionPanel._format_count(value) == expected


@pytest.mark.parametrize("value,expected", [("bad", 0.0), ("-3", 0.0), ("2.5", 2.5)])
def test_number_helper_returns_nonnegative_numeric_values(value, expected):
    assert UnitProductionPanel._number(value) == pytest.approx(expected)


def test_queue_priority_actions_cover_cancel_pause_resume_and_priority_update():
    panel = UnitProductionPanel()
    client = Client()
    context = SimpleNamespace(net_client=client)
    order = {"id": "Q1", "priority": 50, "status": "queued"}

    panel._apply_queue_priority_choice(order, 4, context)
    assert isinstance(client.actions[-1], ActionCancelProductionOrder)

    panel._apply_queue_priority_choice(order, 3, context)
    assert isinstance(client.actions[-1], ActionSetProductionPaused)
    assert client.actions[-1].is_paused is True
    assert panel._queue_priority_overrides["Q1"] == 50

    panel._apply_queue_priority_choice({**order, "status": "paused"}, 0, context)
    assert isinstance(client.actions[-2], ActionSetProductionPaused)
    assert client.actions[-2].is_paused is False
    assert isinstance(client.actions[-1], ActionSetProductionPriority)
    assert client.actions[-1].priority == 100
    assert panel._queue_priority_overrides["Q1"] == 100

    count = len(client.actions)
    panel._apply_queue_priority_choice(order, 0, SimpleNamespace(net_client=None))
    assert len(client.actions) == count
