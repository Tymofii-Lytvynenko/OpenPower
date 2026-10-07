import dataclasses
import shutil
import tempfile

import orjson
import polars as pl
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List

from src.shared.config import GameConfig
from src.shared.migrations import SAVE_FORMAT_VERSION
from src.shared.state import GameState, persistent_state_field_names, persistent_state_fields
from src.core.saves import (
    list_available_saves,
    save_backup_path,
    validate_save_name,
)


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
        try:
            safe_name = validate_save_name(save_name)
        except ValueError:
            print(f"[SaveWriter] Error: Invalid save name '{save_name}'")
            return False

        target_path = self.save_root / safe_name
        backup_path = save_backup_path(self.save_root, safe_name)
        temp_path: Path | None = None

        print(f"[SaveWriter] Saving '{safe_name}'...")

        try:
            # Stage on the same filesystem so the final directory rename is atomic.
            temp_path = Path(tempfile.mkdtemp(prefix=f".{safe_name}.tmp-", dir=self.save_root))
            self._write_state_to_disk(state, temp_path)

            self._commit_staged_save(temp_path, target_path, backup_path)
            # Removing the previous generation is cleanup only; the new slot is already installed.
            if backup_path.exists():
                shutil.rmtree(backup_path, ignore_errors=True)
            
            print(f"[SaveWriter] Saved '{safe_name}' successfully.")
            return True

        except Exception as e:
            print(f"[SaveWriter] Critical Save Failure: {e}")
            # Cleanup temp garbage on failure
            if temp_path is not None and temp_path.exists():
                shutil.rmtree(temp_path, ignore_errors=True)
            return False

    @staticmethod
    def _commit_staged_save(temp_path: Path, target_path: Path, backup_path: Path) -> None:
        if backup_path.exists():
            if target_path.exists():
                shutil.rmtree(backup_path)
            else:
                backup_path.rename(target_path)

        had_previous_save = target_path.exists()
        if had_previous_save:
            target_path.rename(backup_path)

        try:
            temp_path.rename(target_path)
        except Exception:
            if had_previous_save and backup_path.exists() and not target_path.exists():
                backup_path.rename(target_path)
            raise

    def _write_state_to_disk(self, state: GameState, path: Path):
        """
        Internal serialization logic using Reflection.
        """
        meta_data = {
            "version": SAVE_FORMAT_VERSION,
            "timestamp": datetime.now().isoformat(),
            "schema_versions": (
                state.schema_registry.versions() if state.schema_registry is not None else {}
            ),
            "persistent_fields": list(persistent_state_field_names()),
            "checkpointed_systems": sorted(state.system_state.keys()),
        }

        for field in persistent_state_fields():
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
                meta_data[key] = dataclasses.asdict(value) # type: ignore

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
        try:
            safe_name = validate_save_name(save_name)
        except ValueError:
            return False

        target_path = self.save_root / safe_name
        backup_path = save_backup_path(self.save_root, safe_name)
        paths = (target_path, backup_path)
        if any(path.exists() and path.is_dir() for path in paths):
            try:
                for path in paths:
                    if path.exists() and path.is_dir():
                        shutil.rmtree(path)
                print(f"[SaveWriter] Deleted save '{safe_name}'.")
                return True
            except Exception as e:
                print(f"[SaveWriter] Failed to delete '{save_name}': {e}")
                return False
        return False

    def get_available_saves(self) -> List[Dict[str, Any]]:
        """Delegates to the shared core helper so the listing logic lives in one place."""
        return list_available_saves(self.config)
