from __future__ import annotations

import json
import math

import polars as pl

from modules.base.schema import ensure_base_tables
from modules.base.systems.military.military_system import MilitarySystem
from modules.base.systems.world.advanced_diplomacy_system import AdvancedDiplomacySystem
from modules.base.systems.world.peace_deal_policy import PeaceDealPolicy
from modules.base.systems.world.treaty_diplomacy import DiplomacySystem
from src.shared.actions import (
    ActionBuildUnit,
    ActionOfferPeace,
    ActionRespondPeaceDeal,
    ActionSubmitPeaceDeal,
)
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
    response = state.journal.command_results[-1]
    assert response["action_type"] == "ActionRespondPeaceDeal"
    assert response["status"] == "applied"
    assert response["deal_id"] == deal_id
    assert response["country_id"] == "CAN"
    assert state.get_table("peace_deals").item(0, "status") == "pending"
    assert state.get_table("regions").filter(pl.col("id") == 2).item(0, "owner") == "USA"

    state.current_actions = [ActionRespondPeaceDeal("GBR", deal_id, "GBR", True)]
    system.update(state, 0.0)
    response = state.journal.command_results[-1]
    assert response["action_type"] == "ActionRespondPeaceDeal"
    assert response["status"] == "applied"
    assert response["deal_id"] == deal_id
    assert response["country_id"] == "GBR"

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
    rejection = state.journal.command_results[-1]
    assert rejection["action_type"] == "ActionSubmitPeaceDeal"
    assert rejection["status"] == "rejected"
    assert rejection["war_id"] == "war-1"
    assert rejection["country_id"] == "USA"
    assert "region" in rejection["reason"].lower()

    state.current_actions = [
        ActionSubmitPeaceDeal("USA", "war-1", "USA", offered_clauses=_clauses())
    ]
    system.update(state, 0.0)
    submission = state.journal.command_results[-1]
    assert submission["action_type"] == "ActionSubmitPeaceDeal"
    assert submission["status"] == "applied"
    assert submission["war_id"] == "war-1"
    assert submission["country_id"] == "USA"
    assert submission["deal_id"] == state.get_table("peace_deals").item(0, "id")
    deal_id = state.get_table("peace_deals").item(0, "id")
    before = state.get_table("countries").select("id", "money_reserves")
    state.current_actions = [ActionRespondPeaceDeal("USA", deal_id, "CAN", True)]
    system.update(state, 0.0)

    rejection = state.journal.command_results[-1]
    assert rejection["action_type"] == "ActionRespondPeaceDeal"
    assert rejection["status"] == "rejected"
    assert rejection["deal_id"] == deal_id
    assert rejection["country_id"] == "CAN"
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


def test_peace_clause_normalization_rejects_invalid_payload_shapes_and_values():
    policy = PeaceDealPolicy()
    normalized, error = policy.normalize_clauses(None)
    assert normalized == []
    assert "bounded list" in error
    normalized, error = policy.normalize_clauses([{}] * (policy.MAX_CLAUSES + 1))
    assert normalized == []
    assert "bounded list" in error
    assert "structured object" in policy.normalize_clauses([None])[1]
    assert "Unsupported peace clause type" in policy.normalize_clauses([{"type": "unknown"}])[1]
    assert "distinct payer and recipient" in policy.normalize_clauses(
        [{"type": "war-reparations", "payer_country_id": "USA", "recipient_country_id": "USA"}]
    )[1]
    assert "positive finite amount" in policy.normalize_clauses(
        [{"type": "war_reparations", "payer_country_id": "USA", "recipient_country_id": "CAN", "amount": 0}]
    )[1]
    assert "positive region id" in policy.normalize_clauses(
        [{"type": "territory_transfer", "region_id": 0, "new_owner_country_id": "CAN"}]
    )[1]
    assert "requires a treaty id" in policy.normalize_clauses([{"type": "treaty_annulment"}])[1]
    assert "non-negative force cap" in policy.normalize_clauses(
        [{"type": "demilitarization", "country_id": "CAN", "maximum_strength": -1, "duration_days": 0}]
    )[1]

    normalized, error = policy.normalize_clauses(
        [{"type": "territory-transfer", "region_id": "2", "new_owner_country_id": " can "}]
    )
    assert error == ""
    assert normalized == [{"type": "territory_transfer", "region_id": 2, "new_owner_country_id": "CAN"}]


