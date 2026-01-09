import dataclasses
import shutil
import polars as pl
import orjson
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

from src.server.state import GameState
from src.shared.config import GameConfig

class SaveWriter:
    """
    Manages the persistence of GameState to disk.
    Handles Atomic Writes (Save) and Disk Management (Delete/List).
    
    This class complements SaveStateLoader. While Loader focuses on 
    object reconstruction, Writer focuses on serialization and file I/O.
    """
    
    def __init__(self, config: GameConfig):
        self.config = config
        self.save_root = config.project_root / "user_data" / "saves"
        self.save_root.mkdir(parents=True, exist_ok=True)

    def save_game(self, state: GameState, save_name: str) -> bool:
        """
        Serializes the GameState to disk atomically using Parquet and orjson.
        Atomic Write: Writes to a tmp folder first, then renames.
        """
        # Sanitize name to prevent path traversal or filesystem errors
        safe_name = "".join(c for c in save_name if c.isalnum() or c in (' ', '_', '-')).strip()
        if not safe_name:
            print(f"[SaveWriter] Error: Invalid save name '{save_name}'")
            return False

        target_path = self.save_root / safe_name
        temp_path = self.save_root / f"{safe_name}_tmp"

        print(f"[SaveWriter] Saving '{safe_name}'...")

        try:
            # 1. Clean Workspace
            if temp_path.exists():
                shutil.rmtree(temp_path)
            temp_path.mkdir()

            # 2. Serialize Data
            self._write_state_to_disk(state, temp_path)

            # 3. Atomic Commit (Rename)
            # If target exists, remove it first (Windows requires this; POSIX atomic rename is simpler but this is safer X-platform)
            if target_path.exists():
                shutil.rmtree(target_path)
            
            temp_path.rename(target_path)
            
            print(f"[SaveWriter] Saved '{safe_name}' successfully.")
            return True

        except Exception as e:
            print(f"[SaveWriter] Critical Save Failure: {e}")
            # Cleanup temp garbage on failure
            if temp_path.exists():
                shutil.rmtree(temp_path)
            return False

    def _write_state_to_disk(self, state: GameState, path: Path):
        """
        Internal serialization logic using Reflection.
        """
        meta_data = {
            "version": 1,
            "timestamp": datetime.now().isoformat(),
        }

        for field in dataclasses.fields(state):
            key = field.name
            value = getattr(state, key)

            # Strategy A: Polars DataFrames -> Parquet
            if isinstance(value, pl.DataFrame):
                value.write_parquet(path / f"{key}.parquet")

            # Strategy B: Dict[str, DataFrame] -> Folder of Parquets
            elif isinstance(value, dict) and value and isinstance(next(iter(value.values())), pl.DataFrame):
                sub_dir = path / key
                sub_dir.mkdir(exist_ok=True)
                for tbl_name, df in value.items():
                    df.write_parquet(sub_dir / f"{tbl_name}.parquet")

            # Strategy C: Dataclasses -> Dict (for JSON)
            elif dataclasses.is_dataclass(value):
                meta_data[key] = dataclasses.asdict(value)

            # Strategy D: Primitives -> JSON
            else:
                meta_data[key] = value

        # Write Metadata (orjson is fast and handles numpy types well)
        with open(path / "meta.json", "wb") as f:
            f.write(orjson.dumps(meta_data, option=orjson.OPT_INDENT_2))

    def delete_save(self, save_name: str) -> bool:
        """
        Permanently removes a save directory.
        """
        target_path = self.save_root / save_name
        if target_path.exists() and target_path.is_dir():
            try:
                shutil.rmtree(target_path)
                print(f"[SaveWriter] Deleted save '{save_name}'.")
                return True
            except Exception as e:
                print(f"[SaveWriter] Failed to delete '{save_name}': {e}")
                return False
        return False

    def get_available_saves(self) -> List[Dict[str, Any]]:
        """
        Scans the save directory and returns metadata for UI lists.
        Sorted by timestamp (newest first).
        """
        saves = []
        for p in self.save_root.iterdir():
            if not p.is_dir(): continue
                
            meta_file = p / "meta.json"
            if meta_file.exists():
                try:
                    # Quick read of just the JSON for listing
                    with open(meta_file, "rb") as f:
                        data = orjson.loads(f.read())
                        saves.append({
                            "name": p.name,
                            "timestamp": data.get("timestamp", ""),
                            # Robustly handle potential missing keys in globals
                            "tick": data.get("globals", {}).get("tick", 0)
                        })
                except Exception:
                    # Corrupt save or locked file, skip
                    continue
                    
        return sorted(saves, key=lambda x: x["timestamp"], reverse=True)