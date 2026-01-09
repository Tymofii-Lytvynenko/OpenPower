import polars as pl
from dataclasses import dataclass, field
from typing import Dict, Any, List, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from src.shared.actions import GameAction
    from src.shared.events import GameEvent

# The starting point for the simulation time (Epoch).
# We use this to calculate the date from 'total_minutes'.
GAME_EPOCH = datetime(2001, 1, 1, 0, 0)

@dataclass
class TimeData:
    """
    A highly optimized data component for time tracking.
    
    Why separate this from 'globals'?
    1. Performance: Attribute access (.hour) is faster than dict lookup (['hour']).
    2. Type Safety: Provides strict typing for IDEs and static analysis.
    3. Caching: We store pre-calculated integers (year, month, day) so other 
       systems don't have to perform expensive datetime math every tick.
    """
    # Source of Truth: Total minutes elapsed since GAME_EPOCH.
    # We use an integer because floating point time eventually loses precision.
    total_minutes: int = 0
    
    # Cached Human-Readable fields (Updated only when total_minutes changes)
    year: int = 2001
    month: int = 1
    day: int = 1
    hour: int = 0
    minute: int = 0
    
    # Formatted String (e.g., "2001-01-01 14:30") for UI rendering.
    date_str: str = "2001-01-01 00:00"

    # Simulation State
    speed_level: int = 1
    is_paused: bool = False
    
    # Internal accumulator for fractional time updates.
    # (Not intended for use by other systems).
    _accumulator: float = 0.0

@dataclass
class GameState:
    """
    The central data store for the entire simulation.
    Strictly adheres to Data-Oriented Design.
    """
    
    # Stores the primary game data (DataFrames).
    # Keys are table names (e.g., 'regions', 'countries').
    tables: Dict[str, pl.DataFrame] = field(default_factory=dict)
    
    # Dedicated component for Time state.
    time: TimeData = field(default_factory=TimeData)
    
    # Holds other global simulation variables that don't fit into tables.
    globals: Dict[str, Any] = field(default_factory=lambda: {
        "tick": 0,
        "game_speed": 1.0 # Legacy/Visual speed multiplier if needed
    })

    # The Event Bus.
    # Systems append events here during their update.
    # The Engine clears this list at the start of every tick.
    events: List['GameEvent'] = field(default_factory=list)

    # Actions received this specific tick.
    # The Engine populates this before systems update.
    current_actions: List['GameAction'] = field(default_factory=list)

    def get_table(self, name: str) -> pl.DataFrame:
        """
        Retrieves a reference to a simulation table.
        """
        if name not in self.tables:
            raise KeyError(f"Table '{name}' not found in GameState.")
        return self.tables[name]

    def update_table(self, name: str, df: pl.DataFrame):
        """
        Replaces a table in the state (Copy-on-Write).
        """
        self.tables[name] = df