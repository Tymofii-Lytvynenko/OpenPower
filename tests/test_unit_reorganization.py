import copy
from unittest.mock import Mock, patch

import polars as pl
import pytest

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.military_system import MilitarySystem, UnitFactory
from modules.base.systems.military.unit_reorganization import UnitReorganization
from src.core.map.geo import GeoCoordinate
from src.shared.actions import ActionDisbandUnits, ActionMergeUnits, ActionSplitUnit
from src.shared.state import GameState


def world():
    state = GameState()
    ensure_base_tables(state)
    unit = UnitFactory().create("one", "UKR", "infantry", 101, 1, GeoCoordinate(50,30), 0,
                                design_id="design", equipment_quantity=17)
    unit["original_cost"] = 1001.0
    state.update_table("units", pl.DataFrame([unit]))
    return state


def apply(state, *actions):
    state.current_actions = list(actions)
    state.update_table("units", UnitReorganization.apply(state, state.tables["units"]))


def test_split_merge_conserves_personnel_equipment_cost_and_provenance():
    state = world()
    before = state.tables["units"].to_dicts()[0]
    apply(state, ActionSplitUnit("UKR", "one", 33))
    rows = state.tables["units"].to_dicts()
    assert len(rows) == 2
    assert sum(row["strength"] for row in rows) == 101
    assert sum(row["equipment_quantity"] for row in rows) == 17
    assert sum(row["original_cost"] for row in rows) == pytest.approx(1001.0)
    child = next(row for row in rows if row["id"] != "one")
    assert child["design_id"] == "design"
    assert child["training_level"] == before["training_level"]
    apply(state, ActionMergeUnits("UKR", "one", [child["id"]]))
    assert state.tables["units"].height == 1
    restored = state.tables["units"].to_dicts()[0]
    for key in ("strength", "equipment_quantity", "original_cost"):
        assert restored[key] == pytest.approx(before[key])


@pytest.mark.parametrize("count", [0, -1, 101, 102, True, 1.5])
def test_invalid_split_is_rejected_without_consuming_identifiers(count):
    state = world()
    before = state.tables["units"].clone()
    apply(state, ActionSplitUnit("UKR", "one", count))
    assert state.tables["units"].equals(before)
    assert state.determinism.id_sequence == 0
    assert state.journal.command_results[-1]["status"] == "rejected"


def test_foreign_issuer_cannot_split_or_merge():
    state = world()
    apply(state, ActionSplitUnit("POL", "one", 50))
    assert state.tables["units"].height == 1
    assert state.journal.command_results[-1]["status"] == "rejected"


@pytest.mark.parametrize("field,value", [("is_moving", True), ("training_state", "training"),
                                           ("unit_lifecycle", "deployment_queued"),
                                           ("engagement_mode", "positional"),
                                           ("readiness_transition_id", "transition")])
def test_busy_units_cannot_split(field, value):
    state = world()
    state.update_table("units",state.tables["units"].with_columns(pl.lit(value).alias(field)))
    apply(state, ActionSplitUnit("UKR", "one", 50))
    assert state.tables["units"].height == 1
    assert state.journal.command_results[-1]["status"] == "rejected"


def test_active_battle_blocks_reorganization():
    state = world()
    state.update_table("battles", pl.DataFrame([dict(id="fight",status="active")]))
    state.update_table("battle_units", pl.DataFrame([dict(battle_id="fight",unit_id="one")]))
    apply(state, ActionSplitUnit("UKR", "one", 50))
    assert state.tables["units"].height == 1


@pytest.mark.parametrize("field,value", [("owner", "POL"), ("design_id", "other"),
                                           ("current_region_id", 2), ("latitude", 51.0),
                                           ("training_level", "Elite")])
def test_merge_requires_compatible_owned_colocated_units(field,value):
    state = world()
    row = state.tables["units"].to_dicts()[0]
    state.update_table("units",pl.DataFrame([row,dict(row,id="two",**{field:value})]))
    apply(state, ActionMergeUnits("UKR","one",["two"]))
    assert state.tables["units"].height == 2
    assert state.journal.command_results[-1]["status"] == "rejected"