def test_peace_clause_validation_rejects_invalid_participants_and_duplicate_targets():
    policy = PeaceDealPolicy()
    state = _state()
    war = state.get_table("countries_wars").row(0, named=True)
    reparations = {
        "type": "war_reparations",
        "payer_country_id": "CAN",
        "recipient_country_id": "USA",
        "amount": 100.0,
        "duration_months": 12,
    }
    assert "not a participant" in policy.validate_clauses(state, war, "MEX", [])
    assert policy.validate_clauses(state, war, "CAN", []) == ""

    missing_country = dict(reparations, payer_country_id="MEX")
    assert "two existing countries" in policy.validate_clauses(state, war, "USA", [missing_country])
    same_side = dict(reparations, recipient_country_id="GBR")
    assert "opposing war sides" in policy.validate_clauses(state, war, "USA", [same_side])

    missing_region = {"type": "territory_transfer", "region_id": 999, "new_owner_country_id": "CAN"}
    assert "existing region and recipient" in policy.validate_clauses(state, war, "USA", [missing_region])

    owner_state = _state()
    owner_state.update_table(
        "regions",
        owner_state.get_table("regions").with_columns(
            pl.when(pl.col("id") == 2).then(pl.lit("MEX")).otherwise(pl.col("owner")).alias("owner")
        ),
    )
    transfer = {"type": "territory_transfer", "region_id": 2, "new_owner_country_id": "CAN"}
    assert "not owned by a participant" in policy.validate_clauses(
        owner_state, war, "USA", [transfer]
    )

    controller_state = _state()
    controller_state.update_table(
        "regions",
        controller_state.get_table("regions").with_columns(
            pl.when(pl.col("id") == 2).then(pl.lit("MEX")).otherwise(pl.col("controller")).alias("controller")
        ),
    )
    assert "not controlled by a participant" in policy.validate_clauses(
        controller_state, war, "USA", [transfer]
    )

    outsider_state = _state()
    outsider_countries = pl.concat(
        [
            outsider_state.get_table("countries"),
            outsider_state.get_table("countries").head(1).with_columns(pl.lit("MEX").alias("id")),
        ],
        how="vertical_relaxed",
    )
    outsider_state.update_table("countries", outsider_countries)
    same_owner = {"type": "territory_transfer", "region_id": 1, "new_owner_country_id": "USA"}
    assert "different war participant" in policy.validate_clauses(
        outsider_state, war, "USA", [same_owner]
    )

    inactive_state = _state()
    inactive_state.update_table(
        "countries_treaties",
        inactive_state.get_table("countries_treaties").with_columns(pl.lit("expired").alias("status")),
    )
    annulment = {"type": "treaty_annulment", "treaty_id": "trade-1"}
    assert "Only an active treaty" in policy.validate_clauses(inactive_state, war, "USA", [annulment])

    same_side_treaty = _state()
    treaty_rows = same_side_treaty.get_table("countries_treaties").to_dicts()
    treaty_rows[0]["members"] = ["CAN", "GBR"]
    same_side_treaty.update_table("countries_treaties", pl.DataFrame(treaty_rows))
    assert "does not bind both opposing war sides" in policy.validate_clauses(
        same_side_treaty, war, "USA", [annulment]
    )

    invalid_demilitarization = {
        "type": "demilitarization",
        "country_id": "MEX",
        "maximum_strength": 100,
        "duration_days": 30,
    }
    assert "participating in the war" in policy.validate_clauses(
        state, war, "USA", [invalid_demilitarization]
    )
    assert "conflicting duplicate clauses" in policy.validate_clauses(
        state, war, "USA", [annulment, annulment]
    )


