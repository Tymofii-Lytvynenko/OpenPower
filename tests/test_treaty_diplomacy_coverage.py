import json

import polars as pl
import pytest

from modules.base.systems.world.treaty_diplomacy import (
    DiplomacySystem,
    MESSAGE_SCHEMA,
    NEWS_SCHEMA,
    RELATIONS_SCHEMA,
    TreatyGeography,
    WAR_SCHEMA,
)
from src.shared.actions import (
    ActionExpelTreatyMember,
    ActionJoinWar,
    ActionLeaveTreaty,
    ActionUpdateTreatyParticipants,
)
from src.shared.events import EventNewDay
from src.shared.state import GameState
from src.shared.treaties import ANNEXATION_CLAIM_SCHEMA, TREATY_SCHEMA


def _typed_frame(schema, rows=()):
    return pl.DataFrame(list(rows), schema=schema, strict=False) if rows else pl.DataFrame(schema=schema)


def test_debt_assumption_splits_recipient_debt_by_gdp_and_skips_ineligible_rows():
    system = DiplomacySystem()
    state = GameState(tables={"countries": pl.DataFrame([
        {"id": "USA", "gdp": 300.0, "money_reserves": 100.0},
        {"id": "CAN", "gdp": 100.0, "money_reserves": 75.0},
        {"id": "MEX", "gdp": 50.0, "money_reserves": -100.0},
        {"id": "BRA", "gdp": 25.0, "money_reserves": 40.0},
    ])})

    system._assume_foreign_debt(state, {"USA", "CAN", "MISSING"}, {"MEX", "BRA", "MISSING"})

    balances = {row["id"]: row["money_reserves"] for row in state.get_table("countries").to_dicts()}
    assert balances == {"USA": 25.0, "CAN": 50.0, "MEX": 0.0, "BRA": 40.0}
    system._assume_foreign_debt(GameState(), {"USA"}, {"CAN"})


def test_treaty_effect_projection_and_noble_cause_relations_cover_special_policies():
    system = DiplomacySystem()

    assert system._effect_rows({"id": "x", "type": "unknown"}, (), {}) == []
    aid = system._effect_rows({
        "id": "aid", "type": "economic_aid", "side_a": ["USA"], "side_b": ["CAN"],
    }, ("USA", "CAN"), {})
    assert [(row["country_id"], row["effect"], row["value"]) for row in aid] == [
        ("USA", "economic_aid_contributor", 0.01),
        ("CAN", "economic_aid_recipient", 0.1),
    ]
    embargo = system._effect_rows({
        "id": "embargo", "type": "economic_embargo", "side_a": ["USA"], "side_b": ["CAN"],
    }, ("USA", "CAN"), {})
    assert [(row["country_id"], row["effect"]) for row in embargo] == [
        ("USA", "resource_trade_embargo"), ("CAN", "resource_trade_embargo"),
    ]

    deltas = system._daily_relation_deltas(
        "noble_cause", ["USA", "CAN"], ["USA", "CAN", "MEX"],
        {"USA": {"gdp": 100}, "CAN": {"gdp": 50}, "MEX": {"gdp": 50}},
    )
    assert deltas[("USA", "CAN")] == deltas[("CAN", "USA")] == 0.03
    assert deltas[("USA", "MEX")] == deltas[("MEX", "USA")] == -0.005

    countries = [
        {"id": "USA", "human_dev": 0.4},
        {"id": "CAN", "human_dev": 0.8},
        {"id": "MEX", "human_dev": 0.9},
    ]
    system._apply_human_development_convergence(countries, {"USA", "CAN"})
    assert countries[0]["human_dev"] == pytest.approx(0.432)
    assert countries[1]["human_dev"] == 0.8
    assert countries[2]["human_dev"] == 0.9
    assert system._apply_human_development_convergence(countries, set()) is countries


