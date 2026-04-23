import polars as pl
from src.engine.interfaces import ISystem
from src.server.state import GameState
from src.shared.actions import ActionAnnexRegion, ActionOccupyRegion, ActionSetRegionOwner

class TerritorySystem(ISystem):
    def __init__(self):
        self._missing_columns = set()

    @property
    def id(self) -> str:
        return "base.territory"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time"]

    def update(self, state: GameState, delta_time: float) -> None:
        # Handle Instant Territory Changes
        # In a real game, this might take time or require a peace treaty
        
        relevant_actions = [
            a for a in state.current_actions 
            if isinstance(a, (ActionAnnexRegion, ActionSetRegionOwner, ActionOccupyRegion))
        ]
        
        if not relevant_actions:
            return

        regions = state.get_table("regions")
        
        # Ensure controller column exists
        if "controller" not in regions.columns:
            if "controller" not in self._missing_columns:
                print(f"[{self.id}] Column 'controller' not found in 'regions'. Defaulting to values from 'owner'.")
                self._missing_columns.add("controller")
            regions = regions.with_columns(pl.col("owner").alias("controller"))

        for action in relevant_actions:
            if isinstance(action, (ActionAnnexRegion, ActionSetRegionOwner)):
                # Change Owner AND Controller
                regions = regions.with_columns(
                    pl.when(pl.col("id") == action.region_id)
                    .then(pl.lit(action.new_owner_tag))
                    .otherwise(pl.col("owner"))
                    .alias("owner")
                )
                regions = regions.with_columns(
                    pl.when(pl.col("id") == action.region_id)
                    .then(pl.lit(action.new_owner_tag))
                    .otherwise(pl.col("controller"))
                    .alias("controller")
                )
                
            elif isinstance(action, ActionOccupyRegion):
                # Change Controller Only
                regions = regions.with_columns(
                    pl.when(pl.col("id") == action.region_id)
                    .then(pl.lit(action.new_controller_tag))
                    .otherwise(pl.col("controller"))
                    .alias("controller")
                )

        state.update_table("regions", regions)