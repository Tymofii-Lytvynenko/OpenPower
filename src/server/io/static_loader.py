import polars as pl
from pathlib import Path
from typing import List
from src.shared.config import GameConfig
from src.server.state import GameState

class StaticAssetLoader:
    """
    Responsible strictly for loading immutable game definitions (TSV/TOML).
    It populates the initial GameState with static data (Regions, Countries).
    
    This separates the 'Game Rules' loading from the 'Save State' loading.
    """
    def __init__(self, config: GameConfig):
        self.config = config

    def compile_initial_state(self) -> GameState:
        """
        Aggregates data from all active mods to build the starting world state.
        """
        print("[StaticLoader] Compiling immutable game data...")
        state = GameState()
        
        # 1. Load Backbone Tables
        # These tables define the static world (map, factions, definitions)
        state.update_table("regions", self._load_regions())
        state.update_table("countries", self._load_countries())
        
        return state

    def _load_regions(self) -> pl.DataFrame:
        """
        Aggregates region data from all active mods.
        Mods loaded later override earlier ones based on the Hex Color ID.
        """
        dfs = []
        for data_dir in self.config.get_data_dirs():
            p = data_dir / "regions" / "regions.tsv"
            # Also check legacy path
            if not p.exists():
                p = data_dir / "map" / "regions.tsv"
                
            if p.exists():
                print(f"[StaticLoader] Loading regions from {p}")
                dfs.append(self._read_tsv(p))
        
        if not dfs:
            print("[StaticLoader] Warning: No region definitions found.")
            return pl.DataFrame()
            
        # Vertical concat + deduplicate by Hex Color
        # keep='last' ensures mod overrides work (latest loaded mod wins)
        master_df = pl.concat(dfs, how="vertical").unique(subset=["hex"], keep="last")
        
        # Optimize IDs for runtime
        return self._generate_runtime_ids(master_df)

    def _load_countries(self) -> pl.DataFrame:
        """
        Aggregates country definitions.
        """
        main_df = pl.DataFrame()
        
        # 1. Master Table (Base definitions)
        for data_dir in self.config.get_data_dirs():
            master_path = data_dir / "countries" / "countries.tsv"
            if master_path.exists():
                main_df = self._read_tsv(master_path)
                break 
        
        if main_df.is_empty():
            return pl.DataFrame()

        # 2. Extensions (Partial tables adding columns/rows)
        for data_dir in self.config.get_data_dirs():
            target_dir = data_dir / "countries"
            if not target_dir.exists(): continue

            for file_path in target_dir.glob("countries_*.tsv"):
                print(f"[StaticLoader] Merging country extension: {file_path.name}")
                aux_df = self._read_tsv(file_path)
                if "id" not in aux_df.columns: continue
                
                # Join new columns onto the master dataframe
                main_df = main_df.join(aux_df, on="id", how="left")

        # 3. Safety Fill (NaNs -> 0 for numeric columns)
        num_cols = [c for c, t in main_df.schema.items() if t in (pl.Float64, pl.Int64, pl.Int32)]
        if num_cols:
            main_df = main_df.with_columns(pl.col(num_cols).fill_null(0))

        return main_df

    def _read_tsv(self, path: Path) -> pl.DataFrame:
        """
        Robust TSV reader. Forces 'hex' to string to prevent int conversion errors.
        Ignores internal columns starting with '_'.
        """
        try:
            df = pl.read_csv(
                path, 
                separator="\t", 
                ignore_errors=True, 
                infer_schema_length=1000, 
                dtypes={"hex": pl.Utf8}
            )
            # Filter out internal columns immediately
            valid_cols = [c for c in df.columns if not c.startswith("_")]
            return df.select(valid_cols)
        except Exception as e:
            print(f"[StaticLoader] Error reading {path.name}: {e}")
            return pl.DataFrame()

    def _generate_runtime_ids(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Converts Hex Strings (e.g. '#FF0000') to Int32 IDs for fast rendering lookups.
        Formula: B + (G * 256) + (R * 65536)
        """
        # Ensure format is uppercase #RRGGBB
        df = df.with_columns(
            pl.when(pl.col("hex").str.starts_with("#"))
            .then(pl.col("hex"))
            .otherwise(pl.lit("#") + pl.col("hex"))
            .str.to_uppercase()
            .alias("hex")
        )

        # Slice and calculate
        df = df.with_columns([
            pl.col("hex").str.slice(1, 2).map_elements(lambda x: int(x, 16), return_dtype=pl.UInt32).alias("_r"),
            pl.col("hex").str.slice(3, 2).map_elements(lambda x: int(x, 16), return_dtype=pl.UInt32).alias("_g"),
            pl.col("hex").str.slice(5, 2).map_elements(lambda x: int(x, 16), return_dtype=pl.UInt32).alias("_b"),
        ])
        
        df = df.with_columns(
            (pl.col("_b") + (pl.col("_g") * 256) + (pl.col("_r") * 65536)).cast(pl.Int32).alias("id")
        )
        
        return df.drop(["_r", "_g", "_b"])