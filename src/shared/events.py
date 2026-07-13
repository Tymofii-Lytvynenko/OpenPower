from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class GameEvent:
    """
    Base class for all internal simulation events.

    Architecture Note:
        Events are distinct from Actions.
        - Actions: External commands FROM the user/network TO the engine.
        - Events: Internal signals FROM one system TO another.

        Using an Event Bus allows systems to be decoupled. For example, the
        AudioSystem can listen for 'EventNewDay' to play a sound without
        knowing anything about the TimeSystem.
    """

    pass


@dataclass
class DomainGameEvent(GameEvent):
    """Marker for gameplay facts that belong in the persistent journal."""

    pass


@dataclass
class JournalState:
    """Persistent append-only records used for debugging, replay, and UI delivery."""

    domain_events: list[dict[str, Any]] = field(default_factory=list)
    command_results: list[dict[str, Any]] = field(default_factory=list)

    def append_domain_event(
        self,
        event: DomainGameEvent,
        *,
        event_id: str,
        tick: int,
        source: str,
    ) -> dict[str, Any]:
        record = {
            "event_id": event_id,
            "tick": int(tick),
            "source": source,
            "event_type": type(event).__name__,
            "payload": asdict(event),
        }
        self.domain_events.append(record)
        return record

    def append_command_result(self, record: dict[str, Any]) -> None:
        self.command_results.append(dict(record))


@dataclass
class EventNewDay(GameEvent):
    """
    Fired once when the date changes (at 00:00).
    Used by Economy (taxes), Population (growth), and Politics systems.
    """

    day: int
    month: int
    year: int


@dataclass
class EventNewHour(GameEvent):
    """
    Fired every in-game hour.
    Used for granular updates like day/night cycle lighting or military movement steps.
    """

    hour: int
    total_minutes: int


@dataclass
class EventRealSecond(GameEvent):
    """
    Fired once per real-world second (approx 1Hz).
    Used for pacing economy/resource ticks to avoid CPU spikes
    while maintaining smooth progression.
    """

    game_seconds_passed: float  # How much in-game time happened in this real second?
    is_paused: bool


@dataclass
class EventMessageCreated(DomainGameEvent):
    """
    Fired when a new inbox message is appended to the world state.
    """

    message_id: str
    country_tag: str
    category: str


@dataclass
class EventTreatyProposed(DomainGameEvent):
    """
    Fired when a treaty proposal is queued for review.
    """

    treaty_id: str
    source_country_tag: str
    target_country_tag: str


@dataclass
class EventTreatyRefused(DomainGameEvent):
    """
    Fired when a country rejects a treaty proposal.
    """

    treaty_id: str
    responder_country_tag: str


@dataclass
class EventWarStarted(DomainGameEvent):
    """
    Fired when a new war entry becomes active.
    """

    war_id: str
    attacker_tag: str
    defender_tag: str


@dataclass
class EventBattleStarted(DomainGameEvent):
    """
    Fired when combat begins in a region.
    """

    battle_id: str
    region_id: int


@dataclass
class EventBattleEnded(DomainGameEvent):
    """
    Fired when an active battle resolves.
    """

    battle_id: str
    victor_tag: str


@dataclass
class EventProductionCompleted(DomainGameEvent):
    """
    Fired when a production order finishes.
    """

    order_id: str
    country_tag: str


@dataclass
class EventResearchCompleted(DomainGameEvent):
    """
    Fired when a research branch reaches completion.
    """

    track_id: str
    country_tag: str
    branch: str


@dataclass
class EventBudgetChanged(DomainGameEvent):
    """
    Fired when a country's budget allocations are updated.
    """

    country_tag: str


@dataclass
class EventRandomEventTriggered(DomainGameEvent):
    """
    Fired when a new random event (disaster, boom, etc.) activates in a region.
    Other systems can subscribe to apply gameplay effects (economy penalties,
    population loss, etc.) without coupling to RandomEventsSystem.
    """

    event_id: str
    event_type: str
    region_id: int
    severity: float  # 0.0–1.0 scale for future effect magnitude


@dataclass
class EventSystemError(DomainGameEvent):
    """
    Fired when a simulation system encounters a runtime error.
    Used for centralized error tracking and telemetry in the client.
    """
    system_id: str
    error_message: str
    traceback_text: str