def test_expelling_treaty_members_checks_authority_and_removes_or_updates_treaty():
    system = DiplomacySystem()
    messages = pl.DataFrame(schema=MESSAGE_SCHEMA)

    def treaty_frame(members):
        return _typed_frame(TREATY_SCHEMA, [{
            "id": "pact", "name": "Pact", "type": "alliance", "status": "active",
            "source_country_id": "USA", "members": members,
        }])

    state = GameState(globals={"player_country_map": {"sponsor": "USA"}})
    original = treaty_frame(["USA", "CAN", "MEX"])
    unauthorized, unchanged_messages = system._expel_treaty_member(
        state,
        ActionExpelTreatyMember(player_id="outsider", treaty_id="pact", country_tag="CAN"),
        original,
        messages,
    )
    assert unauthorized.equals(original)
    assert unchanged_messages.is_empty()

    updated, messages = system._expel_treaty_member(
        state,
        ActionExpelTreatyMember(player_id="sponsor", treaty_id="pact", country_tag="CAN"),
        original,
        messages,
    )
    assert updated.to_dicts()[0]["members"] == ["MEX", "USA"]
    assert messages.to_dicts()[0]["country_id"] == "CAN"

    removed, _ = system._expel_treaty_member(
        state,
        ActionExpelTreatyMember(player_id="sponsor", treaty_id="pact", country_tag="CAN"),
        treaty_frame(["USA", "CAN"]),
        pl.DataFrame(schema=MESSAGE_SCHEMA),
    )
    assert removed.is_empty()
    missing, _ = system._expel_treaty_member(
        state,
        ActionExpelTreatyMember(player_id="sponsor", treaty_id="absent", country_tag="CAN"),
        original,
        messages,
    )
    assert missing.equals(original)

    integrated_state = GameState(
        tables={"countries_treaties": original},
        globals={"player_country_map": {"sponsor": "USA"}},
    )
    integrated_state.current_actions = [ActionExpelTreatyMember(
        player_id="sponsor", treaty_id="pact", country_tag="CAN",
    )]
    system.update(integrated_state, 0.1)
    assert integrated_state.get_table("countries_treaties").to_dicts()[0]["members"] == ["MEX", "USA"]


