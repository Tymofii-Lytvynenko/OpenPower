import json
import shutil
import polars as pl
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from src.server.state import GameState
from src.shared.config import GameConfig

class SaveManager:
    """
    Manages the lifecycle of game save files (creation, loading, deletion).
    
    This module implements a 'Folder-based Save System' where each save is a 
    directory containing metadata (JSON) and heavy data (Parquet).
    
    Design Choices:
    1.  **Atomicity**: Saves are written to a temporary location first, then renamed. 
        This prevents save corruption if the game crashes during the write process.
    2.  **Parquet Storage**: We use Parquet for DataFrames because it supports compression 
        and schema preservation, which is critical for the ECS-like table structure.
    3.  **Metadata Separation**: 'meta.json' is separate to allow the UI to list 
        saves and show details (date, tick) without loading the heavy game state.
    """

    def __init__(self, config: GameConfig):
        self.config = config
        # We store saves in a dedicated 'saves' directory at the project root
        # to ensure user data is isolated from mod content and game assets.
        self.save_dir = self.config.project_root / "saves"
        self.save_dir.mkdir(parents=True, exist_ok=True)

    def save_game(self, state: GameState, save_name: str) -> bool:
        """
        Serializes the entire GameState to disk atomically.
        
        Args:
            state: The active GameState instance to serialize.
            save_name: The user-defined name for the save.
            
        Returns:
            bool: True if the operation succeeded, False otherwise.
        """
        # Sanitize input to prevent filesystem errors or path traversal
        safe_name = "".join(c for c in save_name if c.isalnum() or c in (' ', '_', '-')).strip()
        if not safe_name:
            print(f"[SaveManager] Error: Cannot save with empty or invalid name '{save_name}'")
            return False

        target_path = self.save_dir / safe_name
        temp_path = self.save_dir / f"{safe_name}_tmp"

        print(f"[SaveManager] Initiating save process for '{safe_name}'...")

        try:
            # 1. Prepare Workspace
            # Ensure we are writing to a clean temporary directory.
            if temp_path.exists():
                shutil.rmtree(temp_path)
            temp_path.mkdir()

            # 2. Serialize Metadata
            # Capture global simulation variables (time, date, etc.).
            # We explicitly separate this from the binary tables for fast UI access.
            meta_data = {
                "version": 1,  # Schema version for future migration support
                "timestamp": datetime.now().isoformat(),
                "globals": state.globals
            }
            
            with open(temp_path / "meta.json", "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=2)

            # 3. Serialize Tables
            # Iterate through all ECS tables and dump them as Parquet files.
            tables_dir = temp_path / "tables"
            tables_dir.mkdir()
            
            for table_name, df in state.tables.items():
                file_path = tables_dir / f"{table_name}.parquet"
                # Write to Parquet using Polars' efficient C++ implementation.
                df.write_parquet(file_path)

            # 4. Atomic Commit
            # The rename operation is atomic on POSIX. This is the "point of no return".
            # Before this line, a crash means the old save is untouched.
            if target_path.exists():
                shutil.rmtree(target_path)
            
            temp_path.rename(target_path)
            print(f"[SaveManager] Save '{safe_name}' completed successfully.")
            return True

        except Exception as e:
            print(f"[SaveManager] Critical Save Failure: {e}")
            # Cleanup garbage to prevent disk clutter
            if temp_path.exists():
                shutil.rmtree(temp_path)
            return False

    def load_game(self, save_name: str) -> Optional[GameState]:
        """
        Reconstructs a GameState from a save directory.
        
        Returns:
            GameState: A new state instance populated with the save data, 
                       or None if loading failed.
        """
        target_path = self.save_dir / save_name
        if not target_path.exists():
            print(f"[SaveManager] Save '{save_name}' not found.")
            return None

        try:
            print(f"[SaveManager] Loading save '{save_name}'...")
            
            # 1. Load Metadata
            meta_path = target_path / "meta.json"
            if not meta_path.exists():
                raise FileNotFoundError("Corrupted save: meta.json missing")

            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)

            state = GameState()
            
            # Restore globals
            # In a production environment, you might add migration logic here
            # if meta['version'] < CURRENT_VERSION.
            state.globals = meta.get("globals", {})

            # 2. Load Tables
            tables_dir = target_path / "tables"
            if tables_dir.exists():
                for file_path in tables_dir.glob("*.parquet"):
                    table_name = file_path.stem
                    # Polars reads Parquet very efficiently (often memory-mapped).
                    df = pl.read_parquet(file_path)
                    state.update_table(table_name, df)

            print(f"[SaveManager] Game loaded successfully. Tick: {state.globals.get('tick', 0)}")
            return state

        except Exception as e:
            print(f"[SaveManager] Load Failure: {e}")
            return None

    def get_save_list(self) -> List[Dict[str, Any]]:
        """
        Scans the save directory and returns a summary for the UI.
        
        Returns:
            List of dicts containing 'name', 'timestamp', and 'tick'.
            Sorted by most recent.
        """
        saves = []
        for p in self.save_dir.iterdir():
            if not p.is_dir():
                continue
                
            meta_file = p / "meta.json"
            if meta_file.exists():
                try:
                    with open(meta_file, "r") as f:
                        data = json.load(f)
                        saves.append({
                            "name": p.name,
                            "timestamp": data.get("timestamp", ""),
                            "tick": data.get("globals", {}).get("tick", 0)
                        })
                except Exception:
                    # Skip corrupted saves in the list rather than crashing
                    continue
                    
        return sorted(saves, key=lambda x: x["timestamp"], reverse=True)

    def delete_save(self, save_name: str) -> bool:
        """
        Permanently removes a save directory.
        """
        target_path = self.save_dir / save_name
        if target_path.exists() and target_path.is_dir():
            try:
                shutil.rmtree(target_path)
                print(f"[SaveManager] Deleted save '{save_name}'.")
                return True
            except Exception as e:
                print(f"[SaveManager] Failed to delete '{save_name}': {e}")
                return False
        return False