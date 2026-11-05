from types import SimpleNamespace
from unittest.mock import Mock

import polars as pl
import pytest

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.covert_operations_system import CovertOperationsSystem
from src.shared.actions import ActionRetargetCovertCell, ActionSetCovertCellActivity, ActionSetCovertCellAssignment
from src.shared.state import GameState
from src.client.ui.panels.military.covert_roster_controls import CovertRosterControls


def world():
    state = GameState(tables={
        "countries": pl.DataFrame(dict(id=["UKR", "POL", "DEU"], money_reserves=[1000., 1000., 1000.])),
        "regions": pl.DataFrame(dict(id=[1, 2, 3], owner=["UKR", "POL", "DEU"],
                                    latitude=[0., 0., 0.], longitude=[0., 1., 2.])),
        "region_adjacency": pl.DataFrame(dict(region_id=[1, 2], neighbor_region_id=[2, 3])),
        "covert_cells": pl.DataFrame([dict(id="cell", country_id="UKR", target_country_id="POL",
            location_country_id="POL", status="active", communications_ready=True, assignment="espionage")]),
    })
    ensure_base_tables(state)
    state.globals["player_country_map"] = {"player": "UKR", "other": "POL"}
    return state


def apply(state, action):
    state.current_actions, state.events = [action], []
    CovertOperationsSystem().update(state, 0)


def test_activity_can_sleep_and_wake_without_charges_or_state_alias_trap():
    state = world()
    apply(state, ActionSetCovertCellActivity("player", "cell", False, "POL", "active"))
    assert state.get_table("covert_cells")["status"][0] == "dormant"
    state.update_table("covert_cells", state.get_table("covert_cells").with_columns(pl.lit("dormant").alias("assignment")))
    apply(state, ActionSetCovertCellActivity("player", "cell", True, "POL", "dormant"))
    cell = state.get_table("covert_cells").to_dicts()[0]
    assert (cell["status"], cell["assignment"]) == ("active", "unassigned")
    assert state.get_table("countries")["money_reserves"].to_list() == [1000.] * 3


def test_legacy_assignment_can_reactivate_a_dormant_cell():
    state = world()
    state.update_table("covert_cells", state.get_table("covert_cells").with_columns(pl.lit("dormant").alias("status")))
    apply(state, ActionSetCovertCellAssignment("player", "cell", "espionage"))
    assert state.get_table("covert_cells")["status"][0] == "active"


def test_retarget_uses_route_and_arrival_survives_ipc_without_teleporting():
    state = world()
    apply(state, ActionRetargetCovertCell("player", "cell", "DEU", "POL", "active"))
    cell = state.get_table("covert_cells").to_dicts()[0]
    assert (cell["status"], cell["location_country_id"], cell["target_country_id"]) == ("transit", "POL", "DEU")
    assert state.get_table("covert_cell_routes")["route_region_ids"][0].to_list() == [2, 3]
    restored = GameState.from_ipc(state.to_ipc())
    for item in (state, restored):
        item.current_actions, item.events = [], []
        item.time.total_minutes = cell["available_at_minute"]
        CovertOperationsSystem().update(item, 0)
        assert item.get_table("covert_cells")["location_country_id"][0] == "DEU"
        assert item.get_table("covert_cells")["status"][0] == "active"
    assert state.get_table("covert_cell_routes").equals(restored.get_table("covert_cell_routes"))


