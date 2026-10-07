from __future__ import annotations

from dataclasses import asdict

from src.shared.actions import (
    ActionChangePoliticalLaw,
    ActionResolvePoliticalCrisis,
    ActionSetElectionOverride,
    GameAction,
)
from src.shared.events import (
    DomainGameEvent,
    EventGovernmentFormChanged,
    EventPoliticalElectionResolved,
    EventPoliticalLawTransitionResolved,
)


def test_political_actions_are_serializable_intents_and_events_are_domain_facts() -> None:
    law_action = ActionChangePoliticalLaw("player-1", "AAA", "labor", "protected")
    override_action = ActionSetElectionOverride("player-1", "AAA", "postpone", 30)
    crisis_action = ActionResolvePoliticalCrisis("player-1", "AAA", "crisis-1", "negotiate")
    resolved = EventPoliticalLawTransitionResolved("AAA", "labor", "transition-1", "effective", "passed", 100)
    election = EventPoliticalElectionResolved("AAA", "election-1", "incumbent", 68.0, 120)
    regime = EventGovernmentFormChanged("AAA", "old", "new", "incumbent", 130, "constitutional vote")

    assert all(isinstance(action, GameAction) for action in (law_action, override_action, crisis_action))
    assert isinstance(resolved, DomainGameEvent)
    assert isinstance(election, DomainGameEvent)
    assert isinstance(regime, DomainGameEvent)
    assert asdict(law_action)["target_value"] == "protected"
    assert asdict(override_action)["duration_days"] == 30
    assert asdict(crisis_action)["decision"] == "negotiate"
