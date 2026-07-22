import unittest
from src.shared.state import GameState
from modules.base.systems.world.time_system import TimeSystem
from src.shared.events import EventNewDay, EventRealSecond

class TestTimeSystem(unittest.TestCase):
    def test_time_progression(self):
        state = GameState()
        state.time.total_minutes = 0
        state.time.is_paused = False
        state.time.speed_level = 3  # 120 in-game minutes per real second

        system = TimeSystem()
        
        # Simulate 0.5 seconds passing -> 60 minutes of game time
        system.update(state, 0.5)
        self.assertEqual(state.time.total_minutes, 60)

    def test_events_emission(self):
        state = GameState()
        state.time.total_minutes = 0
        state.time.is_paused = False
        state.time.speed_level = 4  # 600 in-game minutes per real second
        
        system = TimeSystem()
        
        # Simulate 1.0 real second passing to trigger EventRealSecond
        system.update(state, 1.0)
        has_real_sec = any(isinstance(e, EventRealSecond) for e in state.events)
        self.assertTrue(has_real_sec)
        
        # Simulate another 1.5 real seconds to cross a 24-hour boundary (1440 mins)
        system.update(state, 1.5)
        has_new_day = any(isinstance(e, EventNewDay) for e in state.events)
        self.assertTrue(has_new_day)
