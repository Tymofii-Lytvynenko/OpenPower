import polars as pl
from src.server.state import GameState

def apply_region_ownership_change(state: GameState, region_id: int, new_owner_tag: str):
    """
    Updates the ownership of a specific region in the game state.
    
    Architecture Note:
        In Data-Oriented Design, we avoid object lookups (e.g., region_obj.owner = x).
        Instead, we perform a relational update on the 'regions' table.
        This approach scales massively: we could theoretically update ownership 
        for 1,000 regions in a single frame without lagging, thanks to Polars' SIMD optimizations.
    """
    regions_df = state.get_table("regions")

    # We use a conditional expression to create a new version of the 'owner' column.
    # Logic: If 'id' matches the target, use new_owner_tag; otherwise, keep the old value.
    #
    # TODO: For mass updates (e.g., 'Annex Country' or peace treaties), 
    # implementing a join-based update would be more efficient than single-row 'when/then'.
    updated_regions = regions_df.with_columns(
        pl.when(pl.col("id") == region_id)
        .then(pl.lit(new_owner_tag))
        .otherwise(pl.col("owner"))
        .alias("owner")
    )
    
    # Commit the updated table back to the state.
    # Since Polars uses Copy-on-Write, this is memory-efficient despite looking like a copy.
    state.update_table("regions", updated_regions)
    
    # Debug logging to verify the logic flow in the console.
    print(f"[System:Territory] Region {region_id} ownership transferred to '{new_owner_tag}'")