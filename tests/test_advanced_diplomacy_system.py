from __future__ import annotations

import json
import math

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.military_system import MilitarySystem
from modules.base.systems.world.advanced_diplomacy_system import AdvancedDiplomacySystem
from modules.base.systems.world.peace_deal_policy import PeaceDealPolicy
from modules.base.systems.world.treaty_diplomacy import DiplomacySystem
from src.shared.actions import ActionBuildUnit, ActionRespondPeaceDeal, ActionSubmitPeaceDeal
from src.shared.events import (
    EventPeaceDealProposed,
    EventPeaceDealResolved,
    EventTerritoryOwnershipChanged,
)
from src.shared.state import GameState


def _state() -> GameState:
    state = GameState(
        tables={
            "countries": pl.DataFrame(
                {
                    "id": ["USA", "CAN", "GBR"],
                    "gdp": [10_000.0, 8_000.0, 9_000.0],
                    "money_reserves": [4_000.0, 2_000.0, 3_000.0],
                    "military_count": [300, 240, 200],
                }
            ),
            "regions": pl.DataFrame(
                {
                    "id": [1, 2],
                    "owner": ["USA", "USA"],
                    "controller": ["USA", "CAN"],
                    "area_km2": [10_000.0, 20_000.0],
                }
            ),
        }
    )
    ensure_base_tables(state)
    state.update_table(
        "countries_wars",
        pl.DataFrame(
            {
                "id": ["war-1"],
                "side_a": [["USA"]],
                "side_b": [["CAN", "GBR"]],
                "status": ["active"],
                "leader_a": ["USA"],
                "leader_b": ["CAN"],
                "created_at": ["2001-01-01 00:00"],
                "intent_a": ["war"],
                "intent_b": ["war"],
            }
        ),
    )
    state.update_table(
        "countries_treaties",
        pl.DataFrame(
            {
                "id": ["trade-1"],
                "name": ["Bilateral trade"],
                "type": ["economic_partnership"],
                "members": [["USA", "CAN"]],
                "side_a": [["USA"]],
                "side_b": [["CAN"]],
                "status": ["active"],
                "terms": ["trade"],
                "conditions_json": ["{}"],
                "open_to_new_members": [False],
                "suspended_members": [[]],
                "created_at": ["2001-01-01 00:00"],
                "activated_at_minute": [0],
                "expires_at_minute": [0],
                "maintenance_cost": [0.0],
                "source_country_id": ["USA"],
                "target_country_id": ["CAN"],
            }
        ),
    )
    return state


def _clauses() -> list[dict[str, object]]:
    return [
        {
            "type": "war_reparations",
            "payer_country_id": "CAN",
            "recipient_country_id": "USA",
            "amount": 1_200.0,
            "duration_months": 12,
        },
        {
            "type": "territory_transfer",
            "region_id": 2,
            "new_owner_country_id": "CAN",
        },
        {"type": "treaty_annulment", "treaty_id": "trade-1"},
        {
            "type": "demilitarization",
            "country_id": "GBR",
            "maximum_strength": 100,
            "duration_days": 365,
        },
    ]


def test_all_opposing_war_participants_must_accept_then_package_applies_atomically():
    state = _state()
    system = AdvancedDiplomacySystem()
    state.current_actions = [
        ActionSubmitPeaceDeal(
            "USA",
            "war-1",
            "USA",
            offered_clauses=_clauses(),
        )
    ]

    system.update(state, 0.0)

    deal = state.get_table("peace_deals").row(0, named=True)
    deal_id = deal["id"]
    assert deal["responding_side"] == ["CAN", "GBR"]
    assert any(isinstance(event, EventPeaceDealProposed) for event in state.events)

    state.current_actions = [ActionRespondPeaceDeal("CAN", deal_id, "CAN", True)]
    system.update(state, 0.0)
    assert state.get_table("peace_deals").item(0, "status") == "pending"
    assert state.get_table("regions").filter(pl.col("id") == 2).item(0, "owner") == "USA"

    state.current_actions = [ActionRespondPeaceDeal("GBR", deal_id, "GBR", True)]
    system.update(state, 0.0)

    assert state.get_table("peace_deals").item(0, "status") == "accepted"
    assert state.get_table("debt_contracts").item(0, "debt_type") == "reparations"
    assert state.get_table("debt_contracts").item(0, "debtor_country_id") == "CAN"
    assert state.get_table("regions").filter(pl.col("id") == 2).item(0, "owner") == "CAN"
    ownership_events = [
        event
        for event in state.events
        if isinstance(event, EventTerritoryOwnershipChanged)
        and event.region_id == 2
    ]
    assert len(ownership_events) == 1
    assert ownership_events[0].previous_owner == "USA"
    assert ownership_events[0].owner == "CAN"
    assert ownership_events[0].source == "peace_deal"
    assert state.get_table("countries_treaties").item(0, "status") == "terminated"
    assert state.get_table("demilitarization_limits").item(0, "maximum_strength") == 100
    assert sum(isinstance(action, ActionSubmitPeaceDeal) for action in state.current_actions) == 0
    assert any(isinstance(event, EventPeaceDealResolved) for event in state.events)

    DiplomacySystem().update(state, 0.0)
    assert state.get_table("countries_wars").is_empty()


