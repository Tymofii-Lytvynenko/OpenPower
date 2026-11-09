from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl

from src.client.controllers.unit_move_orders import UnitMoveOrders
from src.shared.actions import ActionMoveUnit, ActionInvadeTerritory
from src.shared.state import GameState


def setup_orders():
    state = GameState(tables={
        "units": pl.DataFrame([dict(id=key, owner=owner, strength=100) for key, owner in
                               (("one", "UKR"), ("two", "UKR"), ("foreign", "POL"))]),
        "regions": pl.DataFrame([dict(id=1, owner="UKR", controller="UKR"),
                                 dict(id=2, owner="POL", controller="POL"),
                                 dict(id=3, owner="DEU", controller="DEU")]),
    })
    client = SimpleNamespace(player_id="player", get_state=lambda: state, send_action=Mock())
    notice = Mock()
    return state, client, notice, UnitMoveOrders(client, "UKR", notice, lambda: "entry-test")


def test_neutral_request_waits_for_yes_and_preserves_each_queued_move():
    state, client, _, orders = setup_orders()
    assert orders.request({"one", "foreign"}, 2, 52, 21)
    assert orders.request({"two"}, 2, 53, 22)
    client.send_action.assert_not_called()
    assert len(orders.pending["POL"]) == 2
    orders.confirm("POL")
    actions = [call.args[0] for call in client.send_action.call_args_list]
    assert [a.unit_ids for a in actions] == [["one"], ["two"]]
    assert [a.target_latitude for a in actions] == [52, 53]
    assert all(isinstance(a, ActionInvadeTerritory) and a.expected_controller == "POL" for a in actions)
    orders.confirm("POL")
    assert client.send_action.call_count == 2


def test_no_cancels_only_that_country_without_dispatch():
    _, client, _, orders = setup_orders()
    orders.request({"one"}, 2, 52, 21)
    orders.request({"two"}, 3, 51, 13)
    orders.cancel("POL")
    assert set(orders.pending) == {"DEU"}
    client.send_action.assert_not_called()


def test_own_and_existing_hostile_destinations_keep_normal_move_semantics():
    state, client, _, orders = setup_orders()
    assert orders.request({"one"}, 1, 50, 30)
    state.tables["countries_wars"] = pl.DataFrame([dict(side_a=["UKR"], side_b=["POL"], status="active")])
    assert orders.request({"one"}, 2, 52, 21)
    assert all(isinstance(call.args[0], ActionMoveUnit) for call in client.send_action.call_args_list)
    assert not orders.pending


def test_new_stationing_rights_avoid_a_war_when_confirmation_is_stale():
    state, client, _, orders = setup_orders()
    orders.request({"one"}, 2, 52, 21)
    state.tables["treaty_effects"] = pl.DataFrame([dict(country_id="UKR", effect="stationing_rights", detail='["POL"]')])
    orders.confirm("POL")
    assert isinstance(client.send_action.call_args.args[0], ActionMoveUnit)


def test_changed_controller_or_unit_removal_cannot_dispatch_stale_intent():
    for change in ("controller", "units"):
        state, client, notice, orders = setup_orders()
        orders.request({"one"}, 2, 52, 21)
        if change == "controller":
            state.tables["regions"] = state.tables["regions"].with_columns(pl.lit("DEU").alias("controller"))
        else:
            state.tables["units"] = state.tables["units"].clear()
        orders.confirm("POL")
        client.send_action.assert_not_called()
        notice.assert_called_once()
        assert not orders.pending


def test_map_controller_routes_a_move_through_confirmation_before_dispatch():
    from src.client.controllers.unit_interaction_controller import UnitInteractionController
    _, client, _, orders = setup_orders()
    controller = UnitInteractionController(None, None, client, on_move_requested=orders.request)
    controller.move_units_to_target({"one"}, 2, 52, 21)
    client.send_action.assert_not_called()
    assert orders.pending["POL"][0].unit_ids == ("one",)


def test_invalid_destination_and_unowned_units_are_rejected():
    _, client, _, orders = setup_orders()

    assert not orders.request({"one"}, 0, 52, 21)
    assert not orders.request({"one"}, 999, 52, 21)
    assert not orders.request({"foreign"}, 2, 52, 21)
    client.send_action.assert_not_called()


def test_malformed_stationing_rights_are_ignored_while_queueing_neutral_move():
    state, client, _, orders = setup_orders()
    state.tables["treaty_effects"] = pl.DataFrame(
        {
            "country_id": ["POL", "UKR", "UKR"],
            "effect": ["stationing_rights", "military_access", "stationing_rights"],
            "detail": ['["POL"]', '["POL"]', "{"],
        }
    )

    assert orders.request({"one"}, 2, 52, 21)

    assert len(orders.pending["POL"]) == 1
    client.send_action.assert_not_called()