def test_treaty_eligibility_and_annexation_guards_return_expected_outcomes(monkeypatch):
    system = DiplomacySystem()
    state = GameState(tables={
        "countries": pl.DataFrame([
            {"id": "USA", "military_count": 100, "gdp": 100.0, "budget_research_ratio": 1.0},
            {"id": "CAN", "military_count": 10, "gdp": 100.0, "budget_research_ratio": 0.01},
        ]),
        "countries_wars": pl.DataFrame({
            "side_a": [["CAN"]], "side_b": [["USA"]], "status": ["active"],
        }),
    })
    assert not system._eligible_for_treaty(state, {"conditions_json": {}}, "MEX", ["USA"])
    assert not system._eligible_for_treaty(state, {"conditions_json": {}}, "CAN", ["MEX"])
    assert not system._eligible_for_treaty(
        state, {"conditions_json": {"max_military_strength_ratio": 2.0}}, "CAN", ["USA"],
    )
    assert not system._eligible_for_treaty(
        state, {"conditions_json": {"max_research_ratio": 2.0}}, "CAN", ["USA"],
    )
    monkeypatch.setattr(TreatyGeography, "within_limit", lambda *_args: False)
    assert not system._eligible_for_treaty(
        state, {"conditions_json": {"maximum_geographic_distance_km": 100.0}}, "CAN", ["USA"],
    )
    similar = GameState(tables={"countries": pl.DataFrame([
        {"id": "USA", "military_count": 10, "gdp": 100.0, "budget_research_ratio": 0.1},
        {"id": "CAN", "military_count": 10, "gdp": 100.0, "budget_research_ratio": 0.1},
    ]), "countries_wars": state.tables["countries_wars"]})
    assert not system._eligible_for_treaty(similar, {"conditions_json": {}}, "CAN", ["USA"])

    annexation_state = GameState(tables={
        "regions": pl.DataFrame([{
            "id": 2, "owner": "CAN", "controller": "USA", "latitude": 1.0, "longitude": 2.0,
        }]),
    })
    expired = _typed_frame(ANNEXATION_CLAIM_SCHEMA, [{
        "id": "old", "region_id": 2, "status": "void", "annexing_country_id": "USA",
        "political_owner_id": "CAN", "due_at_minute": 0,
    }])
    claims, updated_regions = system._resolve_annexation_claims(annexation_state, expired)
    assert claims.to_dicts()[0]["status"] == "void"
    assert updated_regions is None

    pending = _typed_frame(ANNEXATION_CLAIM_SCHEMA, [{
        "id": "claim", "region_id": 2, "status": "pending", "annexing_country_id": "USA",
        "political_owner_id": "CAN", "due_at_minute": 0,
    }])
    claims, updated_regions = system._resolve_annexation_claims(annexation_state, pending)
    assert claims.to_dicts()[0]["status"] == "annexed"
    assert updated_regions.to_dicts()[0]["owner"] == "USA"

    invalid_region = _typed_frame(ANNEXATION_CLAIM_SCHEMA, [{
        "id": "missing-region",
        "region_id": 99,
        "status": "pending",
        "annexing_country_id": "USA",
        "political_owner_id": "CAN",
        "due_at_minute": 0,
    }])
    claims, updated_regions = system._resolve_annexation_claims(annexation_state, invalid_region)
    assert claims.to_dicts()[0]["status"] == "void"
    assert updated_regions is None

    empty_claims = pl.DataFrame(schema=ANNEXATION_CLAIM_SCHEMA)
    assert system._schedule_annexation(GameState(), empty_claims, "pact", {"USA"}, {"CAN"}) is empty_claims
    assert system._remove_foreign_units(GameState(), {"USA"}, {"CAN"}) is None
    assert system._release_regions(GameState(), {"USA"}, {"CAN"}) is None
    assert system._country_row(GameState(), "MEX") == {}


def test_diplomacy_noop_and_government_lookup_defaults():
    system = DiplomacySystem()
    state = GameState()
    system.update(state, 0.1)
    assert state.tables == {}

    state = GameState(tables={"country_governments": pl.DataFrame([
        {"country_id": "CAN", "government_type": "parliamentary"},
        {"country_id": "USA", "government_type": "republic"},
    ])})
    assert system._government_type(state, "USA") == "republic"
    assert system._government_type(state, "MEX") == ""


def test_eligibility_and_sponsor_participant_updates_normalize_member_sets():
    system = DiplomacySystem()
    state = GameState(
        tables={"countries": pl.DataFrame({"id": ["USA", "CAN", "MEX", ""]})},
        globals={"player_country_map": {"sponsor": "USA"}},
    )
    treaty = {
        "id": "pact", "type": "alliance", "members": [],
        "side_a": ["USA", "CAN"], "side_b": [], "conditions_json": {},
    }
    assert system.eligible_treaty_countries(state, treaty) == {"USA", "CAN", "MEX"}
    assert system.ineligible_treaty_members(state, treaty) == frozenset()
    assert system.ineligible_treaty_members(state, {
        **treaty, "members": [], "side_a": ["USA"], "side_b": ["MEX"],
    }) == frozenset()

    original = _typed_frame(TREATY_SCHEMA, [{
        "id": "pact", "name": "Pact", "type": "alliance", "status": "active",
        "source_country_id": "USA", "members": ["USA", "CAN"], "side_a": ["USA", "CAN"],
    }])
    action = ActionUpdateTreatyParticipants(
        player_id="sponsor", treaty_id="pact", side_a_country_tags=["USA", "MEX"],
    )
    updated, messages = system._update_treaty_participants(
        state, action, original, pl.DataFrame(schema=MESSAGE_SCHEMA),
    )
    row = updated.to_dicts()[0]
    assert row["members"] == ["MEX", "USA"]
    assert row["side_a"] == ["MEX", "USA"]
    assert [message["country_id"] for message in messages.to_dicts()] == ["MEX", "CAN"]

    unchanged, _ = system._update_treaty_participants(
        state, action, updated, messages,
    )
    assert unchanged.equals(updated)
    missing, _ = system._update_treaty_participants(
        state, ActionUpdateTreatyParticipants(
            player_id="sponsor", treaty_id="missing", side_a_country_tags=["USA", "MEX"],
        ), original, messages,
    )
    assert missing.equals(original)