def test_invalid_clause_or_unauthorized_responder_cannot_partially_apply_a_deal():
    state = _state()
    system = AdvancedDiplomacySystem()
    invalid = [
        {
            "type": "territory_transfer",
            "region_id": 999,
            "new_owner_country_id": "CAN",
        }
    ]
    state.current_actions = [
        ActionSubmitPeaceDeal("USA", "war-1", "USA", offered_clauses=invalid)
    ]
    system.update(state, 0.0)
    assert state.get_table("peace_deals").is_empty()

    state.current_actions = [
        ActionSubmitPeaceDeal("USA", "war-1", "USA", offered_clauses=_clauses())
    ]
    system.update(state, 0.0)
    deal_id = state.get_table("peace_deals").item(0, "id")
    before = state.get_table("countries").select("id", "money_reserves")
    state.current_actions = [ActionRespondPeaceDeal("USA", deal_id, "CAN", True)]
    system.update(state, 0.0)

    assert state.get_table("peace_deals").item(0, "status") == "pending"
    assert state.get_table("countries").select("id", "money_reserves").equals(before)
    assert state.get_table("debt_contracts").is_empty()
    assert json.loads(state.get_table("peace_deals").item(0, "offered_clauses_json")) == _clauses()


def test_ai_accepts_exhausting_white_peace_and_closes_the_war_in_the_same_tick():
    state = _state()
    state.globals["player_country_map"] = {"human-player": "USA"}
    state.update_table(
        "war_exhaustion_states",
        pl.DataFrame(
            {
                "id": ["war-exhaustion-war-1-CAN", "war-exhaustion-war-1-GBR"],
                "war_id": ["war-1", "war-1"],
                "country_id": ["CAN", "GBR"],
                "exhaustion_index": [100.0, 100.0],
            }
        ),
    )
    state.current_actions = [ActionSubmitPeaceDeal("AI_SYSTEM", "war-1", "USA")]

    AdvancedDiplomacySystem().update(state, 0.0)
    DiplomacySystem().update(state, 0.0)

    deal = state.get_table("peace_deals").row(0, named=True)
    assert deal["status"] == "accepted"
    assert deal["acceptance_utility"] >= 0.55
    assert state.get_table("countries_wars").is_empty()


def test_ai_rejects_an_economically_unsustainable_reparations_demand():
    state = _state()
    state.globals["player_country_map"] = {"human-player": "USA"}
    state.current_actions = [
        ActionSubmitPeaceDeal(
            "AI_SYSTEM",
            "war-1",
            "USA",
            requested_clauses=[
                {
                    "type": "war_reparations",
                    "payer_country_id": "CAN",
                    "recipient_country_id": "USA",
                    "amount": 10_000_000.0,
                    "duration_months": 12,
                }
            ],
        )
    ]

    AdvancedDiplomacySystem().update(state, 0.0)

    deal = state.get_table("peace_deals").row(0, named=True)
    assert deal["status"] == "rejected"
    assert "CAN rejected" in deal["reason"]
    assert state.get_table("debt_contracts").is_empty()
    assert state.get_table("countries_wars").height == 1


def test_opposing_ai_archetypes_score_identical_peace_terms_differently():
    state = _state()
    state.update_table(
        "countries",
        state.get_table("countries").with_columns(
            pl.when(pl.col("id") == "CAN")
            .then(pl.lit("conciliatory"))
            .otherwise(pl.lit("hawkish"))
            .alias("diplomatic_ai_archetype")
        ),
    )
    war = state.get_table("countries_wars").row(0, named=True)
    policy = PeaceDealPolicy()

    conciliatory_score = policy.evaluate_ai_acceptance(state, war, "CAN", [])
    hawkish_score = policy.evaluate_ai_acceptance(state, war, "GBR", [])

    assert math.isclose(conciliatory_score - hawkish_score, 0.24)


def test_active_alliance_obligation_reduces_acceptance_unless_suspended_or_expired():
    state = _state()
    policy = PeaceDealPolicy()
    war = state.get_table("countries_wars").row(0, named=True)
    baseline = policy.evaluate_ai_acceptance(state, war, "CAN", [])
    treaties = state.get_table("countries_treaties")
    alliance = treaties.row(0, named=True)
    alliance.update(
        id="defense-1",
        name="Mutual defense",
        type="alliance",
        members=["CAN", "GBR"],
        status="active",
        suspended_members=[],
        expires_at_minute=0,
    )

    state.update_table(
        "countries_treaties",
        pl.concat(
            [
                treaties,
                pl.DataFrame([alliance], schema=treaties.schema, strict=False),
            ]
        ),
    )
    active_score = policy.evaluate_ai_acceptance(state, war, "CAN", [])
    assert math.isclose(baseline - active_score, 0.08, abs_tol=1e-12)

    suspended = dict(alliance, suspended_members=["CAN"])
    state.update_table(
        "countries_treaties",
        state.get_table("countries_treaties").with_columns(
            pl.when(pl.col("id") == "defense-1")
            .then(pl.lit(suspended["suspended_members"]))
            .otherwise(pl.col("suspended_members"))
            .alias("suspended_members")
        ),
    )
    assert policy.evaluate_ai_acceptance(state, war, "CAN", []) == baseline

    state.time.total_minutes = 10
    state.update_table(
        "countries_treaties",
        state.get_table("countries_treaties").with_columns(
            pl.when(pl.col("id") == "defense-1")
            .then(pl.lit(10))
            .otherwise(pl.col("expires_at_minute"))
            .alias("expires_at_minute")
        ),
    )
    assert policy.evaluate_ai_acceptance(state, war, "CAN", []) == baseline


