from types import SimpleNamespace
from unittest.mock import Mock, patch

import polars as pl
import pytest

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.covert_cell_control import set_cell_activity
from modules.base.systems.military.covert_operations_system import CovertOperationsSystem
from modules.base.systems.military.region_route_snapshot import RegionRouteSnapshot
from modules.base.systems.military.region_travel_time import RegionTravelTime
from src.shared.actions import ActionRetargetCovertCell, ActionSetCovertCellActivity, ActionSetCovertCellAssignment
from src.shared.actions import ActionRetireCovertCell
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


def test_activity_rejects_unknown_cells_before_mutating_anything():
    state = world()
    action = ActionSetCovertCellActivity("player", "missing", False, "POL", "active")

    reason = set_cell_activity(state, [], [], action)

    assert reason == "The issuer cannot edit this covert cell."


def test_activity_cannot_be_enabled_before_communications_are_ready():
    state = world()
    state.update_table(
        "covert_cells",
        state.get_table("covert_cells").with_columns(
            pl.lit(False).alias("communications_ready")
        ),
    )
    cell = state.get_table("covert_cells").to_dicts()
    action = ActionSetCovertCellActivity("player", "cell", True, "POL", "active")

    reason = set_cell_activity(state, cell, [], action)

    assert reason == "The cell must reach its assignment and restore communications before activation."


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


def test_retarget_handles_same_country_changed_ownership_missing_regions_and_overflow():
    def retarget(state, action):
        system = CovertOperationsSystem()
        cells = state.get_table("covert_cells").to_dicts()
        missions = state.get_table("covert_missions").to_dicts()
        routes = state.get_table("covert_cell_routes").to_dicts()
        regions = state.tables.get("regions")
        travel_time = RegionTravelTime(regions)
        routing = RegionRouteSnapshot(regions, state.tables.get("region_adjacency"))
        reason = system._retarget_cell(state, cells, missions, routes, action, travel_time, routing)
        return reason, cells, routes

    state = world()
    reason, cells, _routes = retarget(
        state, ActionRetargetCovertCell("player", "cell", "POL", "POL", "active")
    )
    assert reason == ""
    assert cells[0]["assignment"] == "espionage"

    state = world()
    state.update_table(
        "covert_cells",
        state.get_table("covert_cells").with_columns(pl.lit("DEU").alias("target_country_id")),
    )
    reason, cells, _routes = retarget(
        state, ActionRetargetCovertCell("player", "cell", "POL", "DEU", "active")
    )
    assert reason == ""
    assert cells[0]["assignment"] == "unassigned"

    state = world()
    route_schema = state.get_table("covert_cell_routes").schema
    route = {name: None for name in route_schema}
    route.update(cell_id="cell", owner_country_id="UKR", destination_region_id=2, status="arrived")
    state.update_table("covert_cell_routes", pl.DataFrame([route], schema=route_schema))
    state.update_table(
        "regions",
        state.get_table("regions").with_columns(
            pl.when(pl.col("id") == 2).then(pl.lit("DEU")).otherwise(pl.col("owner")).alias("owner")
        ),
    )
    reason, _cells, _routes = retarget(
        state, ActionRetargetCovertCell("player", "cell", "DEU", "POL", "active")
    )
    assert reason == "The recorded deployment location changed ownership."

    state = world()
    state.tables.pop("regions")
    reason, _cells, _routes = retarget(
        state, ActionRetargetCovertCell("player", "cell", "DEU", "POL", "active")
    )
    assert reason == "A valid current location or destination region is unavailable."

    state = world()
    state.time.total_minutes = 9_223_372_036_854_775_807
    reason, _cells, _routes = retarget(
        state, ActionRetargetCovertCell("player", "cell", "DEU", "POL", "active")
    )
    assert reason == "The covert transit date exceeds the supported range."


