"""Authoritative diplomatic sponsorship, valuation, and relationship effects."""
import polars as pl
import pytest

from modules.base.schema import ensure_base_tables
from modules.base.systems.world.treaty_diplomacy import DiplomacySystem
from modules.base.systems.world.treaty_pressure_policy import (
    national_pressure_ratios,
    pressure_relation_loss_counts,
    treaty_pressure_summary,
)
from src.shared.actions import ActionRespondTreaty, ActionSetTreatyPressure
from src.shared.events import EventNewDay
from src.shared.state import GameState


def pressure_state():
    system = DiplomacySystem()
    state = GameState(tables={
        "countries": pl.DataFrame({"id": ["USA", "CAN", "GBR"]}),
        "unit_designs": pl.DataFrame({"id": ["US", "CA", "GB"], "cost": [100.0, 200.0, 20.0]}),
        "units": pl.DataFrame({"owner": ["USA", "CAN", "GBR"], "design_id": ["US", "CA", "GB"], "equipment_quantity": [1, 1, 1]}),
    })
    ensure_base_tables(state)
    state.globals["player_country_map"] = {"player": "USA", "canadian": "CAN"}
    state.tables["pending_treaties"] = system._pending(pl.DataFrame([{
        "id": "P1", "source_country_id": "USA", "target_country_id": "CAN",
        "treaty_type": "alliance", "members": ["USA", "CAN"],
        "side_a": ["USA", "CAN"], "required_responses": ["CAN"],
        "accepted_members": ["USA"], "status": "pending", "pressure_members": [],
    }]))
    return state, system


def test_sponsorship_is_reversible_and_never_signs_for_the_target():
    state, system = pressure_state()
    state.current_actions = [ActionSetTreatyPressure("player", "P1", "USA")]
    system.update(state, 0.0)
    proposal = state.tables["pending_treaties"].to_dicts()[0]
    assert proposal["pressure_members"] == ["USA"]
    assert proposal["accepted_members"] == ["USA"]
    assert state.tables["countries_treaties"].is_empty()
    summary = treaty_pressure_summary(state, proposal)
    assert summary["share"] == pytest.approx(100.0 / 320.0)
    countries = {row["id"]: row for row in state.tables["countries"].to_dicts()}
    assert countries["CAN"]["political_pressure"] == pytest.approx(100.0 / 201.0)
    assert countries["USA"]["political_pressure"] == 0.0
    state.current_actions = [ActionSetTreatyPressure("player", "P1", "USA", False)]
    system.update(state, 0.0)
    assert state.tables["pending_treaties"].to_dicts()[0]["pressure_members"] == []
    assert state.tables["countries"]["political_pressure"].sum() == 0.0


def test_unauthorized_and_self_pressuring_commands_do_not_mutate_support():
    state, system = pressure_state()
    for action in (ActionSetTreatyPressure("player", "P1", "CAN"),
                   ActionSetTreatyPressure("canadian", "P1", "CAN")):
        state.current_actions = [action]
        system.update(state, 0.0)
        assert state.tables["pending_treaties"].to_dicts()[0]["pressure_members"] == []
        assert state.journal.command_results[-1]["status"] == "rejected"


def test_acceptance_preserves_sponsors_and_removes_unanswered_pressure():
    state, system = pressure_state()
    state.current_actions = [ActionSetTreatyPressure("player", "P1", "USA"),
                             ActionRespondTreaty("canadian", "P1", "CAN", True)]
    system.update(state, 0.0)
    assert state.tables["pending_treaties"].is_empty()
    agreement = state.tables["countries_treaties"].to_dicts()[0]
    assert agreement["pressure_members"] == ["USA"]
    assert state.tables["countries"]["political_pressure"].sum() == 0.0


def test_sponsor_is_deduplicated_across_proposals_and_force_changes_refresh_pressure():
    state, system = pressure_state()
    proposal = state.tables["pending_treaties"].to_dicts()[0]
    proposal["pressure_members"] = ["USA"]
    state.tables["pending_treaties"] = system._pending(pl.DataFrame([proposal, {**proposal, "id": "P2"}]))
    ratios = national_pressure_ratios(state, None, state.tables["pending_treaties"])
    assert ratios["CAN"] == pytest.approx(100.0 / 201.0)
    state.current_actions = []
    system.update(state, 0.0)
    state.tables["units"] = state.tables["units"].filter(pl.col("owner") != "USA")
    system.update(state, 0.0)
    assert state.tables["countries"]["political_pressure"].sum() == 0.0


def test_pending_pressure_causes_daily_relation_loss():
    state, system = pressure_state()
    state.current_actions = [ActionSetTreatyPressure("player", "P1", "USA")]
    system.update(state, 0.0)
    state.current_actions = []
    state.events = [EventNewDay(2, 1, 2001)]
    system.update(state, 0.0)
    rows = state.tables["countries_relations"].filter((pl.col("source") == "USA") & (pl.col("target") == "CAN"))
    assert rows["value"][0] == pytest.approx(-15.0 / 365.25)


def test_relationship_loss_is_applied_once_per_pressured_treaty():
    state, system = pressure_state()
    proposal = state.tables["pending_treaties"].to_dicts()[0]
    proposal["pressure_members"] = ["USA"]
    state.tables["pending_treaties"] = system._pending(
        pl.DataFrame([proposal, {**proposal, "id": "P2"}])
    )
    state.events = [EventNewDay(2, 1, 2001)]

    system.update(state, 0.0)

    rows = state.tables["countries_relations"].filter(
        (pl.col("source") == "USA") & (pl.col("target") == "CAN")
    )
    assert rows["value"][0] == pytest.approx(-30.0 / 365.25)
    assert pressure_relation_loss_counts(
        None, state.tables["pending_treaties"]
    ) == {("USA", "CAN"): 2}


def test_unpressured_treaties_skip_world_force_aggregation(monkeypatch):
    state, system = pressure_state()
    proposal = state.tables["pending_treaties"].to_dicts()[0]

    def fail_if_force_is_aggregated(_state):
        raise AssertionError("No force values are needed when there are no pressure sponsors.")

    monkeypatch.setattr(
        "modules.base.systems.world.treaty_pressure_policy.military_values",
        fail_if_force_is_aggregated,
    )

    assert national_pressure_ratios(state, None, state.tables["pending_treaties"]) == {}
    assert treaty_pressure_summary(state, proposal) == {"share": None, "countries": ()}
