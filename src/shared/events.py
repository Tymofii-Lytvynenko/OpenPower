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