from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl
import pytest

from src.shared.state import GameState
from src.client.ui.panels.military.unit_training_confirmation import UnitTrainingConfirmation, training_offer


def training_state():
    return GameState(tables={
        "units": pl.DataFrame([dict(id="unit-1", owner="UKR", strength=1000,
                                    training_level="Recruit", current_region_id=1)]),
        "unit_training_quotes": pl.DataFrame([dict(unit_id="unit-1", country_id="UKR",
            from_level="Recruit", target_level="Regular", cost=1000.0, required_days=30.0,
            available=True, reason="")]),
    })


def controller():
    client = SimpleNamespace(player_id="player", send_action=Mock())
    notify = Mock()
    return UnitTrainingConfirmation(client, "UKR", notify), client, notify


def test_yes_dispatches_once_and_no_dispatches_nothing():
    state = training_state()
    confirmation, client, _ = controller()
    assert confirmation.request(state, "unit-1")
    assert not confirmation.request(state, "unit-1")
    client.send_action.assert_not_called()
    confirmation.question.answer(False)
    client.send_action.assert_not_called()
    assert confirmation.request(state, "unit-1")
    confirmation.question.answer(True)
    confirmation.question.answer(True)
    client.send_action.assert_called_once()
    action = client.send_action.call_args.args[0]
    assert (action.unit_id, action.target_level, action.expected_cost,
            action.expected_required_days, action.expected_from_level) == (
                "unit-1", "Regular", 1000, 30, "Recruit")


def test_accept_callback_runs_only_after_validated_yes():
    state = training_state()
    confirmation, client, notify = controller()
    on_accept = Mock()

    assert confirmation.request(state, "unit-1", on_accept=on_accept)
    confirmation.question.answer(False)
    on_accept.assert_not_called()
    client.send_action.assert_not_called()

    assert confirmation.request(state, "unit-1", on_accept=on_accept)
    confirmation.question.answer(True)
    on_accept.assert_called_once_with()
    client.send_action.assert_called_once()
    notify.assert_not_called()

    stale_confirmation, stale_client, stale_notify = controller()
    stale_callback = Mock()
    assert stale_confirmation.request(state, "unit-1", on_accept=stale_callback)
    state.update_table("unit_training_quotes", state.get_table("unit_training_quotes").with_columns(
        pl.lit(1200.0).alias("cost")))
    stale_confirmation.question.answer(True)
    stale_callback.assert_not_called()
    stale_client.send_action.assert_not_called()
    stale_notify.assert_called_once()


@pytest.mark.parametrize("table,column,value", [
    ("units", "owner", "POL"), ("units", "strength", 900),
    ("units", "current_region_id", 2), ("units", "training_level", "Regular"),
    ("unit_training_quotes", "cost", 1200.0),
    ("unit_training_quotes", "required_days", 31.0),
    ("unit_training_quotes", "available", False),
])
def test_changed_snapshot_invalidates_open_confirmation(table, column, value):
    state = training_state()
    confirmation, client, notify = controller()
    assert confirmation.request(state, "unit-1")
    state.update_table(table, state.get_table(table).with_columns(pl.lit(value).alias(column)))
    confirmation.question.answer(True)
    client.send_action.assert_not_called()
    notify.assert_called_once()


def test_foreign_missing_and_malformed_offers_are_unavailable():
    state = training_state()
    assert training_offer(state, "unit-1", "POL") is None
    assert training_offer(state, "removed", "UKR") is None
    state.update_table("unit_training_quotes", state.get_table("unit_training_quotes").with_columns(
        pl.lit(float("nan")).alias("cost")))
    assert training_offer(state, "unit-1", "UKR") is None


@pytest.mark.parametrize("column,value", [
    ("is_moving", True),
    ("engagement_mode", "battle"),
    ("training_state", "training"),
])
def test_training_offer_is_unavailable_for_units_already_in_transition(column, value):
    state = training_state()
    state.update_table("units", state.get_table("units").with_columns(pl.lit(value).alias(column)))

    assert training_offer(state, "unit-1", "UKR") is None


def test_batch_request_validates_selection_and_confirms_the_complete_training_plan():
    state = training_state()
    units = state.get_table("units")
    units = units.vstack(pl.DataFrame([{
        "id": "unit-2", "owner": "UKR", "strength": 800, "training_level": "Recruit",
        "current_region_id": 2,
    }], schema=units.schema))
    quotes = state.get_table("unit_training_quotes")
    quotes = quotes.vstack(pl.DataFrame([{
        "unit_id": "unit-2", "country_id": "UKR", "from_level": "Recruit",
        "target_level": "Veteran", "cost": 1250.0, "required_days": 45.0,
        "available": True, "reason": "",
    }], schema=quotes.schema))
    state.update_table("units", units)
    state.update_table("unit_training_quotes", quotes)
    confirmation, client, _notify = controller()
    confirmation.question.show = Mock(return_value=True)

    assert confirmation.request_many(state, ["", None]) is False
    assert confirmation.request_many(state, ["unit-1", "missing"]) is False
    assert confirmation.request_many(state, ["unit-1", "unit-2", "unit-1"])

    message, accept, _cancel = confirmation.question.show.call_args.args
    assert "Train 2 selected units to Regular, Veteran?" in message
    assert "Estimated duration: 30–45 days" in message
    assert "Combined cost: $ 2,250.00" in message
    accept()
    assert {call.args[0].unit_id for call in client.send_action.call_args_list} == {"unit-1", "unit-2"}

    confirmation.question.render = Mock()
    confirmation.render(state)
    confirmation.question.render.assert_called_once_with()