def test_ai_acceptance_scores_reparations_territory_demilitarization_and_annulment():
    state = _state()
    war = state.get_table("countries_wars").row(0, named=True)
    policy = PeaceDealPolicy()

    payer = policy.evaluate_ai_acceptance(
        state,
        war,
        "CAN",
        [{"type": "war_reparations", "payer_country_id": "CAN", "recipient_country_id": "USA", "amount": 5_000.0}],
    )
    recipient = policy.evaluate_ai_acceptance(
        state,
        war,
        "USA",
        [{"type": "war_reparations", "payer_country_id": "CAN", "recipient_country_id": "USA", "amount": 1_200.0}],
    )
    assert 0.0 <= payer <= 1.0
    assert recipient > policy.evaluate_ai_acceptance(state, war, "USA", [])

    territory_gain = policy.evaluate_ai_acceptance(
        state,
        war,
        "CAN",
        [{"type": "territory_transfer", "region_id": 2, "new_owner_country_id": "CAN"}],
    )
    territory_loss = policy.evaluate_ai_acceptance(
        state,
        war,
        "USA",
        [{"type": "territory_transfer", "region_id": 1, "new_owner_country_id": "CAN"}],
    )
    disarmament = policy.evaluate_ai_acceptance(
        state,
        war,
        "CAN",
        [{"type": "demilitarization", "country_id": "CAN", "maximum_strength": 100}],
    )
    assert territory_gain > policy.evaluate_ai_acceptance(state, war, "CAN", [])
    assert territory_loss < policy.evaluate_ai_acceptance(state, war, "USA", [])
    assert disarmament < policy.evaluate_ai_acceptance(state, war, "CAN", [])

    annulment = [{"type": "treaty_annulment", "treaty_id": "trade-1"}]
    partnership_score = policy.evaluate_ai_acceptance(state, war, "CAN", annulment)
    state.update_table(
        "countries_treaties",
        state.get_table("countries_treaties").with_columns(pl.lit("alliance").alias("type")),
    )
    alliance_score = policy.evaluate_ai_acceptance(state, war, "CAN", annulment)
    assert partnership_score > alliance_score


def test_peace_policy_parsers_return_safe_fallbacks():
    policy = PeaceDealPolicy()
    assert policy._country_tags("usa, CAN") == {"USA", "CAN"}
    assert policy._country_tags(["usa", " CAN "]) == {"USA", "CAN"}
    assert policy._country_tags(None) == set()
    assert policy._finite("invalid", 7.0) == 7.0
    assert policy._finite(float("inf"), 7.0) == 7.0
    assert policy._integer("invalid", 9) == 9
    assert policy._integer(1.5, 9) == 9
    assert policy._integer(float("inf"), 9) == 9


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


