import polars as pl
from src.server.state import GameState
from src.shared.config import GameConfig

class DataExporter:
    """
    Saves the 'regions.tsv' backbone.
    """
    def __init__(self, config: GameConfig):
        self.config = config

    def save_regions(self, state: GameState):
        target_dir = self.config.get_write_data_dir() / "regions"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / "regions.tsv"
        
        print(f"[Exporter] Saving regions to {target_path}...")
        df = state.get_table("regions")
        
        # We use the 'hex' column which is preserved in the DataFrame.
        # We explicitly exclude the runtime 'id' (int) and any developer comments.
        
        # Define preferred column order
        priority_cols = ["hex", "name", "owner", "type"]
        
        # Filter valid columns (excluding 'id' and '_*')
        cols_to_save = [c for c in priority_cols if c in df.columns]
        
        # Add any other columns found in the DF that are NOT in priority list, NOT 'id', and NOT internal
        extra_cols = [c for c in df.columns if c not in priority_cols and c != "id" and not c.startswith("_")]
        
        # Note: In a split-file system, we might be saving 'population' here too if we aren't careful.
        # Ideally, we should only save columns that belong to the backbone.
        # For this MVP, we will assume the user manually manages split files or we save everything flat.
        # Let's stick to saving essential backbone data to keep it clean.
        
        final_cols = cols_to_save # + extra_cols (Uncomment if you want to flatten everything into one file)
        
        df.select(final_cols).write_csv(target_path, separator="\t")