def test_split_identifiers_are_deterministic_and_not_reused_after_merge():
    state = world()
    duplicate = copy.deepcopy(state)
    apply(state,ActionSplitUnit("UKR","one",50))
    apply(duplicate,ActionSplitUnit("UKR","one",50))
    assert state.tables["units"].equals(duplicate.tables["units"])
    child = state.tables["units"]["id"].to_list()[1]
    apply(state,ActionMergeUnits("UKR","one",[child]))
    apply(state,ActionSplitUnit("UKR","one",50))
    assert child not in state.tables["units"]["id"].to_list()


def test_reorganization_commands_are_routed_to_authoritative_military_system():
    assert {ActionSplitUnit, ActionMergeUnits, ActionDisbandUnits}.issubset(MilitarySystem.access.handles)


def test_military_update_executes_split_without_advancing_time():
    state = world()
    state.current_actions = [ActionSplitUnit("UKR","one",33)]
    MilitarySystem().update(state,0.0)
    assert state.tables["units"].height == 2
    assert state.tables["units"]["strength"].sum() == 101
    assert state.tables["units"]["equipment_quantity"].sum() == 17


def test_active_order_and_malformed_merge_do_not_change_units():
    state = world()
    state.update_table("unit_pending_orders",pl.DataFrame([dict(id="pending",unit_id="one",status="queued")]))
    apply(state,ActionSplitUnit("UKR","one",50))
    assert state.tables["units"].height == 1
    assert state.journal.command_results[-1]["status"] == "rejected"
    apply(state,ActionMergeUnits("UKR","one",None))
    assert state.tables["units"].height == 1
    assert state.journal.command_results[-1]["status"] == "rejected"


def test_split_survives_snapshot_transport_with_identifier_state():
    state = world()
    apply(state,ActionSplitUnit("UKR","one",33))
    loaded = GameState.from_ipc(state.to_ipc())
    assert loaded.tables["units"].equals(state.tables["units"])
    assert loaded.determinism.id_sequence == state.determinism.id_sequence
    apply(loaded,ActionSplitUnit("UKR","one",10))
    assert loaded.tables["units"]["strength"].sum() == 101
    assert len(set(loaded.tables["units"]["id"].to_list())) == 3


def _set_country_military_count(state, country_id, military_count):
    schema = state.tables["countries"].schema
    state.update_table("countries", pl.DataFrame(
        [{"id": country_id, "military_count": military_count}], schema=schema
    ))


def test_disband_removes_selected_units_and_releases_personnel():
    state = world()
    _set_country_military_count(state, "UKR", 101)

    apply(state, ActionDisbandUnits("UKR", ["one"]))

    assert state.tables["units"].is_empty()
    assert state.tables["countries"].filter(pl.col("id") == "UKR")["military_count"][0] == 0
    assert state.journal.command_results[-1]["status"] == "applied"


def test_batch_disband_releases_personnel_for_every_selected_unit():
    state = world()
    original = state.tables["units"].to_dicts()[0]
    state.update_table("units", pl.DataFrame([
        original, dict(original, id="two", strength=50, equipment_quantity=8),
    ], schema=state.tables["units"].schema))
    _set_country_military_count(state, "UKR", 151)

    apply(state, ActionDisbandUnits("UKR", ["one", "two"]))

    assert state.tables["units"].is_empty()
    assert state.tables["countries"]["military_count"][0] == 0
    assert state.journal.command_results[-1]["status"] == "applied"


@pytest.mark.parametrize("unit_ids", [[], ["one", "one"], ["missing"], ["one", "missing"]])
def test_disband_rejects_empty_duplicate_or_stale_unit_selection(unit_ids):
    state = world()
    _set_country_military_count(state, "UKR", 101)
    before = state.tables["units"].clone()

    apply(state, ActionDisbandUnits("UKR", unit_ids))

    assert state.tables["units"].equals(before)
    assert state.tables["countries"]["military_count"][0] == 101
    assert state.journal.command_results[-1]["status"] == "rejected"