def test_multiple_ai_responders_can_accept_and_reject_the_same_proposal_in_one_tick():
    state = _state()
    state.globals["player_country_map"] = {"human-player": "USA"}
    state.update_table(
        "countries",
        state.get_table("countries").with_columns(
            pl.when(pl.col("id") == "CAN")
            .then(pl.lit("conciliatory"))
            .when(pl.col("id") == "GBR")
            .then(pl.lit("hawkish"))
            .otherwise(pl.lit("pragmatic"))
            .alias("diplomatic_ai_archetype")
        ),
    )
    state.current_actions = [ActionSubmitPeaceDeal("AI_SYSTEM", "war-1", "USA")]

    AdvancedDiplomacySystem().update(state, 0.0)

    deal = state.get_table("peace_deals").row(0, named=True)
    assert deal["status"] == "rejected"
    assert deal["accepted_responses"] == ["CAN"]
    assert deal["acceptance_utility"] < 0.55
    assert "GBR rejected" in deal["reason"]
    assert state.get_table("countries_wars").height == 1


def test_expired_peace_deal_cannot_be_accepted():
    state = _state()
    system = AdvancedDiplomacySystem()
    state.current_actions = [
        ActionSubmitPeaceDeal(
            "USA",
            "war-1",
            "USA",
            offered_clauses=_clauses(),
            expires_after_days=1,
        )
    ]
    system.update(state, 0.0)
    deal_id = state.get_table("peace_deals").item(0, "id")
    state.time.total_minutes = 1_441
    state.current_actions = [ActionRespondPeaceDeal("CAN", deal_id, "CAN", True)]
    system.update(state, 0.0)

    assert state.get_table("peace_deals").item(0, "status") == "expired"
    assert state.get_table("demilitarization_limits").is_empty()
    assert state.get_table("countries_wars").height == 1


def test_ratified_demilitarization_limit_disarms_excess_and_blocks_recruitment():
    state = _state()
    state.update_table(
        "units",
        pl.DataFrame(
            {
                "id": ["GBR-army-001"],
                "owner": ["GBR"],
                "strength": [200],
            }
        ),
    )
    state.current_actions = [
        ActionSubmitPeaceDeal(
            "USA",
            "war-1",
            "USA",
            offered_clauses=[
                {
                    "type": "demilitarization",
                    "country_id": "GBR",
                    "maximum_strength": 100,
                    "duration_days": 365,
                }
            ],
        )
    ]
    AdvancedDiplomacySystem().update(state, 0.0)
    deal_id = state.get_table("peace_deals").item(0, "id")
    state.globals["player_country_map"] = {"can-player": "CAN", "gbr-player": "GBR"}
    state.current_actions = [ActionRespondPeaceDeal("CAN", deal_id, "CAN", True)]
    AdvancedDiplomacySystem().update(state, 0.0)
    state.current_actions = [ActionRespondPeaceDeal("GBR", deal_id, "GBR", True)]
    AdvancedDiplomacySystem().update(state, 0.0)

    assert state.get_table("units").item(0, "strength") == 100
    assert state.get_table("countries").filter(pl.col("id") == "GBR").item(0, "military_count") == 100

    countries = state.get_table("countries").to_dicts()
    for row in countries:
        if row["id"] == "USA":
            row.update(military_count=4, money_reserves=1_000_000.0)
    state.update_table("countries", pl.DataFrame(countries, schema=state.get_table("countries").schema))
    state.update_table(
        "demilitarization_limits",
        pl.DataFrame(
            {
                "id": ["usa-limit"],
                "country_id": ["USA"],
                "maximum_strength": [5],
                "effective_at_minute": [0],
                "expires_at_minute": [10_000],
                "status": ["active"],
            }
        ),
    )
    state.update_table("units", pl.DataFrame(schema=state.get_table("units").schema))
    state.current_actions = [ActionBuildUnit("USA", "USA", "infantry", 2)]
    MilitarySystem().update(state, 0.0)

    usa_strength = state.get_table("units").filter(pl.col("owner") == "USA")["strength"].sum()
    assert usa_strength == 4
    assert state.get_table("countries").filter(pl.col("id") == "USA").item(0, "money_reserves") == 1_000_000.0
    assert state.get_table("unit_order_feedback").filter(
        pl.col("reason").str.contains("demilitarization")
    ).height == 1
