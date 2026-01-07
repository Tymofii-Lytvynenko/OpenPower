import polars as pl
from src.server.state import GameState

def apply_tax_change(state: GameState, country_tag: str, new_rate: float):
    """
    Updates the tax rate modifier for a specific country.
    
    Responsibility:
        This function acts as a gatekeeper for the data. It ensures that 
        invalid inputs from the UI or network (like -50% tax) are clamped 
        to safe ranges before they ever touch the simulation state.
    """
    # 1. Validation Logic
    # Clamp the tax rate between 0.0 (0%) and 1.0 (100%).
    # This prevents simulation crashes or exploits (e.g., infinite money glitches).
    validated_rate = max(0.0, min(new_rate, 1.0))
    
    countries_df = state.get_table("countries")
    
    # 2. Vectorized Update
    # We update the 'global_tax_mod' column for the specific country.
    # If the column doesn't exist (e.g., early prototype data), Polars might raise an error,
    # encouraging strict schema adherence.
    updated_countries = countries_df.with_columns(
        pl.when(pl.col("id") == country_tag)
        .then(pl.lit(validated_rate))
        .otherwise(pl.col("global_tax_mod"))
        .alias("global_tax_mod")
    )

    state.update_table("countries", updated_countries)
    print(f"[System:Economy] Country '{country_tag}' tax adjusted to {validated_rate:.1%}")

def calculate_daily_income(state: GameState):
    """
    Example of a continuous simulation step (to be used in the future).
    Calculates income for ALL countries at once without a Python loop.
    """
    # Placeholder for future logic:
    # 1. Join Regions with Countries on 'owner_id'
    # 2. Multiply Region GDP * Country Tax Rate
    # 3. Aggregation (Sum) by Country
    # 4. Update Country Balance
    pass