@pytest.mark.parametrize("field,value", [
    ("is_moving", True), ("training_state", "training"),
    ("unit_lifecycle", "deployment_queued"), ("engagement_mode", "assault"),
    ("readiness_transition_id", "transition"),
])
def test_disband_rejects_unit_that_is_not_available(field, value):
    state = world()
    _set_country_military_count(state, "UKR", 101)
    state.update_table("units", state.tables["units"].with_columns(pl.lit(value).alias(field)))

    apply(state, ActionDisbandUnits("UKR", ["one"]))

    assert state.tables["units"].height == 1
    assert state.tables["countries"]["military_count"][0] == 101
    assert state.journal.command_results[-1]["status"] == "rejected"


def test_disband_rejects_unit_with_active_deployment_order():
    state = world()
    _set_country_military_count(state, "UKR", 101)
    state.update_table("unit_deployment_orders", pl.DataFrame([
        {"id": "deployment", "unit_id": "one", "status": "blocked"},
    ], schema=state.tables["unit_deployment_orders"].schema))

    apply(state, ActionDisbandUnits("UKR", ["one"]))

    assert state.tables["units"].height == 1
    assert state.tables["countries"]["military_count"][0] == 101
    assert state.journal.command_results[-1]["status"] == "rejected"


def test_disband_rejects_foreign_issuer_without_changing_country_totals():
    state = world()
    _set_country_military_count(state, "UKR", 101)

    apply(state, ActionDisbandUnits("POL", ["one"]))

    assert state.tables["units"].height == 1
    assert state.tables["countries"]["military_count"][0] == 101
    assert state.journal.command_results[-1]["status"] == "rejected"


def test_military_update_executes_disband_and_preserves_delivered_deployment_history():
    state = world()
    _set_country_military_count(state, "UKR", 101)
    state.update_table("unit_deployment_orders", pl.DataFrame([
        {"id": "deployment", "unit_id": "one", "status": "delivered"},
    ], schema=state.tables["unit_deployment_orders"].schema))
    state.current_actions = [ActionDisbandUnits("UKR", ["one"])]

    MilitarySystem().update(state, 0.0)

    assert state.tables["units"].is_empty()
    assert state.tables["countries"]["military_count"][0] == 0
    assert state.tables["unit_deployment_orders"]["status"][0] == "delivered"


def test_invalid_unit_counts_and_missing_disband_country_data_are_rejected():
    unit = {"id": "one", "owner": "UKR", "strength": 0, "equipment_quantity": 0}
    assert UnitReorganization._unavailable_reason(GameState(), unit) == (
        "The unit has an invalid personnel or equipment count."
    )
    assert UnitReorganization._disband(GameState(), [unit], [unit]) == (
        "Country military totals are unavailable."
    )

    state = GameState(
        tables={"countries": pl.DataFrame({"id": ["UKR"], "military_count": [10]})}
    )
    foreign_unit = dict(unit, strength=5, owner="POL")
    assert UnitReorganization._disband(state, [foreign_unit], [foreign_unit]) == (
        "The owner country is unavailable."
    )


def test_split_retries_a_deterministic_identifier_that_already_exists():
    state = GameState()
    unit = {"id": "one", "strength": 10, "equipment_quantity": 3}
    rows = [unit]
    runtime = Mock()
    runtime.next_id.side_effect = ["one", "unit-split-child"]

    with patch(
        "modules.base.systems.military.unit_reorganization.DeterministicRuntime",
        return_value=runtime,
    ):
        reason = UnitReorganization._split(state, rows, unit, 5)

    assert reason == ""
    assert [row["id"] for row in rows] == ["one", "unit-split-child"]
    assert runtime.next_id.call_count == 2


def test_merge_rejects_too_few_units_and_invalid_resulting_size():
    unit = {"id": "one", "strength": 10, "equipment_quantity": 2}
    assert UnitReorganization._merge([unit], [unit]) == "Select at least two units to merge."

    invalid = [
        {"id": "one", "strength": 0, "equipment_quantity": 0},
        {"id": "two", "strength": 1, "equipment_quantity": 0},
    ]
    assert UnitReorganization._merge(invalid, invalid) == (
        "The resulting unit would have an invalid size."
    )
