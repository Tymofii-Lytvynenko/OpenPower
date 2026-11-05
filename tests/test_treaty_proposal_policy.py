import polars as pl

from modules.base.systems.world.treaty_diplomacy import DiplomacySystem
from modules.base.systems.world.treaty_proposal_policy import (
    country_diplomacy_restriction,
    treaty_title_restriction,
)
from modules.base.schema import ensure_base_tables
from src.shared.actions import ActionCreateTreaty, ActionRespondTreaty
from src.shared.events import EventTreatyLifecycleChanged, EventTreatyRefused
from src.shared.state import GameState


def test_restrictions_use_actual_government_and_names():
    governments = pl.DataFrame([
        {"country_id": "UKR", "government_type": "Anarchy"},
        {"country_id": "POL", "government_type": "Republic"},
    ])
    assert country_diplomacy_restriction(governments, "ukr")
    assert not country_diplomacy_restriction(governments, "POL")
    assert not country_diplomacy_restriction(None, "UKR")
    assert treaty_title_restriction(" Existing ", pl.DataFrame({"name": ["Existing"]}), None)
    assert treaty_title_restriction("Reserved", None, pl.DataFrame({"title": ["Reserved"]}))
    assert not treaty_title_restriction("New name", pl.DataFrame({"name": ["Existing"]}), None)


def make_state():
    state = GameState(tables={"countries": pl.DataFrame({"id": ["UKR", "POL", "DEU"]})})
    ensure_base_tables(state)
    return state


def proposal(title="Compact", target="POL"):
    return ActionCreateTreaty(
        player_id="player", source_country_tag="UKR", target_country_tag=target,
        treaty_type="alliance", title=title, terms="",
    )


def test_direct_client_cannot_sponsor_during_anarchy():
    state = make_state()
    state.tables["country_governments"] = pl.DataFrame({
        "country_id": ["UKR"], "government_type": ["Anarchy"],
    })
    state.current_actions = [proposal()]
    DiplomacySystem().update(state, 0.1)
    assert state.tables["pending_treaties"].is_empty()
    assert state.journal.command_results[-1]["status"] == "rejected"
    assert not state.events


def test_names_are_reserved_between_actions_in_the_same_tick():
    state = make_state()
    state.current_actions = [proposal(), proposal(target="DEU")]
    DiplomacySystem().update(state, 0.1)
    assert state.tables["pending_treaties"].height == 1
    assert state.journal.command_results[-1]["status"] == "rejected"
    state.current_actions = [proposal("Other compact", "DEU")]
    DiplomacySystem().update(state, 0.1)
    assert state.tables["pending_treaties"].height == 2


def test_activation_preserves_exact_proposal_context_for_client_callbacks():
    state = make_state()
    system = DiplomacySystem()
    state.current_actions = [proposal()]
    system.update(state, 0.1)
    proposal_id = state.tables["pending_treaties"]["id"][0]
    state.current_actions = [ActionRespondTreaty("player", proposal_id, "POL", True)]
    system.update(state, 0.1)
    event = next(event for event in state.events if isinstance(event, EventTreatyLifecycleChanged))
    assert event.proposal_id == proposal_id
    assert event.treaty_id != proposal_id
    state.journal.append_domain_event(event, event_id="activation", tick=1, source=system.id)
    from src.shared.snapshots import StateSnapshotEncoder, StateSnapshotDecoder

    restored = StateSnapshotDecoder().decode(StateSnapshotEncoder().encode(state))
    assert restored.journal.domain_events[-1]["payload"]["proposal_id"] == proposal_id


def test_refusal_retains_context_after_the_proposal_has_been_deleted():
    state = make_state()
    system = DiplomacySystem()
    state.current_actions = [proposal()]
    system.update(state, 0.1)
    proposal_id = state.tables["pending_treaties"]["id"][0]
    state.current_actions = [ActionRespondTreaty("player", proposal_id, "POL", False)]
    system.update(state, 0.1)
    event = next(event for event in state.events if isinstance(event, EventTreatyRefused))
    assert state.tables["pending_treaties"].is_empty()
    assert (event.source_country_tag, event.title, event.accepted_country_tags) == ("UKR", "Compact", ("UKR",))
    state.journal.append_domain_event(event, event_id="refusal", tick=1, source=system.id)
    from src.shared.snapshots import StateSnapshotEncoder, StateSnapshotDecoder

    restored = StateSnapshotDecoder().decode(StateSnapshotEncoder().encode(state))
    assert restored.journal.domain_events[-1]["payload"]["source_country_tag"] == "UKR"