def test_leaving_a_multi_member_treaty_updates_members_and_emits_records():
    system = DiplomacySystem()
    treaties = _typed_frame(TREATY_SCHEMA, [{
        "id": "pact", "name": "Pact", "type": "alliance", "status": "active",
        "members": ["USA", "CAN", "MEX"], "side_a": ["USA", "CAN", "MEX"],
    }])
    relations = pl.DataFrame(schema=RELATIONS_SCHEMA)
    messages = pl.DataFrame(schema=MESSAGE_SCHEMA)
    news = pl.DataFrame(schema=NEWS_SCHEMA)

    unchanged, _, _, _ = system._leave_treaty(
        GameState(), ActionLeaveTreaty(player_id="USA", treaty_id="missing", country_tag="CAN"),
        treaties, relations, messages, news,
    )
    assert unchanged.equals(treaties)
    unchanged, _, _, _ = system._leave_treaty(
        GameState(), ActionLeaveTreaty(player_id="USA", treaty_id="pact", country_tag="BRA"),
        treaties, relations, messages, news,
    )
    assert unchanged.equals(treaties)

    updated, _, messages, news = system._leave_treaty(
        GameState(), ActionLeaveTreaty(player_id="CAN", treaty_id="pact", country_tag="CAN"),
        treaties, relations, messages, news,
    )
    row = updated.to_dicts()[0]
    assert row["members"] == ["MEX", "USA"]
    assert row["side_a"] == ["MEX", "USA"]
    assert messages.to_dicts()[0]["country_id"] == "CAN"
    assert news.to_dicts()[0]["related_country_id"] == "CAN"


def test_monthly_long_term_effects_converge_member_development():
    system = DiplomacySystem()
    state = GameState(
        tables={"countries": pl.DataFrame([
            {"id": "USA", "gdp": 100.0, "human_dev": 0.4, "money_reserves": 10.0},
            {"id": "CAN", "gdp": 100.0, "human_dev": 0.8, "money_reserves": 10.0},
        ])},
        events=[EventNewDay(day=1, month=1, year=2001)],
    )
    treaties = _typed_frame(TREATY_SCHEMA, [{
        "id": "development", "type": "human_development_collaboration", "status": "active",
        "members": ["USA", "CAN"],
    }])

    updated_treaties, _, effects = system._apply_long_term_effects(
        state, treaties, pl.DataFrame(schema=RELATIONS_SCHEMA),
    )

    countries = {row["id"]: row for row in state.get_table("countries").to_dicts()}
    assert countries["USA"]["human_dev"] == pytest.approx(0.432)
    assert countries["CAN"]["human_dev"] == 0.8
    assert updated_treaties.to_dicts()[0]["maintenance_cost"] > 0
    assert effects.is_empty()


def test_noble_cause_daily_effects_accumulate_relation_deltas():
    system = DiplomacySystem()
    state = GameState(
        tables={
            "countries": pl.DataFrame([
                {"id": "USA", "gdp": 100.0, "money_reserves": 100.0},
                {"id": "CAN", "gdp": 50.0, "money_reserves": 100.0},
                {"id": "MEX", "gdp": 50.0, "money_reserves": 100.0},
            ]),
            "countries_relations": pl.DataFrame(schema=RELATIONS_SCHEMA),
        },
        events=[EventNewDay(day=2, month=1, year=2001)],
    )
    treaties = _typed_frame(TREATY_SCHEMA, [{
        "id": "cause",
        "type": "noble_cause",
        "status": "active",
        "members": ["USA", "CAN"],
    }])

    _, relations, _ = system._apply_long_term_effects(
        state,
        treaties,
        pl.DataFrame(schema=RELATIONS_SCHEMA),
    )

    assert relations.height > 0


