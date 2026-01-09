import dataclasses
import polars as pl
import orjson
from pathlib import Path
from typing import get_type_hints, Any
from src.server.state import GameState
from src.shared.config import GameConfig

class SaveStateLoader:
    """
    Responsible strictly for reconstructing GameState from user save files (Parquet/JSON).
    Uses reflection to map disk data back to the GameState dataclass structure.
    """
    def __init__(self, config: GameConfig):
        self.save_root = config.project_root / "user_data" / "saves"

    def load(self, save_name: str) -> GameState:
        """
        Loads a specific save directory into a GameState object.
        """
        save_dir = self.save_root / save_name
        if not save_dir.exists():
            raise FileNotFoundError(f"Save '{save_name}' not found at {save_dir}")

        print(f"[SaveLoader] Restoring save '{save_name}'...")

        # 1. Load Metadata (Global variables, Time, Non-tabular data)
        # We use orjson for high-performance JSON parsing
        meta = {}
        meta_path = save_dir / "meta.json"
        if meta_path.exists():
            with open(meta_path, "rb") as f:
                meta = orjson.loads(f.read())
        else:
            print(f"[SaveLoader] Warning: meta.json missing for {save_name}. Using defaults.")

        # 2. Reflection: Build Constructor Arguments
        # We iterate over the fields defined in GameState and fetch their values
        # from either the parquet files (tables) or the metadata JSON (primitives).
        constructor_args = {}
        type_hints = get_type_hints(GameState)

        for field in dataclasses.fields(GameState):
            key = field.name
            target_type = type_hints.get(key)

            # Strategy A: The 'tables' dictionary (Dynamic collection of DataFrames)
            # We expect a subdirectory named 'tables' containing .parquet files.
            if key == "tables":
                constructor_args[key] = self._load_tables_dir(save_dir / "tables")

            # Strategy B: Single DataFrame fields (if any exist in root of State)
            elif target_type == pl.DataFrame:
                p_file = save_dir / f"{key}.parquet"
                if p_file.exists():
                    constructor_args[key] = pl.read_parquet(p_file)
                else:
                    constructor_args[key] = pl.DataFrame()

            # Strategy C: Nested Dataclasses (e.g., state.time)
            # We reconstruct them from the dictionary found in meta.json
            elif dataclasses.is_dataclass(target_type):
                data_dict = meta.get(key, {})
                # Recursive safety: check if data is actually a dict
                if isinstance(data_dict, dict):
                    constructor_args[key] = target_type(**data_dict)
                else:
                    # Fallback for empty/corrupt data
                    constructor_args[key] = target_type()

            # Strategy D: Primitives (int, float, list, etc.)
            else:
                if key in meta:
                    constructor_args[key] = meta[key]

        # 3. Construct and Return
        state = GameState(**constructor_args)
        print(f"[SaveLoader] Save loaded successfully. Tick: {state.globals.get('tick', 0)}")
        return state

    def _load_tables_dir(self, path: Path) -> dict:
        """
        Scans a directory for .parquet files and loads them into a dictionary.
        Key = Filename (without extension), Value = DataFrame.
        """
        tables = {}
        if path.exists() and path.is_dir():
            for p_file in path.glob("*.parquet"):
                try:
                    # Lazy loading is possible but eager is safer for GameState ownership
                    tables[p_file.stem] = pl.read_parquet(p_file)
                except Exception as e:
                    print(f"[SaveLoader] Error loading table {p_file.name}: {e}")
        return tables