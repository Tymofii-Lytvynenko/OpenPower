import polars as pl
import rtoml
from pathlib import Path
from typing import List

from src.server.state import GameState
from src.shared.config import GameConfig

class DataLoader:
    """
    Responsible for compiling TSV/TOML files into the GameState.
    
    Key Features:
    1. **Hex is Key:** Merges files based on the 'hex' column.
    2. **Int Optimization:** Generates an 'id' (Int32) column from hex for runtime speed.
    3. **Dev Friendly:** Ignores columns starting with '_' (comments).
    """

    def __init__(self, config: GameConfig):
        self.config = config

    def load_initial_state(self) -> GameState:
        print("[DataLoader] Compiling state (Hex-Key Mode)...")
        state = GameState()
        
        # --- 1. REGIONS ---
        # Step A: Load the Backbone (regions.tsv containing 'hex')
        regions_df = self._load_master_regions()
        
        if not regions_df.is_empty():
            # Step B: Generate the Runtime ID (Int32) from Hex
            # This allows the engine/renderer to work with fast ints, while humans use hex.
            regions_df = self._generate_int_id(regions_df)
            
            # Step C: Enrich (Join 'regions_pop.tsv', 'regions_res.tsv' on 'hex')
            regions_df = self._enrich_regions_data(regions_df)
            
            # Step D: Safety Fill
            # Fill numeric columns with 0 to prevent math errors on nulls
            num_cols = [c for c, t in regions_df.schema.items() if t in (pl.Float64, pl.Int64, pl.Int32)]
            if num_cols:
                regions_df = regions_df.with_columns(pl.col(num_cols).fill_null(0))

            state.update_table("regions", regions_df)
            print(f"[DataLoader] Regions loaded: {len(regions_df)}")
        else:
            print("[DataLoader] CRITICAL: No regions found!")
            state.update_table("regions", pl.DataFrame())

        # --- 2. COUNTRIES ---
        countries_df = self._load_countries()
        state.update_table("countries", countries_df if not countries_df.is_empty() else pl.DataFrame())
             
        return state

    def _read_clean_tsv(self, path: Path) -> pl.DataFrame:
        """Reads TSV, forcing 'hex' to string, and ignoring '_' columns."""
        try:
            # dtypes={"hex": pl.Utf8} ensures #000000 isn't parsed weirdly
            df = pl.read_csv(path, separator="\t", ignore_errors=True, infer_schema_length=1000, dtypes={"hex": pl.Utf8})
            
            # Filter out developer comment columns
            valid_cols = [c for c in df.columns if not c.startswith("_")]
            return df.select(valid_cols)
        except Exception as e:
            print(f"[DataLoader] Error reading {path.name}: {e}")
            return pl.DataFrame()

    def _load_master_regions(self) -> pl.DataFrame:
        """Loads 'regions.tsv' to find all defined HEX codes."""
        dfs = []
        for data_dir in self.config.get_data_dirs():
            # Support both structure preferences
            paths = [data_dir / "regions" / "regions.tsv", data_dir / "map" / "regions.tsv"]
            for p in paths:
                if p.exists():
                    df = self._read_clean_tsv(p)
                    if "hex" in df.columns:
                        # Normalize hex: Uppercase, remove # for internal consistency during join
                        df = df.with_columns(pl.col("hex").str.strip_prefix("#").str.to_uppercase())
                        dfs.append(df)
                    break 
        
        if not dfs: return pl.DataFrame()
        # Merge by HEX (Last loaded mod wins)
        return pl.concat(dfs, how="vertical").unique(subset=["hex"], keep="last")

    def _generate_int_id(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Generates the 'id' (Int32) column from the 'hex' column.
        """
        # Calculate BGR Int32
        df = df.with_columns([
            pl.col("hex").str.slice(0, 2).map_elements(lambda x: int(x, 16), return_dtype=pl.UInt32).alias("_r"),
            pl.col("hex").str.slice(2, 2).map_elements(lambda x: int(x, 16), return_dtype=pl.UInt32).alias("_g"),
            pl.col("hex").str.slice(4, 2).map_elements(lambda x: int(x, 16), return_dtype=pl.UInt32).alias("_b"),
        ])
        
        df = df.with_columns(
            (pl.col("_b") + (pl.col("_g") * 256) + (pl.col("_r") * 65536)).cast(pl.Int32).alias("id")
        )
        
        # Restore '#' to the hex column for UI readability
        df = df.with_columns(("#" + pl.col("hex")).alias("hex"))
        
        return df.drop(["_r", "_g", "_b"])

    def _enrich_regions_data(self, main_df: pl.DataFrame) -> pl.DataFrame:
        """
        Scans for auxiliary files (pop, res) and Joins them on 'hex'.
        """
        for data_dir in self.config.get_data_dirs():
            target_dir = data_dir / "regions"
            if not target_dir.exists(): continue
            
            for file_path in target_dir.glob("*.tsv"):
                if file_path.name == "regions.tsv": continue 
                
                aux_df = self._read_clean_tsv(file_path)
                if "hex" not in aux_df.columns: continue
                
                # Normalize aux hex to match main_df (which now has '#')
                # If aux file has 'FF0000', add '#'. If '#FF0000', keep it.
                aux_df = aux_df.with_columns(
                    pl.when(pl.col("hex").str.starts_with("#"))
                    .then(pl.col("hex"))
                    .otherwise("#" + pl.col("hex"))
                    .str.to_uppercase()
                    .alias("hex")
                )
                
                print(f"[DataLoader] Merging data from: {file_path.name}")
                main_df = main_df.join(aux_df, on="hex", how="left", suffix=f"_{file_path.stem}")
                
        return main_df

    def _load_countries(self) -> pl.DataFrame:
        """
        Loads 'countries.tsv' and merges any 'countries_*.tsv' extensions.
        """
        print("[DataLoader] Loading Countries...")
        
        main_df = pl.DataFrame()
        
        # 1. Find the Master Table (countries.tsv)
        for data_dir in self.config.get_data_dirs():
            master_path = data_dir / "countries" / "countries.tsv"
            if master_path.exists():
                main_df = self._read_clean_tsv(master_path)
                break # Found master, stop searching
        
        if main_df.is_empty():
            return pl.DataFrame()

        # 2. Find and Merge Extensions (eco, pol, dem, mil)
        # We look in ALL active mod directories for extra data
        for data_dir in self.config.get_data_dirs():
            target_dir = data_dir / "countries"
            if not target_dir.exists(): continue

            for file_path in target_dir.glob("countries_*.tsv"):
                # Skip the master file if strictly named countries_countries.tsv (unlikely)
                
                print(f"[DataLoader] Merging country data: {file_path.name}")
                aux_df = self._read_clean_tsv(file_path)
                
                # Check if join key exists
                if "id" not in aux_df.columns:
                    print(f"   [Warning] {file_path.name} missing 'id' column. Skipping.")
                    continue

                # Merge: Left Join ensures we only add data for countries that exist in master
                # We do NOT use suffixes here because we want clean column names like 'money_balance'
                # directly in the main table.
                main_df = main_df.join(aux_df, on="id", how="left")

        # 3. Fill N/A for numeric columns (Safety)
        # This prevents crashes if a country is missing from 'countries_eco.tsv'
        num_cols = [c for c, t in main_df.schema.items() if t in (pl.Float64, pl.Int64, pl.Int32)]
        if num_cols:
            main_df = main_df.with_columns(pl.col(num_cols).fill_null(0))

        print(f"[DataLoader] Countries loaded: {len(main_df)} rows, {len(main_df.columns)} columns.")
        return main_df