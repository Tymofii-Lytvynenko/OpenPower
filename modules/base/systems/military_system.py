import polars as pl
from src.engine.interfaces import ISystem
from src.server.state import GameState
from src.shared.actions import ActionBuildUnit

class MilitarySystem(ISystem):
    def __init__(self):
        self._missing_columns = set()

    @property
    def id(self) -> str:
        return "base.military"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time","base.population", "base.economy"]

    def update(self, state: GameState, delta_time: float) -> None:
        # 1. Process Build Actions
        # We filter actions to find ActionBuildUnit
        actions_to_process = [a for a in state.current_actions if isinstance(a, ActionBuildUnit)]
        
        if actions_to_process:
            countries = state.get_table("countries")
            
            for action in actions_to_process:
                # Basic Logic: deduct money, add unit count
                # In a real game, this would be complex (manpower pools, equipment, training time)
                # For MVP: Instant build
                
                # 1. Check if country exists and has money (Mock cost 1M)
                COST = 1_000_000
                
                # We assume 'military_count' column exists. If not, we create/fill it.
                if "military_count" not in countries.columns:
                     if "military_count" not in self._missing_columns:
                         print(f"[{self.id}] Column 'military_count' not found in 'countries'. Defaulting to 0.")
                         self._missing_columns.add("military_count")
                     countries = countries.with_columns(pl.lit(0).alias("military_count"))
                
                if "money_reserves" not in countries.columns:
                     if "money_reserves" not in self._missing_columns:
                         print(f"[{self.id}] Column 'money_reserves' not found in 'countries'. Defaulting to 0.")
                         self._missing_columns.add("money_reserves")
                     countries = countries.with_columns(pl.lit(0.0).alias("money_reserves"))

                # Apply update
                countries = countries.with_columns(
                    pl.when(pl.col("id") == action.country_tag)
                    .then(pl.col("military_count") + action.count)
                    .otherwise(pl.col("military_count"))
                    .alias("military_count")
                )
                
                # Deduct Money
                countries = countries.with_columns(
                    pl.when(pl.col("id") == action.country_tag)
                    .then(pl.col("money_reserves") - (COST * action.count))
                    .otherwise(pl.col("money_reserves"))
                    .alias("money_reserves")
                )
            
            state.update_table("countries", countries)

        # 2. Update Manpower based on Population (Weekly)
        tick = state.globals.get("tick", 0)
        if tick % 7 == 0:
            self._update_manpower(state)

    def _update_manpower(self, state: GameState):
        # Manpower is usually a % of pop_15_64
        regions = state.get_table("regions")
        countries = state.get_table("countries")
        
        # Aggregate eligible population by owner
        # We group regions by 'owner' and sum 'pop_15_64'
        pop_stats = regions.group_by("owner").agg(pl.col("pop_15_64").sum().alias("total_core_manpower"))
        
        # Join into countries (This is a simplified approach)
        # In Polars, joins are fast.
        # We simply update the 'manpower_pool' column in countries based on the region sums * 0.10 (10% mobilization)
        
        # Note: Implementing the join back to 'countries' requires careful handling of column names 
        # to avoid duplication. For MVP, we'll skip the complex join and assume countries table has a 'manpower' column.
        pass