def test_transit_handles_legacy_missing_map_invalid_incomplete_and_replanned_routes():
    system = CovertOperationsSystem()

    state = world()
    legacy_cell = {
        "id": "legacy", "country_id": "UKR", "target_country_id": "POL",
        "status": "transit", "available_at_minute": 10,
    }
    system._advance_cell_transit(state, legacy_cell, [], 10, RegionTravelTime(state.tables["regions"]),
                                RegionRouteSnapshot(state.tables["regions"], state.tables.get("region_adjacency")))
    assert legacy_cell["status"] == "active"
    assert legacy_cell["location_country_id"] == "POL"

    future_cell = {**legacy_cell, "id": "future", "status": "transit"}
    future_route = {"cell_id": "future", "route_region_ids": [1, 2], "route_index": 0,
                    "destination_region_id": 2, "arrival_at_minute": 20, "status": "in_transit"}
    before = dict(future_route)
    system._advance_cell_transit(state, future_cell, [future_route], 10, RegionTravelTime(state.tables["regions"]),
                                RegionRouteSnapshot(state.tables["regions"], state.tables.get("region_adjacency")))
    assert future_route == before

    missing_map_state = world()
    missing_map_routing = RegionRouteSnapshot(
        missing_map_state.tables["regions"], missing_map_state.tables.get("region_adjacency")
    )
    missing_map_travel = RegionTravelTime(missing_map_state.tables["regions"])
    missing_map_state.tables.pop("regions")
    missing_map_cell = {"id": "missing-map", "country_id": "UKR", "target_country_id": "DEU", "status": "transit"}
    missing_map_route = {"cell_id": "missing-map", "route_region_ids": [1, 3], "route_index": 0,
                         "destination_region_id": 3, "arrival_at_minute": 0, "status": "in_transit"}
    system._advance_cell_transit(missing_map_state, missing_map_cell, [missing_map_route], 1,
                                missing_map_travel, missing_map_routing)
    assert missing_map_route["rejection_reason"] == "The region map is unavailable."

    invalid_cell = {"id": "invalid", "country_id": "UKR", "target_country_id": "DEU", "status": "transit"}
    invalid_route = {"cell_id": "invalid", "route_region_ids": [0], "route_index": 0,
                     "destination_region_id": 0, "arrival_at_minute": 0, "status": "in_transit"}
    system._advance_cell_transit(state, invalid_cell, [invalid_route], 1, RegionTravelTime(state.tables["regions"]),
                                RegionRouteSnapshot(state.tables["regions"], state.tables.get("region_adjacency")))
    assert invalid_route["rejection_reason"] == "The current or destination region is invalid."

    arrived_cell = {"id": "already-there", "country_id": "UKR", "target_country_id": "DEU", "status": "transit"}
    arrived_route = {"cell_id": "already-there", "route_region_ids": [3], "route_index": 0,
                     "destination_region_id": 3, "arrival_at_minute": 0, "status": "in_transit"}
    system._advance_cell_transit(state, arrived_cell, [arrived_route], 1, RegionTravelTime(state.tables["regions"]),
                                RegionRouteSnapshot(state.tables["regions"], state.tables.get("region_adjacency")))
    assert arrived_route["status"] == "arrived"
    assert arrived_cell["location_country_id"] == "DEU"

    incomplete_cell = {"id": "incomplete", "country_id": "UKR", "target_country_id": "DEU", "status": "transit"}
    incomplete_route = {"cell_id": "incomplete", "route_region_ids": [1], "route_index": 0,
                        "destination_region_id": 3, "arrival_at_minute": 0, "status": "in_transit"}
    system._advance_cell_transit(state, incomplete_cell, [incomplete_route], 1, RegionTravelTime(state.tables["regions"]),
                                RegionRouteSnapshot(state.tables["regions"], state.tables.get("region_adjacency")))
    assert incomplete_route["rejection_reason"] == "The remaining route is incomplete."

    reroute_cell = {"id": "reroute", "country_id": "UKR", "target_country_id": "DEU", "status": "transit"}
    reroute = {"cell_id": "reroute", "route_region_ids": [2, 3], "route_index": 0,
               "destination_region_id": 3, "arrival_at_minute": 0, "status": "in_transit"}
    regions = state.tables["regions"]
    routing = RegionRouteSnapshot(regions, state.tables.get("region_adjacency"))
    travel_time = RegionTravelTime(regions)
    with (
        patch.object(system, "_cell_region_access", return_value=False),
        patch.object(system, "_plan_cell_route_from_region", return_value=SimpleNamespace(
            is_valid=True, region_ids=[2, 3], rejection_reason=""
        )),
    ):
        system._advance_cell_transit(state, reroute_cell, [reroute], 1, travel_time, routing)
    assert reroute["status"] == "in_transit"
    assert reroute["arrival_at_minute"] > 1


def test_assignment_and_retirement_reject_invalid_requests():
    state = world()
    apply(state, ActionSetCovertCellAssignment("player", "missing", "espionage"))
    assert state.journal.command_results[-1]["status"] == "rejected"

    apply(state, ActionSetCovertCellAssignment("player", "cell", "unsupported"))
    assert state.journal.command_results[-1]["reason"] == "The requested cell assignment is not supported."

    apply(state, ActionSetCovertCellAssignment("player", "cell", "dormant"))
    assert state.get_table("covert_cells")["status"][0] == "dormant"

    apply(state, ActionRetireCovertCell("player", "missing"))
    assert state.journal.command_results[-1]["reason"] == "The cell cannot be retired by this issuer."
