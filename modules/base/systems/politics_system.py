import polars as pl
import random
from src.engine.interfaces import ISystem
from src.server.state import GameState

class PoliticsSystem(ISystem):
    @property
    def id(self) -> str:
        return "base.politics"

    @property
    def dependencies(self) -> list[str]:
        return ["base.population"] # Politics might depend on pop happiness later

    def update(self, state: GameState, delta_time: float) -> None:
        tick = state.globals.get("tick", 0)
        
        # Run weekly
        if tick % 7 != 0:
            return

        countries = state.get_table("countries")
        
        # Logic: 
        # Expected Stability = (Approval * 0.7) + (HumanDev * 0.3) - Corruption
        # Current Stability moves towards Expected Stability by 1% per week.

        # Note: We use .fill_null(0) generously because map data is often incomplete during dev
        
        # 1. Calculate Target
        countries = countries.with_columns(
            (
                (pl.col("gvt_approval").fill_null(50) * 0.7) + 
                (pl.col("human_dev").fill_null(50) * 0.3) - 
                (pl.col("gvt_corruption").fill_null(0))
            ).clip(0, 100).alias("_target_stability")
        )

        # 2. Drift towards target
        # Formula: New = Old + (Target - Old) * 0.1
        countries = countries.with_columns(
            (
                pl.col("gvt_stability") + 
                ((pl.col("_target_stability") - pl.col("gvt_stability")) * 0.05)
            ).cast(pl.Int64).alias("gvt_stability")
        ).drop(["_target_stability"])

        state.update_table("countries", countries)