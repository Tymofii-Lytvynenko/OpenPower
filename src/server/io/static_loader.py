import rtoml
import polars as pl
from pathlib import Path
from typing import List, Dict, Any, Optional
from src.shared.config import GameConfig
from src.server.state import GameState

class StaticAssetLoader:
    """
    Responsible for loading immutable game data from static files (TSV/TOML).
    It populates the initial GameState with Definitions, Entities, and World State.

    Architecture:
    1. Definitions (data/definitions/*.toml): Static rules (resources, unit types).
    2. Map & Regions (data/map/*.tsv): Topography and geography.
    3. Countries (data/countries/*.tsv): Entity attributes.
    4. World State (data/world/*.toml): Relational data (wars, diplomacy, environment).

    This separation ensures that rules exist before entities, and entities exist 
    before relationships are established between them.
    """

    def __init__(self, config: GameConfig):
        self.config = config

    def compile_initial_state(self) -> GameState:
        """
        Aggregates data from all active mods to build the starting world state.
        Data loading order is critical for dependency resolution.
        """
        print("[StaticLoader] Compiling immutable game data...")
        state = GameState()
        
        # PHASE 1: Load Definitions
        # These are the "blueprints" of the game (e.g., what is 'Iron'?).
        # Other systems might reference these IDs immediately.
        definitions = self._load_toml_collection("definitions")
        for key, df in definitions.items():
            # We prefix definitions tables to avoid collision (e.g., 'def_resources')
            state.update_table(f"def_{key}", df)

        # PHASE 2: Load Entities (Backbone)
        # These are the physical actors and locations in the game.
        state.update_table("regions", self._load_regions())
        state.update_table("countries", self._load_countries())
        
        # PHASE 3: Load World State (Relations)
        # These are interactions or global conditions involving entities.
        # e.g., Wars, Diplomacy, Global Market.
        world_data = self._load_toml_collection("world")
        for key, df in world_data.items():
            state.update_table(key, df)
        
        return state

    # =========================================================================
    # SECTION: TSV LOADING (Entities & Map)
    # =========================================================================

    def _load_regions(self) -> pl.DataFrame:
        """
        Aggregates region data. Mods can override regions by Hex Color ID.
        """
        dfs = []
        for data_dir in self.config.get_data_dirs():
            # Support both new 'regions' folder and legacy 'map' folder
            p_new = data_dir / "regions" / "regions.tsv"
            p_old = data_dir / "map" / "regions.tsv"
            p = p_new if p_new.exists() else p_old
            
            if p.exists():
                print(f"[StaticLoader] Loading regions from {p}")
                dfs.append(self._read_tsv(p))
        
        if not dfs:
            print("[StaticLoader] Warning: No region definitions found.")
            return pl.DataFrame()
            
        # Vertical concatenation with deduplication ensures mod overrides work.
        # keep='last' means the last loaded mod (highest priority) wins.
        master_df = pl.concat(dfs, how="vertical").unique(subset=["hex"], keep="last")
        
        # Pre-calculate integer IDs for faster rendering lookups
        return self._generate_runtime_ids(master_df)

    def _load_countries(self) -> pl.DataFrame:
        """
        Aggregates country definitions. 
        Merges the main 'countries.tsv' with any extension files (Horizontal Join).
        """
        main_df = pl.DataFrame()
        
        # 1. Master Table (Base definitions)
        # Iterating to find the main country list. Currently, we overwrite 
        # previous lists, assuming the last mod provides the definitive list.
        for data_dir in self.config.get_data_dirs():
            master_path = data_dir / "countries" / "countries.tsv"
            if master_path.exists():
                main_df = self._read_tsv(master_path)
        
        if main_df.is_empty():
            return pl.DataFrame()

        # 2. Extensions (Adding columns via 'countries_*.tsv')
        # This allows mods to add new mechanics (e.g., 'countries_magic.tsv')
        # without redefining the entire country list.
        for data_dir in self.config.get_data_dirs():
            target_dir = data_dir / "countries"
            if not target_dir.exists(): continue

            for file_path in target_dir.glob("countries_*.tsv"):
                print(f"[StaticLoader] Merging country extension: {file_path.name}")
                aux_df = self._read_tsv(file_path)
                
                if "id" not in aux_df.columns: 
                    continue
                
                # Left join ensures we don't lose countries if the extension is partial
                main_df = main_df.join(aux_df, on="id", how="left")

        # 3. Safety Fill
        # Fill numeric NaNs with 0 to prevent crashes during math operations later.
        num_cols = [c for c, t in main_df.schema.items() if t in (pl.Float64, pl.Int64, pl.Int32, pl.UInt32)]
        if num_cols:
            main_df = main_df.with_columns(pl.col(num_cols).fill_null(0))

        return main_df

    def _read_tsv(self, path: Path) -> pl.DataFrame:
        """
        Robust TSV reader using Polars.
        Forces 'hex' column to String to prevent data corruption (00FF00 -> 255).
        """
        try:
            df = pl.read_csv(
                path, 
                separator="\t", 
                ignore_errors=True, 
                infer_schema_length=1000, 
                schema_overrides={"hex": pl.String} 
            )
            # Filter out internal columns (starting with underscore)
            valid_cols = [c for c in df.columns if not c.startswith("_")]
            return df.select(valid_cols)
        except Exception as e:
            print(f"[StaticLoader] Error reading {path.name}: {e}")
            return pl.DataFrame()

    def _generate_runtime_ids(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Converts Hex Strings (e.g. '#FF0000') to Int32 IDs.
        Formula: B + (G * 256) + (R * 65536). 
        Used for O(1) lookups in the rendering pipeline.
        """
        # Ensure format is uppercase #RRGGBB
        df = df.with_columns(
            pl.when(pl.col("hex").str.starts_with("#"))
            .then(pl.col("hex"))
            .otherwise(pl.lit("#") + pl.col("hex"))
            .str.to_uppercase()
            .alias("hex")
        )

        # Slice hex string into components and compute integer ID
        df = df.with_columns([
            pl.col("hex").str.slice(1, 2).map_elements(lambda x: int(x, 16), return_dtype=pl.UInt32).alias("_r"),
            pl.col("hex").str.slice(3, 2).map_elements(lambda x: int(x, 16), return_dtype=pl.UInt32).alias("_g"),
            pl.col("hex").str.slice(5, 2).map_elements(lambda x: int(x, 16), return_dtype=pl.UInt32).alias("_b"),
        ])
        
        df = df.with_columns(
            (pl.col("_b") + (pl.col("_g") * 256) + (pl.col("_r") * 65536)).cast(pl.Int32).alias("id")
        )
        
        return df.drop(["_r", "_g", "_b"])

    # =========================================================================
    # SECTION: TOML LOADING (Definitions & World)
    # =========================================================================

    def _load_toml_collection(self, folder_name: str) -> Dict[str, pl.DataFrame]:
        """
        Scans a specific folder (e.g., 'world' or 'definitions') in all mods.
        Merges TOML files with the same name across mods into single DataFrames.
        
        This generic approach allows us to add new data categories (like 'technology')
        without changing the loader code.
        """
        collected_data: Dict[str, List[pl.DataFrame]] = {}

        for data_dir in self.config.get_data_dirs():
            target_dir = data_dir / folder_name
            if not target_dir.exists():
                continue

            for file_path in target_dir.glob("*.toml"):
                key_name = file_path.stem  # e.g., 'wars' from 'wars.toml'
                
                try:
                    df = self._parse_toml_file(file_path, key_name)
                    if not df.is_empty():
                        if key_name not in collected_data:
                            collected_data[key_name] = []
                        collected_data[key_name].append(df)
                        print(f"[StaticLoader] Loaded '{folder_name}/{key_name}' from {file_path.name}")
                except Exception as e:
                    print(f"[StaticLoader] Error loading TOML {file_path}: {e}")

        # Concatenate collected DataFrames
        # 'diagonal_relaxed' handles cases where mods might add extra properties/columns
        final_tables = {}
        for key, dfs in collected_data.items():
            if dfs:
                final_tables[key] = pl.concat(dfs, how="diagonal_relaxed")
        
        return final_tables

    def _parse_toml_file(self, file_path: Path, key: str) -> pl.DataFrame:
        """
        Parses a single TOML file and detects its structure strategy.
        Uses 'rtoml' for high-performance parsing.

        Supported Strategies:
        
        1. LIST STRATEGY (Entity Component System style)
           Used for lists of definitions or events.
           Key matches filename: [[units]] inside units.toml
           
           Example 'units.toml':
               [[units]]
               id = "tank_t1"
               attack = 10
               
           Result: | id | attack |

        2. MATRIX STRATEGY (Adjacency Matrix / Dictionary style)
           Used for defining relationships between entities.
           Nested dictionaries: [diplomacy.USA] GBR = 100
           
           Result: | source | target | value |
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = rtoml.load(f)
        except Exception as e:
            print(f"[StaticLoader] Critical error reading {file_path}: {e}")
            return pl.DataFrame()

        raw_content = data.get(key)

        if raw_content is None:
            # Graceful failure: return empty if key is missing (e.g. empty file)
            return pl.DataFrame()

        # Strategy 1: Normalized List
        if isinstance(raw_content, list):
            return pl.from_dicts(raw_content)

        # Strategy 2: Adjacency Matrix / Nested Dictionary
        elif isinstance(raw_content, dict):
            # We need to distinguish between a Matrix (Source -> Target -> Value)
            # and an Entity Dictionary (Entity_ID -> {Properties})
            # If the first value is a dict, and it contains 'production' or other properties, 
            # it's likely an Entity Dictionary.
            first_val = next(iter(raw_content.values())) if raw_content else None
            if isinstance(first_val, dict) and any(k in first_val for k in ['production', 'legal', 'id', 'name']):
                return self._flatten_entity_dict(raw_content)
            return self._flatten_matrix(raw_content)

        else:
            print(f"[StaticLoader] Unknown data structure in {file_path.name} under key '{key}'")
            return pl.DataFrame()

    def _flatten_entity_dict(self, entity_data: Dict[str, Dict[str, Any]]) -> pl.DataFrame:
        """
        Converts a dictionary of entities into a normalized table.
        [section.entity_id] prop = value
        
        Result: | id | prop1 | prop2 |
        """
        rows = []
        for entity_id, properties in entity_data.items():
            if not isinstance(properties, dict):
                continue
            row = {"id": entity_id}
            row.update(properties)
            rows.append(row)
        
        return pl.from_dicts(rows)

    def _flatten_matrix(self, matrix_data: Dict[str, Any]) -> pl.DataFrame:
        """
        Flattens a nested dictionary structure into a normalized table.
        
        Handles two types of values:
        1. Scalar: USA -> GBR = 100 (becomes 'value' column)
        2. Complex: USA -> GBR = { trust=100, pact=true } (columns unrolled)
        """
        rows = []
        
        # Iterate through Source entities
        for source_tag, targets in matrix_data.items():
            if not isinstance(targets, dict):
                continue

            # Iterate through Target entities
            for target_tag, value in targets.items():
                row = {
                    "source": source_tag,
                    "target": target_tag
                }

                if isinstance(value, dict):
                    # Complex value: merge dict into row
                    row.update(value)
                else:
                    # Simple value: assign to generic 'value' column
                    row["value"] = value
                
                rows.append(row)

        if not rows:
            return pl.DataFrame()

        return pl.from_dicts(rows)