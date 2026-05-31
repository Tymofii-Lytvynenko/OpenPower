from dataclasses import dataclass


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
class EventMessageCreated(GameEvent):
    """
    Fired when a new inbox message is appended to the world state.
    """

    message_id: str
    country_tag: str
    category: str


@dataclass
class EventTreatyProposed(GameEvent):
    """
    Fired when a treaty proposal is queued for review.
    """

    treaty_id: str
    source_country_tag: str
    target_country_tag: str


@dataclass
class EventTreatyRefused(GameEvent):
    """
    Fired when a country rejects a treaty proposal.
    """

    treaty_id: str
    responder_country_tag: str


@dataclass
class EventWarStarted(GameEvent):
    """
    Fired when a new war entry becomes active.
    """

    war_id: str
    attacker_tag: str
    defender_tag: str


@dataclass
class EventBattleStarted(GameEvent):
    """
    Fired when combat begins in a region.
    """

    battle_id: str
    region_id: int


@dataclass
class EventBattleEnded(GameEvent):
    """
    Fired when an active battle resolves.
    """

    battle_id: str
    victor_tag: str


@dataclass
class EventProductionCompleted(GameEvent):
    """
    Fired when a production order finishes.
    """

    order_id: str
    country_tag: str


@dataclass
class EventResearchCompleted(GameEvent):
    """
    Fired when a research branch reaches completion.
    """

    track_id: str
    country_tag: str
    branch: str


@dataclass
class EventBudgetChanged(GameEvent):
    """
    Fired when a country's budget allocations are updated.
    """

    country_tag: str


@dataclass
class EventRandomEventTriggered(GameEvent):
    """
    Fired when a new random event (disaster, boom, etc.) activates in a region.
    Other systems can subscribe to apply gameplay effects (economy penalties,
    population loss, etc.) without coupling to RandomEventsSystem.
    """

    event_id: str
    event_type: str
    region_id: int
    severity: float  # 0.0–1.0 scale for future effect magnitude