def test_submit_rejects_inactive_unauthorized_duplicate_and_malformed_packages() -> None:
    system = AdvancedDiplomacySystem()

    inactive = _state()
    inactive.update_table(
        "countries_wars",
        inactive.get_table("countries_wars").with_columns(pl.lit("ended").alias("status")),
    )
    deals = system._submit(
        inactive,
        ActionSubmitPeaceDeal("USA", "war-1", "USA"),
        system._deals(None),
    )
    assert deals.is_empty()
    assert inactive.journal.command_results[-1]["status"] == "rejected"

    unauthorized = _state()
    system._submit(
        unauthorized,
        ActionSubmitPeaceDeal("USA", "war-1", "CAN"),
        system._deals(None),
    )
    assert "war leader" in unauthorized.journal.command_results[-1]["reason"]

    state = _state()
    action = ActionSubmitPeaceDeal("USA", "war-1", "USA")
    pending = system._submit(state, action, system._deals(None))
    system._submit(state, action, pending)
    assert "already awaiting" in state.journal.command_results[-1]["reason"]
    closed = pending.with_columns(pl.lit("rejected").alias("status"))
    system._submit(state, action, closed)
    assert "already been submitted" in state.journal.command_results[-1]["reason"]

    invalid_offered = _state()
    system._submit(
        invalid_offered,
        ActionSubmitPeaceDeal("USA", "war-1", "USA", offered_clauses=[None]),
        system._deals(None),
    )
    assert "structured object" in invalid_offered.journal.command_results[-1]["reason"]

    invalid_requested = _state()
    system._submit(
        invalid_requested,
        ActionSubmitPeaceDeal("USA", "war-1", "USA", requested_clauses=[None]),
        system._deals(None),
    )
    assert "structured object" in invalid_requested.journal.command_results[-1]["reason"]

    clause = {
        "type": "war_reparations",
        "payer_country_id": "CAN",
        "recipient_country_id": "USA",
        "amount": 100.0,
        "duration_months": 12,
    }
    too_many = _state()
    system._submit(
        too_many,
        ActionSubmitPeaceDeal(
            "USA",
            "war-1",
            "USA",
            offered_clauses=[clause] * system._policy.MAX_CLAUSES,
            requested_clauses=[clause],
        ),
        system._deals(None),
    )
    assert "more than" in too_many.journal.command_results[-1]["reason"]

    for deadline in ("invalid", 0, 366):
        state = _state()
        system._submit(
            state,
            ActionSubmitPeaceDeal("USA", "war-1", "USA", expires_after_days=deadline),
            system._deals(None),
        )
        assert state.journal.command_results[-1]["status"] == "rejected"

    no_opposition = _state()
    no_opposition.update_table(
        "countries_wars",
        no_opposition.get_table("countries_wars").with_columns(
            pl.lit([], dtype=pl.List(pl.Utf8)).alias("side_b")
        ),
    )
    system._submit(
        no_opposition,
        ActionSubmitPeaceDeal("USA", "war-1", "USA"),
        system._deals(None),
    )
    assert "no participants" in no_opposition.journal.command_results[-1]["reason"]


def test_respond_rejects_missing_deals_ended_wars_and_changed_clauses() -> None:
    system = AdvancedDiplomacySystem()

    missing = _state()
    system._respond(
        missing,
        ActionRespondPeaceDeal("CAN", "missing", "CAN", True),
        system._deals(None),
    )
    assert "no longer awaiting" in missing.journal.command_results[-1]["reason"]

    duplicate = _state()
    pending = system._submit(
        duplicate,
        ActionSubmitPeaceDeal("USA", "war-1", "USA"),
        system._deals(None),
    )
    deal_id = pending.item(0, "id")
    pending = system._respond(
        duplicate, ActionRespondPeaceDeal("CAN", deal_id, "CAN", True), pending
    )
    system._respond(
        duplicate, ActionRespondPeaceDeal("CAN", deal_id, "CAN", True), pending
    )
    assert "another response" in duplicate.journal.command_results[-1]["reason"]

    rejected = _state()
    pending = system._submit(
        rejected,
        ActionSubmitPeaceDeal("USA", "war-1", "USA"),
        system._deals(None),
    )
    deal_id = pending.item(0, "id")
    result = system._respond(
        rejected, ActionRespondPeaceDeal("CAN", deal_id, "CAN", False), pending
    )
    assert result.item(0, "status") == "rejected"

    ended = _state()
    pending = system._submit(
        ended,
        ActionSubmitPeaceDeal("USA", "war-1", "USA"),
        system._deals(None),
    )
    deal_id = pending.item(0, "id")
    ended.update_table(
        "countries_wars",
        ended.get_table("countries_wars").with_columns(pl.lit("ended").alias("status")),
    )
    pending = system._respond(
        ended, ActionRespondPeaceDeal("CAN", deal_id, "CAN", True), pending
    )
    result = system._respond(
        ended, ActionRespondPeaceDeal("GBR", deal_id, "GBR", True), pending
    )
    assert result.item(0, "status") == "rejected"
    assert "no longer active" in ended.journal.command_results[-1]["reason"]

    changed = _state()
    clause = {
        "type": "territory_transfer",
        "region_id": 2,
        "new_owner_country_id": "CAN",
    }
    pending = system._submit(
        changed,
        ActionSubmitPeaceDeal("USA", "war-1", "USA", offered_clauses=[clause]),
        system._deals(None),
    )
    deal_id = pending.item(0, "id")
    changed.update_table(
        "regions",
        changed.get_table("regions").with_columns(
            pl.when(pl.col("id") == 2)
            .then(pl.lit("MEX"))
            .otherwise(pl.col("owner"))
            .alias("owner"),
            pl.when(pl.col("id") == 2)
            .then(pl.lit("MEX"))
            .otherwise(pl.col("controller"))
            .alias("controller"),
        ),
    )
    pending = system._respond(
        changed, ActionRespondPeaceDeal("CAN", deal_id, "CAN", True), pending
    )
    result = system._respond(
        changed, ActionRespondPeaceDeal("GBR", deal_id, "GBR", True), pending
    )
    assert result.item(0, "status") == "rejected"
    assert "not owned by a participant" in changed.journal.command_results[-1]["reason"]