def test_punctual_war_declaration_delegates_to_war_start(monkeypatch):
    system = DiplomacySystem()
    state = GameState()
    treaties = pl.DataFrame(schema=TREATY_SCHEMA)
    wars = pl.DataFrame(schema=WAR_SCHEMA)
    relations = pl.DataFrame(schema=RELATIONS_SCHEMA)
    messages = pl.DataFrame(schema=MESSAGE_SCHEMA)
    news = pl.DataFrame(schema=NEWS_SCHEMA)
    claims = pl.DataFrame(schema=ANNEXATION_CLAIM_SCHEMA)
    calls = []

    def start_war(*args, **kwargs):
        calls.append(kwargs)
        return wars, relations, messages, news

    monkeypatch.setattr(system, "_start_war", start_war)
    result = system._apply_punctual_effect(
        state,
        {
            "id": "war-request",
            "type": "request_war_declaration",
            "side_a": ["USA"],
            "side_b": ["CAN"],
            "terms": "Defensive pact",
        },
        treaties,
        wars,
        relations,
        messages,
        news,
        claims,
    )

    assert calls[0]["source"] == "USA"
    assert calls[0]["target"] == "CAN"
    assert result[1:5] == (wars, relations, messages, news)


def test_treaty_eligibility_rejects_peer_below_minimum_relation():
    system = DiplomacySystem()
    state = GameState(tables={
        "countries": pl.DataFrame([{"id": "CAN"}, {"id": "USA"}]),
        "countries_relations": pl.DataFrame(schema=RELATIONS_SCHEMA),
    })

    assert not system._eligible_for_treaty(
        state,
        {"conditions_json": {"minimum_relation": 25}},
        "CAN",
        ["USA"],
    )


def test_annexation_claim_with_controller_mismatch_is_void(monkeypatch):
    system = DiplomacySystem()
    monkeypatch.setattr(
        "modules.base.systems.world.treaty_diplomacy.AnnexationPolicy.invalidated_claim_regions",
        lambda *_args: set(),
    )
    state = GameState(tables={"regions": pl.DataFrame([{
        "id": 2,
        "owner": "CAN",
        "controller": "CAN",
    }])})
    claims = _typed_frame(ANNEXATION_CLAIM_SCHEMA, [{
        "id": "pending-claim",
        "region_id": 2,
        "status": "pending",
        "annexing_country_id": "USA",
        "political_owner_id": "CAN",
        "due_at_minute": 0,
    }])

    updated_claims, updated_regions = system._resolve_annexation_claims(state, claims)

    assert updated_claims.to_dicts()[0]["status"] == "void"
    assert updated_regions is None


def test_allied_expansion_skips_other_active_treaty_types():
    system = DiplomacySystem()
    treaties = _typed_frame(TREATY_SCHEMA, [{
        "id": "trade",
        "type": "economic_partnership",
        "status": "active",
        "members": ["USA", "CAN"],
    }])

    assert system._expand_allies(treaties, "USA") == {"USA"}


