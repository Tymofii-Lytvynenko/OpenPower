from pathlib import Path

import polars as pl

from src.server.session import GameSession
from src.shared.actions import (
    ActionCreateTreaty,
    ActionMoveUnit,
    ActionSetGameSpeed,
    ActionSetGovernmentForm,
    ActionSetPaused,
    ActionSetTax,
    ActionUpdateBudget,
)
from src.shared.config import GameConfig
from src.shared.events import EventNewDay, EventRandomEventTriggered, EventRealSecond


PLAYER_TAG = "UKR"
PLAYER_ID = "local_admin"


def _population_totals(state):
    regions = state.tables["regions"]
    return tuple(int(regions[column].sum() or 0) for column in ("pop_14", "pop_15_64", "pop_65"))


def _adjacent_owned_destination(state, country_tag):
    regions = state.tables["regions"]
    owner_by_region = {
        int(region_id): str(owner or "").strip().upper()
        for region_id, owner in regions.select("id", "owner").iter_rows()
    }
    adjacency = state.tables["region_adjacency"]
    units = state.tables["units"].filter(
        (pl.col("owner") == country_tag) & pl.col("current_region_id").is_not_null()
    )
    for unit in units.iter_rows(named=True):
        source_region = int(unit["current_region_id"])
        neighbors = adjacency.filter(pl.col("region_id") == source_region)
        destination = next(
            (
                int(neighbor_id)
                for neighbor_id in neighbors["neighbor_region_id"].to_list()
                if owner_by_region.get(int(neighbor_id)) == country_tag
            ),
            None,
        )
        if destination is not None:
            return unit, destination
    raise AssertionError(f"No {country_tag} unit has an adjacent friendly region.")


def _treaty_target(state, source_country):
    existing_pairs = set()
    for table_name in ("countries_treaties", "pending_treaties"):
        table = state.tables.get(table_name)
        if table is None or "members" not in table.columns or "treaty_type" not in table.columns:
            continue
        for row in table.iter_rows(named=True):
            members = {str(member).strip().upper() for member in (row.get("members") or [])}
            if str(row.get("treaty_type") or "").strip().lower() == "cultural_exchanges":
                existing_pairs.update(
                    (source_country, member)
                    for member in members
                    if member != source_country and source_country in members
                )

    candidates = state.tables["countries"]["id"].to_list()
    return next(
        (
            str(candidate)
            for candidate in candidates
            if str(candidate).strip().upper() != source_country
            and (source_country, str(candidate).strip().upper()) not in existing_pairs
        ),
        None,
    )


def test_freeplay_session_advances_and_applies_core_actions_without_campaign_outcomes():
    session = GameSession.create_headless(
        GameConfig(Path(__file__).resolve().parents[1]),
        player_tag=PLAYER_TAG,
        random_seed=5,
    )
    session.tick(0.1)
    state = session.state

    assert state.globals["player_tag"] == PLAYER_TAG
    assert state.tables["campaigns"].is_empty()
    starting_minute = state.time.total_minutes
    starting_population = _population_totals(state)

    session.receive_action(ActionSetPaused(PLAYER_ID, True))
    session.receive_action(ActionSetGameSpeed(PLAYER_ID, 5))
    session.tick(1.0)

    assert state.time.total_minutes == starting_minute
    assert state.time.is_paused
    assert state.time.speed_level == 5

    session.receive_action(ActionSetPaused(PLAYER_ID, False))
    session.tick(1.0)
    first_running_minute = state.time.total_minutes
    assert first_running_minute == starting_minute + 2400
    assert not state.time.is_paused
    assert any(isinstance(event, EventNewDay) for event in state.events)
    assert state.tables["campaigns"].is_empty()

    session.tick(1.0)
    assert state.time.total_minutes == first_running_minute + 2400
    assert any(
        isinstance(event, EventRealSecond) and event.game_seconds_passed > 0
        for event in state.events
    )
    assert _population_totals(state) != starting_population
    assert session.engine.systems_map["base.ai"].last_decisions.height > 0
    assert any(isinstance(event, EventRandomEventTriggered) for event in state.events)
    assert state.tables["campaigns"].is_empty()

    state.globals["economic_health_terms"] = {
        "policy_delay_minutes": 0,
        "policy_cooldown_minutes": 0,
        "personal_income_tax_rate_transition_cost": 0.0,
    }
    session.receive_action(ActionSetTax(PLAYER_ID, PLAYER_TAG, 0.37))
    session.tick(0.1)
    tax_rate = state.tables["countries"].filter(pl.col("id") == PLAYER_TAG)[
        "personal_income_tax_rate"
    ][0]
    assert tax_rate == 0.37
    assert state.tables["economic_policy_transitions"].filter(
        (pl.col("country_id") == PLAYER_TAG)
        & (pl.col("policy_name") == "personal_income_tax_rate")
        & (pl.col("target_value") == 0.37)
    ).height == 1

    government = state.tables["country_governments"].filter(
        pl.col("country_id") == PLAYER_TAG
    ).row(0, named=True)
    previous_martial_law = bool(government["martial_law"])
    session.receive_action(
        ActionSetGovernmentForm(
            PLAYER_ID,
            PLAYER_TAG,
            government["government_form_id"],
            government["government_form_id"],
            previous_martial_law,
            not previous_martial_law,
        )
    )
    session.tick(0.1)
    updated_government = state.tables["country_governments"].filter(
        pl.col("country_id") == PLAYER_TAG
    ).row(0, named=True)
    assert bool(updated_government["martial_law"]) is not previous_martial_law
    assert state.tables["political_history"].filter(
        (pl.col("country_id") == PLAYER_TAG)
        & (pl.col("event_type") == "martial_law_changed")
    ).height == 1

    target_country = _treaty_target(state, PLAYER_TAG)
    assert target_country is not None
    treaty_title = "Freeplay core loop test proposal"
    session.receive_action(
        ActionCreateTreaty(
            PLAYER_ID,
            PLAYER_TAG,
            target_country,
            "cultural_exchanges",
            treaty_title,
            "A deterministic freeplay proposal.",
        )
    )
    session.tick(0.1)
    assert state.tables["pending_treaties"].filter(
        (pl.col("source_country_id") == PLAYER_TAG)
        & (pl.col("target_country_id") == target_country)
        & (pl.col("title") == treaty_title)
        & (pl.col("status") == "pending")
    ).height == 1

    unit, destination = _adjacent_owned_destination(state, PLAYER_TAG)
    session.receive_action(ActionMoveUnit(PLAYER_ID, str(unit["id"]), destination))
    session.tick(0.1)
    movement_order = state.tables["unit_pending_orders"].filter(
        pl.col("unit_id") == str(unit["id"])
    )
    movement_feedback = state.tables["unit_order_feedback"].filter(
        (pl.col("unit_id") == str(unit["id"]))
        & pl.col("status").is_in(["queued", "accepted", "executed"])
    )
    assert not movement_order.is_empty() or not movement_feedback.is_empty()

    session.receive_action(
        ActionUpdateBudget(PLAYER_ID, PLAYER_TAG, {"unsupported_budget_field": 0.3})
    )
    session.tick(0.1)
    budget_rejection = next(
        result
        for result in reversed(state.journal.command_results)
        if result.get("action_type") == "ActionUpdateBudget"
        and result.get("player_id") == PLAYER_ID
        and result.get("status") == "rejected"
    )
    assert budget_rejection["status"] == "rejected"
    assert "unsupported budget fields" in budget_rejection["reason"].lower()
    assert "unsupported_budget_field" in budget_rejection["reason"]
    assert state.tables["campaigns"].is_empty()
