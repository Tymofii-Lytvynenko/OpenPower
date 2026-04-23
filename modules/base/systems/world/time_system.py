from datetime import timedelta
from typing import List, Dict

from src.engine.interfaces import ISystem
from src.server.state import GameState, GAME_EPOCH
from src.shared.actions import ActionSetGameSpeed, ActionSetPaused
from src.shared.events import EventNewDay, EventNewHour, EventRealSecond

class TimeSystem(ISystem):
    """
    Manages the flow of game time.
    Calculates date progression and fires temporal events.
    
    Responsibility:
    - Reads 'ActionSetGameSpeed' / 'ActionSetPaused'
    - Updates 'state.time' (Year, Month, Day)
    - Emits 'EventNewDay', 'EventNewHour', and 'EventRealSecond'
    """

    def __init__(self):
        # Optimization: Pre-calculated "Game Minutes per Real Second"
        # Formula: 1440 minutes (1 day) / X seconds
        # Level 1: 48.0s -> 30 min/s
        # Level 2: 24.0s -> 60 min/s
        # Level 3: 12.0s -> 120 min/s
        # Level 4:  2.4s -> 600 min/s
        # Level 5:  0.6s -> 2400 min/s
        self.minutes_per_sec: Dict[int, float] = {
            1: 30.0,
            2: 60.0,
            3: 120.0,
            4: 600.0,
            5: 2400.0
        }
        
        # Trackers for the Real Second Heartbeat
        self.real_sec_timer = 0.0
        self.last_event_total_minutes = 0

    @property
    def id(self) -> str:
        return "base.time"

    @property
    def dependencies(self) -> List[str]:
        # Time has no dependencies on other gameplay systems.
        return []

    def update(self, state: GameState, delta_time: float) -> None:
        t = state.time

        # 1. Handle Control Actions
        # We iterate through actions to see if speed was changed this tick
        for action in state.current_actions:
            if isinstance(action, ActionSetGameSpeed):
                # Clamp speed between 1 and 5
                t.speed_level = max(1, min(5, action.speed_level))
                state.globals["game_speed"] = t.speed_level
            
            elif isinstance(action, ActionSetPaused):
                t.is_paused = action.is_paused

        # 2. Real Second Heartbeat
        # We process this BEFORE the pause check so the heartbeat continues
        # even if the game is paused (useful for UI updates).
        self.real_sec_timer += delta_time
        
        if self.real_sec_timer >= 1.0:
            # Calculate how many in-game minutes passed since the last pulse
            # If paused, this will naturally be 0.
            minutes_passed = t.total_minutes - self.last_event_total_minutes
            game_seconds = minutes_passed * 60
            
            state.events.append(EventRealSecond(
                game_seconds_passed=float(game_seconds),
                is_paused=t.is_paused
            ))
            
            # Maintain phase and update tracker
            self.real_sec_timer -= 1.0
            self.last_event_total_minutes = t.total_minutes

        # 3. Check Pause State
        if t.is_paused:
            return

        # 4. Calculate Time Progression
        # Get the rate based on current speed level (default to Normal/Level 3 if invalid)
        rate = self.minutes_per_sec.get(t.speed_level, 120.0)
        
        # Accumulate fractional minutes
        t._accumulator += delta_time * rate
        
        # 5. Integer Step Logic
        # We only update the simulation if at least 1 in-game minute has passed.
        if t._accumulator >= 1.0:
            minutes_delta = int(t._accumulator)
            t.total_minutes += minutes_delta
            t._accumulator -= minutes_delta  # Keep the remainder
            
            # --- Temporal Update & Signaling ---
            
            # Snapshot previous values to detect changes
            prev_hour = t.hour
            prev_day = t.day
            
            # Recalculate human-readable fields using Python's robust datetime logic
            current_dt = GAME_EPOCH + timedelta(minutes=t.total_minutes)
            
            # Update optimized integers
            t.year = current_dt.year
            t.month = current_dt.month
            t.day = current_dt.day
            t.hour = current_dt.hour
            t.minute = current_dt.minute
            
            # Update UI string
            t.date_str = current_dt.strftime("%Y-%m-%d %H:%M")
            
            # 6. Emit Temporal Events
            if t.hour != prev_hour:
                state.events.append(EventNewHour(t.hour, t.total_minutes))
                
            if t.day != prev_day:
                state.events.append(EventNewDay(t.day, t.month, t.year))