def test_background_resolution_and_private_helpers_cover_expiry_and_defaults() -> None:
    system = AdvancedDiplomacySystem()
    state = _state()
    pending = system._submit(
        state,
        ActionSubmitPeaceDeal("USA", "war-1", "USA"),
        system._deals(None),
    ).with_columns(pl.lit(0).alias("expires_at_minute"))
    expired = system._expire_pending(state, pending)
    assert expired.item(0, "status") == "expired"
    assert any(isinstance(event, EventPeaceDealResolved) for event in state.events)

    missing_war = pending.with_columns(pl.lit("missing-war").alias("war_id"))
    assert system._evaluate_ai_responses(state, missing_war).equals(missing_war)

    state.globals["ai_controlled_countries"] = ["CAN"]
    assert system._is_ai_country(state, "CAN")
    assert not system._is_ai_country(state, "GBR")

    assert system._deals(None).is_empty()
    assert system._decode_clauses("not-json") == []
    assert system._tags("usa, CAN") == {"USA", "CAN"}
    assert system._tags(None) == set()

    no_wars = _state()
    no_wars.tables.pop("countries_wars")
    assert system._war(no_wars, "war-1") is None
    no_id = _state()
    no_id.update_table("countries_wars", pl.DataFrame({"status": ["active"]}))
    assert system._war(no_id, "war-1") is None


def test_demilitarization_clamps_deployments_and_legacy_ai_offer_is_translated() -> None:
    system = AdvancedDiplomacySystem()
    state = _state()
    state.update_table(
        "units",
        pl.DataFrame({"id": ["unit-1"], "owner": ["CAN"], "strength": [120]}),
    )
    state.update_table(
        "unit_deployment_orders",
        pl.DataFrame({"unit_id": ["unit-1"], "quantity": [150]}),
    )
    updates = system._apply_clauses(
        state,
        {"id": "deal-1"},
        [
            {
                "type": "demilitarization",
                "country_id": "CAN",
                "maximum_strength": 500,
                "duration_days": 30,
            }
        ],
    )
    assert updates["units"].item(0, "strength") == 120
    assert updates["unit_deployment_orders"].item(0, "quantity") == 120

    state = _state()
    pending = system._submit(
        state,
        ActionSubmitPeaceDeal("USA", "war-1", "USA"),
        system._deals(None),
    )
    state.update_table("peace_deals", pending)
    state.current_actions = [ActionOfferPeace("AI_SYSTEM", "war-1", "USA", "peace")]
    system.update(state, 0.0)
    assert state.get_table("peace_deals").item(0, "status") == "pending"
    assert "already awaiting" in state.journal.command_results[-1]["reason"]


def test_system_metadata_and_idle_tick_are_stable() -> None:
    system = AdvancedDiplomacySystem()
    assert system.id == "base.advanced_diplomacy"
    assert system.dependencies == ["base.time", "base.bootstrap"]

    state = _state()
    system.update(state, 0.0)
    assert state.get_table("peace_deals").is_empty()
    assert state.journal.command_results == []
