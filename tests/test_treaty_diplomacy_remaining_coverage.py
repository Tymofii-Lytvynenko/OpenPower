import polars as pl

from modules.base.systems.world.treaty_diplomacy import (
    DiplomacySystem,
    MESSAGE_SCHEMA,
    NEWS_SCHEMA,
    RELATIONS_SCHEMA,
    WAR_SCHEMA,
)
from src.shared.actions import (
    ActionCreateTreaty,
    ActionJoinTreaty,
    ActionRespondTreaty,
    ActionUpdateTreatyParticipants,
)
from src.shared.state import GameState
from src.shared.treaties import (
    ANNEXATION_CLAIM_SCHEMA,
    PENDING_TREATY_SCHEMA,
    TREATY_SCHEMA,
)


def _frame(schema, rows=()):
    return pl.DataFrame(list(rows), schema=schema, strict=False) if rows else pl.DataFrame(schema=schema)


def _state():
    return GameState(
        tables={"countries": pl.DataFrame({"id": ["USA", "CAN", "MEX"]})},
        globals={"player_country_map": {"sponsor": "USA"}},
    )


def _treaty(treaty_type):
    return _frame(TREATY_SCHEMA, [{
        "id": "pact",
        "name": "Pact",
        "type": treaty_type,
        "members": ["USA", "CAN"],
        "side_a": ["USA"],
        "side_b": ["CAN"],
        "status": "active",
        "source_country_id": "USA",
        "target_country_id": "CAN",
    }])


def test_create_proposal_rejects_invalid_sides_members_and_duplicates():
    system = DiplomacySystem()
    state = _state()
    treaties = pl.DataFrame(schema=TREATY_SCHEMA)
    pending = pl.DataFrame(schema=PENDING_TREATY_SCHEMA)
    messages = pl.DataFrame(schema=MESSAGE_SCHEMA)
    news = pl.DataFrame(schema=NEWS_SCHEMA)

    overlapping = ActionCreateTreaty(
        player_id="USA",
        source_country_tag="USA",
        target_country_tag="CAN",
        treaty_type="mobility_agreement",
        title="Mobility",
        terms="",
        side_a_country_tags=["USA"],
        side_b_country_tags=["USA"],
    )
    unchanged, _, _ = system._create_proposal(
        state, overlapping, treaties, pending, messages, news
    )
    assert unchanged.is_empty()

    source_is_added = ActionCreateTreaty(
        player_id="USA",
        source_country_tag="USA",
        target_country_tag="CAN",
        treaty_type="alliance",
        title="Alliance",
        terms="",
        member_country_tags=["CAN"],
    )
    created, _, _ = system._create_proposal(
        state, source_is_added, treaties, pending, messages, news
    )
    assert created.row(0, named=True)["members"] == ["CAN", "USA"]

    oversized_bilateral = ActionCreateTreaty(
        player_id="USA",
        source_country_tag="USA",
        target_country_tag="MEX",
        treaty_type="request_war_declaration",
        title="War request",
        terms="",
        side_a_country_tags=["USA", "CAN"],
        side_b_country_tags=["MEX"],
    )
    rejected, _, _ = system._create_proposal(
        state, oversized_bilateral, treaties, pending, messages, news
    )
    assert rejected.is_empty()

    unknown_member = ActionCreateTreaty(
        player_id="USA",
        source_country_tag="USA",
        target_country_tag="MISSING",
        treaty_type="alliance",
        title="Unknown member",
        terms="",
        member_country_tags=["USA", "MISSING"],
    )
    rejected, _, _ = system._create_proposal(
        state, unknown_member, treaties, pending, messages, news
    )
    assert rejected.is_empty()

    active_treaty = _treaty("alliance")
    duplicate = ActionCreateTreaty(
        player_id="USA",
        source_country_tag="USA",
        target_country_tag="CAN",
        treaty_type="alliance",
        title="Duplicate",
        terms="",
        member_country_tags=["USA", "CAN"],
    )
    rejected, _, _ = system._create_proposal(
        state, duplicate, active_treaty, pending, messages, news
    )
    assert rejected.is_empty()


