import random
import polars as pl
from src.engine.interfaces import ISystem
from src.server.state import GameState
from src.shared.actions import ActionBuildUnit

class AISystem(ISystem):
    """
    Basic AI that performs actions for non-player countries.
    """
    def __init__(self):
        self._missing_columns = set()

    @property
    def id(self) -> str:
        return "base.ai"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time","base.economy", "base.military"]

    def update(self, state: GameState, delta_time: float) -> None:
        # Run AI logic infrequently (e.g., once every 30 ticks/month)
        tick = state.globals.get("tick", 0)
        if tick % 30 != 0:
            return

        countries = state.get_table("countries")
        
        # Ensure money_reserves exists
        if "money_reserves" not in countries.columns:
            if "money_reserves" not in self._missing_columns:
                print(f"[{self.id}] Column 'money_reserves' not found in 'countries'. Defaulting to 0.")
                self._missing_columns.add("money_reserves")
            countries = countries.with_columns(pl.lit(0.0).alias("money_reserves"))

        # Filter: Only AI countries (assuming we have a 'is_player' flag or check external map)
        # For MVP, let's assume any country with > 1B money is rich enough to build armies
        
        rich_countries = countries.filter(pl.col("money_reserves") > 1_000_000_000)
        
        for row in rich_countries.iter_rows(named=True):
            tag = row['id']
            
            # Simple Logic: 50% chance to build a unit if rich
            if random.random() > 0.5:
                # Issue Action
                # Note: The AI pushes actions to the NEXT tick's queue usually.
                # However, since we are INSIDE the update loop, we can't easily append to current_actions.
                # In a robust engine, we'd have an 'output_actions' queue.
                # For this MVP, we will modify the state directly or use a workaround.
                
                # Correct way for MVP: AI actions are processed in the NEXT tick via the Session, 
                # OR we execute the logic directly here if we want instant AI.
                
                # Let's simulate the AI ordering a build by directly firing the action intent 
                # into the 'events' or just printing for now, as modifying state directly is safer here.
                pass