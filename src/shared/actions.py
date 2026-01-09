from dataclasses import dataclass
from typing import Optional

@dataclass
class GameAction:
    """
    Base class for all discrete game actions following the Command Pattern.
    
    Architecture Note:
        In this Data-Oriented architecture, Clients do not modify the GameState directly.
        Instead, they issue Actions. The Engine then processes these Actions deterministically.
        This approach simplifies networking (sending actions) and replays.
    """
    # Identifies who initiated the action ('local_player', 'server', or a specific player ID).
    player_id: str

# --- Map Actions ---

@dataclass
class ActionSetRegionOwner(GameAction):
    """
    Transfers ownership of a specific region to a new country.
    Used by the Editor (painting) and Gameplay (conquest/diplomacy).
    """
    region_id: int
    new_owner_tag: str

# --- Economy Actions ---

@dataclass
class ActionSetTax(GameAction):
    """
    Updates the tax rate for a specific country.
    """
    country_tag: str
    new_tax_rate: float

# --- Time & Control Actions ---

@dataclass
class ActionSetGameSpeed(GameAction):
    """
    Sets the target simulation speed.
    
    Speed Levels (Game Design):
    1: Very Slow (48s / day)
    2: Slow      (24s / day)
    3: Normal    (12s / day)
    4: Fast      (2.4s / day)
    5: Very Fast (0.6s / day)
    """
    speed_level: int

@dataclass
class ActionSetPaused(GameAction):
    """
    Pauses or resumes the simulation.
    Note: The Engine loop continues to run (for UI/Network), but the TimeSystem 
    will stop advancing the game date.
    """
    is_paused: bool