def test_punctual_diplomacy_effects_release_control_and_schedule_claims_once():
    system = DiplomacySystem()
    region_state = GameState(tables={"regions": pl.DataFrame([
        {"id": 1, "owner": "CAN", "controller": "USA"},
    ])})
    wars = pl.DataFrame(schema=WAR_SCHEMA)
    relations = pl.DataFrame(schema=RELATIONS_SCHEMA)
    messages = pl.DataFrame(schema=MESSAGE_SCHEMA)
    news = pl.DataFrame(schema=NEWS_SCHEMA)
    claims = pl.DataFrame(schema=ANNEXATION_CLAIM_SCHEMA)
    result = system._apply_punctual_effect(
        region_state, {"id": "free", "type": "free_region", "side_a": ["USA"], "side_b": ["CAN"]},
        pl.DataFrame(schema=TREATY_SCHEMA), wars, relations, messages, news, claims,
    )
    assert region_state.get_table("regions").to_dicts()[0]["controller"] == "CAN"
    assert result[-1].equals(claims)

    debt_state = GameState(tables={"countries": pl.DataFrame([
        {"id": "USA", "gdp": 10.0, "money_reserves": 50.0},
        {"id": "CAN", "gdp": 10.0, "money_reserves": -20.0},
    ])})
    system._apply_punctual_effect(
        debt_state,
        {"id": "debt", "type": "assume_foreign_debt", "side_a": ["USA"], "side_b": ["CAN"]},
        pl.DataFrame(schema=TREATY_SCHEMA), wars, relations, messages, news, claims,
    )
    debt_balances = {row["id"]: row["money_reserves"] for row in debt_state.get_table("countries").to_dicts()}
    assert debt_balances == {"USA": 30.0, "CAN": 0.0}

    region_state.update_table("regions", pl.DataFrame([
        {"id": 2, "owner": "CAN", "controller": "USA"},
    ]))
    existing_claim = _typed_frame(ANNEXATION_CLAIM_SCHEMA, [{
        "id": "claim-pact-2", "treaty_id": "pact", "region_id": 2,
        "annexing_country_id": "USA", "political_owner_id": "CAN", "status": "pending",
    }])
    scheduled = system._schedule_annexation(region_state, existing_claim, "pact", {"USA"}, {"CAN"})
    assert scheduled.height == 1

    unit_state = GameState(tables={
        "regions": pl.DataFrame([
            {"id": 1, "owner": "USA", "controller": "USA", "latitude": 0.0, "longitude": 0.0},
            {"id": 2, "owner": "CAN", "controller": "CAN", "latitude": 1.0, "longitude": 1.0},
        ]),
        "units": pl.DataFrame([
            {"id": "foreign", "owner": "CAN", "current_region_id": 1, "latitude": 5.0, "longitude": 5.0},
            {"id": "no-home", "owner": "MEX", "current_region_id": 1, "latitude": 6.0, "longitude": 6.0},
            {"id": "local", "owner": "USA", "current_region_id": 1, "latitude": 0.0, "longitude": 0.0},
        ]),
    })
    system._remove_foreign_units(unit_state, {"USA"}, {"CAN", "MEX"})
    units = {row["id"]: row for row in unit_state.get_table("units").to_dicts()}
    assert units["foreign"]["current_region_id"] == 2
    assert units["no-home"]["current_region_id"] == 1
    assert units["local"]["current_region_id"] == 1
    assert system._release_regions(GameState(), {"USA"}, {"CAN"}) is None


def test_war_helpers_apply_coalition_pacts_and_handle_missing_join_targets():
    system = DiplomacySystem()
    pacts = pl.DataFrame([
        {"status": "ended", "mutual_defense": True, "primary_target_country_id": "USA", "member_country_ids": ["CAN"]},
        {"status": "active", "mutual_defense": False, "primary_target_country_id": "USA", "member_country_ids": ["CAN"]},
        {"status": "active", "mutual_defense": True, "primary_target_country_id": "USA", "member_country_ids": ["CAN", "MEX"]},
        {"status": "active", "mutual_defense": True, "primary_target_country_id": "CAN", "member_country_ids": ["USA", "MEX"]},
    ])
    state = GameState(tables={"coalition_pacts": pacts})
    empty_wars = pl.DataFrame(schema=WAR_SCHEMA)
    relations = pl.DataFrame(schema=RELATIONS_SCHEMA)
    messages = pl.DataFrame(schema=MESSAGE_SCHEMA)
    news = pl.DataFrame(schema=NEWS_SCHEMA)
    wars, relations, messages, news = system._start_war(
        state,
        source="USA",
        target="CAN",
        casus_belli="Defense pact",
        treaties=pl.DataFrame(schema=TREATY_SCHEMA),
        wars=empty_wars,
        relations=relations,
        messages=messages,
        news=news,
    )
    war = wars.to_dicts()[0]
    assert war["side_a"] == ["USA"]
    assert war["side_b"] == ["CAN", "MEX"]
    assert messages.height == 3 and news.height == 1

    missing_war = system._join_war(
        state, ActionJoinWar(player_id="MEX", war_id="missing", source_country_tag="MEX", side="attacker"),
        wars, relations, messages, news,
    )
    assert missing_war[0].equals(wars)
    one_sided_war = _typed_frame(WAR_SCHEMA, [{
        "id": "one-sided", "side_a": ["USA"], "side_b": [], "status": "active",
    }])
    unchanged = system._join_war(
        state, ActionJoinWar(player_id="MEX", war_id="one-sided", source_country_tag="MEX", side="attacker"),
        one_sided_war, relations, messages, news,
    )
    assert unchanged[0].equals(one_sided_war)


