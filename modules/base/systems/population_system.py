import polars as pl
from src.engine.interfaces import ISystem
from src.server.state import GameState

class PopulationSystem(ISystem):
    @property
    def id(self) -> str:
        return "base.population"

    @property
    def dependencies(self) -> list[str]:
        return []

    def update(self, state: GameState, delta_time: float) -> None:
        # Run monthly (assuming 1 tick = 1 day, run every 30 ticks)
        tick = state.globals.get("tick", 0)
        if tick % 30 != 0:
            return

        regions = state.get_table("regions")
        
        # --- CONSTANTS ---
        # In a real game, these might come from a config table
        GROWTH_RATE = 0.001   # 0.1% monthly natural growth (births)
        AGING_RATE = 0.0005   # Rate at which people move to next bracket
        DEATH_RATE = 0.0008   # Elderly death rate

        # --- LOGIC ---
        # 1. Births add to pop_14
        # 2. Aging moves pop_14 -> pop_15_64
        # 3. Aging moves pop_15_64 -> pop_65
        # 4. Deaths remove from pop_65

        # We assume columns exist: 'pop_14', 'pop_15_64', 'pop_65'
        # If the TSV loaded them, they are there.

        upd = regions.with_columns([
            # Calculate flows
            (pl.col("pop_15_64") * GROWTH_RATE).alias("_births"),
            (pl.col("pop_14") * AGING_RATE).alias("_aging_kids"),
            (pl.col("pop_15_64") * AGING_RATE).alias("_aging_workers"),
            (pl.col("pop_65") * DEATH_RATE).alias("_deaths"),
        ])

        # Apply flows
        upd = upd.with_columns([
            (pl.col("pop_14") + pl.col("_births") - pl.col("_aging_kids")).cast(pl.Int64).alias("pop_14"),
            (pl.col("pop_15_64") + pl.col("_aging_kids") - pl.col("_aging_workers")).cast(pl.Int64).alias("pop_15_64"),
            (pl.col("pop_65") + pl.col("_aging_workers") - pl.col("_deaths")).cast(pl.Int64).alias("pop_65")
        ])

        # Drop temporary columns to keep state clean
        upd = upd.drop(["_births", "_aging_kids", "_aging_workers", "_deaths"])

        state.update_table("regions", upd)