@pytest.mark.parametrize("case", ["foreign", "stale-country", "stale-status", "busy", "mission", "missing", "communications", "boolean"])
def test_refused_edits_preserve_cells_routes_and_funds(case):
    state = world()
    if case == "busy":
        state.update_table("covert_cells", state.get_table("covert_cells").with_columns(
            pl.lit("training").alias("status"), pl.lit(100.).alias("training_required"),
            pl.lit(100).cast(pl.Int64).alias("training_completes_at_minute")))
    if case == "mission":
        row = dict(id="mission", cell_id="cell", owner_country_id="UKR", status="ready")
        state.update_table("covert_missions", pl.DataFrame([row], schema={k:v for k,v in state.get_table("covert_missions").schema.items() if k in row}))
        ensure_base_tables(state)
    if case == "communications":
        state.update_table("covert_cells", state.get_table("covert_cells").with_columns(pl.lit(False).alias("communications_ready")))
    before = {name: state.get_table(name).clone() for name in ("covert_cells", "covert_cell_routes", "countries")}
    action = ActionRetargetCovertCell("other" if case == "foreign" else "player", "cell",
        "ZZZ" if case == "missing" else "DEU", "UKR" if case == "stale-country" else "POL",
        "training" if case == "busy" else "idle" if case == "stale-status" else "active")
    if case == "boolean":
        action = ActionSetCovertCellActivity("player", "cell", 1, "POL", "active")
    apply(state, action)
    assert state.journal.command_results[-1]["status"] == "rejected"
    assert all(state.get_table(name).equals(frame) for name, frame in before.items())


def test_pending_controls_wait_for_matching_authoritative_result():
    state = world()
    client = SimpleNamespace(player_id="player", send_action=Mock())
    context = SimpleNamespace(target_tag="UKR", is_own_country=True, net_client=client)
    controls = CovertRosterControls()
    controls.update(state, context)
    row = state.get_table("covert_cells").to_dicts()[0]
    action = ActionSetCovertCellActivity("player", "cell", False, "POL", "active")
    assert controls.submit(row, action, context)
    assert not controls.submit(row, action, context)
    state.journal.append_command_result(dict(player_id="other", action_type=type(action).__name__, cell_id="cell", status="rejected"))
    controls.update(state, context)
    assert "cell" in controls.pending
    state.journal.append_command_result(dict(player_id="player", action_type=type(action).__name__, cell_id="cell", status="rejected"))
    controls.update(state, context)
    assert not controls.pending


def test_retarget_requires_access_through_third_country_and_rejects_atomically():
    state = world()
    state.update_table("covert_cells", state.get_table("covert_cells").with_columns(
        pl.lit("DEU").alias("target_country_id"), pl.lit("DEU").alias("location_country_id")))
    before = state.get_table("covert_cells").clone()
    action = ActionRetargetCovertCell("player", "cell", "UKR", "DEU", "active")
    apply(state, action)
    assert state.journal.command_results[-1]["status"] == "rejected"
    assert state.get_table("covert_cells").equals(before)
    assert state.get_table("covert_cell_routes").is_empty()
    state.update_table("treaty_effects", pl.DataFrame([dict(treaty_id="access", country_id="UKR",
        effect="transit_rights", value=1., detail='["POL"]')], schema=state.get_table("treaty_effects").schema))
    apply(state, action)
    assert state.journal.command_results[-1]["status"] == "applied"
    assert state.get_table("covert_cell_routes")["route_region_ids"][0].to_list() == [3, 2, 1]


def test_reassignment_uses_recorded_arrival_instead_of_a_changed_capital():
    state = world()
    state.update_table("regions", pl.concat([state.get_table("regions"), state.get_table("regions").filter(
        pl.col("id") == 2).with_columns(pl.lit(4).cast(state.get_table("regions").schema["id"]).alias("id"))]))
    schema = state.get_table("country_governments").schema
    row = {name: None for name in schema}
    row.update(country_id="POL", capital_region_id=4)
    state.update_table("country_governments", pl.DataFrame([row], schema=schema))
    route_schema = state.get_table("covert_cell_routes").schema
    route = {name: None for name in route_schema}
    route.update(cell_id="cell", owner_country_id="UKR", destination_region_id=2, status="arrived")
    state.update_table("covert_cell_routes", pl.DataFrame([route], schema=route_schema))
    apply(state, ActionRetargetCovertCell("player", "cell", "DEU", "POL", "active"))
    assert state.journal.command_results[-1]["status"] == "applied"
    assert state.get_table("covert_cell_routes")["source_region_id"][0] == 2