def test_relationship_helpers_cover_empty_inputs_and_suspension_policies():
    system = DiplomacySystem()
    relations = pl.DataFrame(schema=RELATIONS_SCHEMA)
    assert system._apply_daily_relations(
        relations, "cultural_exchanges", ["USA", "CAN"], ["USA", "CAN"], {},
    ).to_dicts() == [
        {"source": "CAN", "target": "USA", "value": 0.05},
        {"source": "USA", "target": "CAN", "value": 0.05},
    ]
    assert system._set_relation_pairs(relations, [("USA", "USA"), ("", "CAN")], 150) is relations
    assert system._frame_like(relations, []).schema == relations.schema
    assert system._owned_frame(pl.DataFrame({"id": [1]}), MESSAGE_SCHEMA).columns == list(MESSAGE_SCHEMA)
    empty_messages = pl.DataFrame(schema=MESSAGE_SCHEMA)
    assert system._append_messages(GameState(), empty_messages, []) is empty_messages

    treaties = _typed_frame(TREATY_SCHEMA, [
        {
            "id": "profile", "type": "alliance", "status": "active", "members": ["USA", "CAN"],
            "conditions_json": json.dumps({"minimum_relation": 0}),
        },
        {
            "id": "war_ok", "type": "alliance", "status": "active", "members": ["USA", "CAN"],
            "conditions_json": json.dumps({"allow_members_at_war": True}),
        },
    ])
    state = GameState(tables={
        "countries": pl.DataFrame({"id": ["USA", "CAN"]}),
        "countries_relations": pl.DataFrame({
            "source": ["USA", "CAN"], "target": ["CAN", "USA"], "value": [25.0, 25.0],
        }),
        "countries_wars": pl.DataFrame({
            "side_a": [["USA"]], "side_b": [["CAN"]], "status": ["active"],
        }),
    })
    refreshed = system._refresh_suspended_members(state, treaties, system._wars(state.tables["countries_wars"]))
    assert [row["suspended_members"] for row in refreshed.to_dicts()] == [["CAN", "USA"], []]
    assert system._war_pair_index(pl.DataFrame({
        "side_a": [["USA"]], "side_b": [["CAN"]], "status": ["ended"],
    })) == set()
    assert not system._countries_at_war(
        pl.DataFrame({"side_a": [["USA"]], "side_b": [["CAN"]], "status": ["ended"]}),
        "USA", "CAN",
    )
    assert system._has_matching_treaty(
        treaties, pl.DataFrame(schema=TREATY_SCHEMA), "alliance", {"USA", "CAN"},
    )
    assert not system._has_matching_treaty(
        pl.DataFrame(schema=TREATY_SCHEMA), pl.DataFrame(schema=TREATY_SCHEMA), "alliance", {"USA", "CAN"},
    )
    legacy = system._treaties(pl.DataFrame([{
        "id": "legacy", "source_country_id": "USA", "target_country_id": "CAN",
    }]))
    assert legacy.to_dicts()[0]["side_a"] == ["USA"]
    assert legacy.to_dicts()[0]["side_b"] == ["CAN"]