def test_response_and_join_ignore_missing_or_unsupported_records():
    system = DiplomacySystem()
    state = _state()
    treaties = pl.DataFrame(schema=TREATY_SCHEMA)
    pending = pl.DataFrame(schema=PENDING_TREATY_SCHEMA)
    wars = pl.DataFrame(schema=WAR_SCHEMA)
    relations = pl.DataFrame(schema=RELATIONS_SCHEMA)
    messages = pl.DataFrame(schema=MESSAGE_SCHEMA)
    news = pl.DataFrame(schema=NEWS_SCHEMA)
    claims = pl.DataFrame(schema=ANNEXATION_CLAIM_SCHEMA)

    missing = ActionRespondTreaty(
        player_id="CAN", treaty_id="missing", responder_country_tag="CAN", accept=True
    )
    _, unchanged, *_ = system._respond_to_proposal(
        state, missing, treaties, pending, wars, relations, messages, news, claims
    )
    assert unchanged.is_empty()

    unsupported = _frame(PENDING_TREATY_SCHEMA, [{
        "id": "legacy",
        "source_country_id": "USA",
        "target_country_id": "CAN",
        "treaty_type": "unsupported_treaty",
        "title": "Legacy proposal",
        "side_a": ["USA"],
        "side_b": ["CAN"],
        "members": ["USA", "CAN"],
        "required_responses": ["CAN"],
        "accepted_members": ["USA"],
        "status": "pending",
    }])
    response = ActionRespondTreaty(
        player_id="CAN", treaty_id="legacy", responder_country_tag="CAN", accept=True
    )
    unchanged_treaties, remaining, *_ = system._respond_to_proposal(
        state, response, treaties, unsupported, wars, relations, messages, news, claims
    )
    assert unchanged_treaties.is_empty()
    assert remaining.is_empty()

    unchanged, unchanged_messages = system._join_open_treaty(
        state,
        ActionJoinTreaty(player_id="CAN", treaty_id="missing", country_tag=""),
        treaties,
        messages,
    )
    assert unchanged.is_empty()
    assert unchanged_messages.is_empty()


def test_participant_updates_reject_inconsistent_sides_and_unknown_members():
    system = DiplomacySystem()
    state = _state()
    messages = pl.DataFrame(schema=MESSAGE_SCHEMA)

    invalid_updates = [
        ("mobility_agreement", ["USA"], ["USA"]),
        ("mobility_agreement", ["CAN"], ["MEX"]),
        ("alliance", ["USA", "CAN"], ["MEX"]),
        ("alliance", ["USA", "MISSING"], []),
    ]
    for treaty_type, side_a, side_b in invalid_updates:
        original = _treaty(treaty_type)
        action = ActionUpdateTreatyParticipants(
            player_id="sponsor",
            treaty_id="pact",
            side_a_country_tags=side_a,
            side_b_country_tags=side_b,
        )
        updated, unchanged_messages = system._update_treaty_participants(
            state, action, original, messages
        )
        assert updated.equals(original)
        assert unchanged_messages.is_empty()


def test_diplomacy_update_applies_due_annexation_to_the_world_state():
    state = GameState(
        tables={
            "regions": pl.DataFrame([{
                "id": 2,
                "owner": "CAN",
                "controller": "USA",
            }]),
            "annexation_claims": _frame(ANNEXATION_CLAIM_SCHEMA, [{
                "id": "claim",
                "treaty_id": "pact",
                "region_id": 2,
                "annexing_country_id": "USA",
                "political_owner_id": "CAN",
                "controller_at_start": "USA",
                "due_at_minute": 0,
                "status": "pending",
            }]),
        }
    )

    DiplomacySystem().update(state, 0.0)

    assert state.get_table("regions").item(0, "owner") == "USA"
    assert state.get_table("annexation_claims").item(0, "status") == "annexed"
