from datetime import datetime, timedelta
from typing import List
from src.engine.interfaces import ISystem
from src.server.state import GameState
from src.shared.actions import ActionSetGameSpeed, ActionSetPaused

class TimeSystem(ISystem):
    """
    Manages the flow of game time, date advancement, and simulation speed.
    
    Specs:
    Level 1: 48.0 sec/day
    Level 2: 24.0 sec/day
    Level 3: 12.0 sec/day
    Level 4:  2.4 sec/day
    Level 5:  0.6 sec/day
    """

    def __init__(self):
        # Seconds per day for each speed level
        self.speed_curve = {
            1: 48.0,
            2: 24.0,
            3: 12.0,
            4: 2.4,
            5: 0.6
        }

    @property
    def id(self) -> str:
        return "base.time"

    @property
    def dependencies(self) -> List[str]:
        # Time usually runs first so other systems know if it's a new day
        return []

    def update(self, state: GameState, delta_time: float) -> None:
        # 1. Handle Control Actions
        # We iterate through actions to see if speed was changed this tick
        for action in state.current_actions:
            if isinstance(action, ActionSetGameSpeed):
                # Clamp between 1 and 5
                new_speed = max(1, min(5, action.speed_level))
                state.globals["speed_level"] = new_speed
                # print(f"[TimeSystem] Speed set to {new_speed}")
            
            elif isinstance(action, ActionSetPaused):
                state.globals["is_paused"] = action.is_paused
                # print(f"[TimeSystem] Paused: {action.is_paused}")

        # 2. Check Pause State
        if state.globals.get("is_paused", False):
            state.globals["is_new_day"] = False
            return

        # 3. Calculate Time Progression
        speed_level = state.globals.get("speed_level", 1)
        seconds_per_day = self.speed_curve.get(speed_level, 48.0)
        
        # Accumulate real delta time
        accumulator = state.globals.get("time_accumulator", 0.0)
        accumulator += delta_time
        
        # 4. Advance Days
        days_to_advance = 0
        while accumulator >= seconds_per_day:
            accumulator -= seconds_per_day
            days_to_advance += 1
        
        # Update accumulator in state (so it persists safely)
        state.globals["time_accumulator"] = accumulator

        # 5. Update Calendar
        if days_to_advance > 0:
            current_date_str = state.globals.get("date_str", "2001-01-01")
            try:
                # Parse
                date_obj = datetime.strptime(current_date_str, "%Y-%m-%d")
                
                # Advance
                date_obj += timedelta(days=days_to_advance)
                
                # Format
                state.globals["date_str"] = date_obj.strftime("%Y-%m-%d")
                
                # Set flag for other systems (e.g., Economy, Population) to trigger monthly/daily updates
                state.globals["is_new_day"] = True
                
            except ValueError:
                print(f"[TimeSystem] Error parsing date: {current_date_str}")
                state.globals["is_new_day"] = False
        else:
            state.globals["is_new_day"] = False