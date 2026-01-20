import dataclasses
import polars as pl
import rtoml
import orjson
from pathlib import Path
from typing import List, Dict, Any, get_type_hints
from datetime import datetime

from src.server.state import GameState
from src.shared.config import GameConfig

class DataLoader:
    """
    Responsible for loading GameState data from two sources:
    1. Static Assets (TSV/TOML) -> For starting a fresh game (load_initial_state).
    2. User Saves (Parquet/JSON) -> For loading a saved session (load_save).
    """

    def __init__(self, config: GameConfig):
        self.config = config
        self.save_root = config.project_root / "user_data" / "saves"

    # =========================================================================
    #  PART 1: SAVE GAME LOADING (Reflection Based)
    # =========================================================================

    def load_save(self, save_name: str) -> GameState:
        """
        Reconstructs a GameState from a save directory using type-driven reflection.
        """
        save_dir = self.save_root / save_name
        if not save_dir.exists():
            raise FileNotFoundError(f"Save '{save_name}' not found.")

        print(f"[DataLoader] Loading save '{save_name}'...")

        # 1. Load Metadata (JSON)
        # We use orjson for speed.
        meta_path = save_dir / "meta.json"
        if meta_path.exists():
            with open(meta_path, "rb") as f:
                meta_data = orjson.loads(f.read())
        else:
            print(f"[DataLoader] Warning: meta.json not found for {save_name}. Using defaults.")
            meta_data = {}

        # 2. Reflection: Build Constructor Arguments
        constructor_args = {}
        type_hints = get_type_hints(GameState)

        for field in dataclasses.fields(GameState):
            key = field.name
            target_type = type_hints.get(key)
            
            # Strategy A: Dynamic Table Collections (e.g., state.tables: Dict[str, DataFrame])
            # We assume any Dict[str, DataFrame] implies a folder of parquets.
            if key == "tables": 
                tables = {}
                sub_dir = save_dir / key
                if sub_dir.exists():
                    for p_file in sub_dir.glob("*.parquet"):
                        tables[p_file.stem] = pl.read_parquet(p_file)
                constructor_args[key] = tables

            # Strategy B: Single DataFrame Fields
            elif target_type == pl.DataFrame:
                p_file = save_dir / f"{key}.parquet"
                if p_file.exists():
                    constructor_args[key] = pl.read_parquet(p_file)
                else:
                    constructor_args[key] = pl.DataFrame()

            # Strategy C: Nested Dataclasses (e.g., state.time)
            elif dataclasses.is_dataclass(target_type):
                data_dict = meta_data.get(key, {})
                constructor_args[key] = target_type(**data_dict) # type: ignore

            # Strategy D: Primitives (globals, tick, etc.)
            else:
                if key in meta_data:
                    constructor_args[key] = meta_data[key]

        state = GameState(**constructor_args)
        print(f"[DataLoader] Save loaded successfully. Tick: {state.globals.get('tick', 0)}")
        return state

    # =========================================================================
    #  PART 2: INITIAL STATE COMPILATION (Static Assets)
    #  (Preserved from your original code)
    # =========================================================================

    def load_initial_state(self) -> GameState:
        print("[DataLoader] Compiling state (Hex-Key Mode)...")
        state = GameState()
        
        # --- 1. REGIONS ---
        regions_df = self._load_master_regions()
        
        if not regions_df.is_empty():
            # Generate Runtime ID
            regions_df = self._generate_int_id(regions_df)
            # Enrich with pop/res data
            regions_df = self._enrich_regions_data(regions_df)
            
            # Safety Fill
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
            df = pl.read_csv(
                path, 
                separator="\t", 
                ignore_errors=True, 
                infer_schema_length=1000, 
                schema_overrides={"hex": pl.String} # 'schema_overrides' is the modern arg
            )
            valid_cols = [c for c in df.columns if not c.startswith("_")]
            return df.select(valid_cols)
        except Exception as e:
            print(f"[DataLoader] Error reading {path.name}: {e}")
            return pl.DataFrame()

    def _load_master_regions(self) -> pl.DataFrame:
        dfs = []
        for data_dir in self.config.get_data_dirs():
            paths = [data_dir / "regions" / "regions.tsv", data_dir / "map" / "regions.tsv"]
            for p in paths:
                if p.exists():
                    df = self._read_clean_tsv(p)
                    if "hex" in df.columns:
                        df = df.with_columns(pl.col("hex").str.strip_prefix("#").str.to_uppercase())
                        dfs.append(df)
                    break 
        
        if not dfs: return pl.DataFrame()
        return pl.concat(dfs, how="vertical").unique(subset=["hex"], keep="last")

    def _generate_int_id(self, df: pl.DataFrame) -> pl.DataFrame:
        df = df.with_columns([
            pl.col("hex").str.slice(0, 2).map_elements(lambda x: int(x, 16), return_dtype=pl.UInt32).alias("_r"),
            pl.col("hex").str.slice(2, 2).map_elements(lambda x: int(x, 16), return_dtype=pl.UInt32).alias("_g"),
            pl.col("hex").str.slice(4, 2).map_elements(lambda x: int(x, 16), return_dtype=pl.UInt32).alias("_b"),
        ])
        df = df.with_columns(
            (pl.col("_b") + (pl.col("_g") * 256) + (pl.col("_r") * 65536)).cast(pl.Int32).alias("id")
        )
        # Restore '#' to the hex column
        df = df.with_columns(("#" + pl.col("hex")).alias("hex"))
        return df.drop(["_r", "_g", "_b"])

    def _enrich_regions_data(self, main_df: pl.DataFrame) -> pl.DataFrame:
        for data_dir in self.config.get_data_dirs():
            target_dir = data_dir / "regions"
            if not target_dir.exists(): continue
            
            for file_path in target_dir.glob("*.tsv"):
                if file_path.name == "regions.tsv": continue 
                
                aux_df = self._read_clean_tsv(file_path)
                if "hex" not in aux_df.columns: continue
                
                # Normalize aux hex
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
        print("[DataLoader] Loading Countries...")
        main_df = pl.DataFrame()
        
        # 1. Master Table
        for data_dir in self.config.get_data_dirs():
            master_path = data_dir / "countries" / "countries.tsv"
            if master_path.exists():
                main_df = self._read_clean_tsv(master_path)
                break 
        
        if main_df.is_empty():
            return pl.DataFrame()

        # 2. Extensions
        for data_dir in self.config.get_data_dirs():
            target_dir = data_dir / "countries"
            if not target_dir.exists(): continue

            for file_path in target_dir.glob("countries_*.tsv"):
                print(f"[DataLoader] Merging country data: {file_path.name}")
                aux_df = self._read_clean_tsv(file_path)
                if "id" not in aux_df.columns: continue
                main_df = main_df.join(aux_df, on="id", how="left")

        # 3. Safety Fill
        num_cols = [c for c, t in main_df.schema.items() if t in (pl.Float64, pl.Int64, pl.Int32)]
        if num_cols:
            main_df = main_df.with_columns(pl.col(num_cols).fill_null(0))

        print(f"[DataLoader] Countries loaded: {len(main_df)} rows.")
        return main_df