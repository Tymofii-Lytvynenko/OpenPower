"""
Save file discovery utility.

This module provides a read-only helper for listing available save files.
It is safe to import from any layer (client, server, engine, modules) because
it only performs filesystem I/O and has no dependencies on simulation state.
"""

import orjson
import logging
from pathlib import Path
from typing import Any, Dict, List

from src.shared.config import GameConfig

logger = logging.getLogger(__name__)


def sanitize_save_name(save_name: str) -> str:
    """Return the canonical slot name used by the save writer."""
    return "".join(c for c in str(save_name) if c.isalnum() or c in (" ", "_", "-")).strip()


def validate_save_name(save_name: str) -> str:
    """Reject non-canonical names before they are used to access a save path."""
    raw_name = str(save_name or "").strip()
    safe_name = sanitize_save_name(raw_name)
    if not safe_name or safe_name != raw_name:
        raise ValueError("Save name must contain only letters, numbers, spaces, '_' or '-'.")
    return safe_name


def save_backup_path(save_root: Path, save_name: str) -> Path:
    return save_root / f".{save_name}.backup"


def save_mod_compatibility_error(metadata, active_mods) -> str:
    if "active_mods" not in metadata:
        return ""
    saved_mods = metadata["active_mods"]
    if not isinstance(saved_mods, list) or not all(isinstance(mod, str) and mod for mod in saved_mods):
        return "Invalid mod metadata."
    active = list(active_mods)
    if saved_mods == active:
        return ""
    return f"Requires mods in this order: {', '.join(saved_mods) or 'none'}. Active mods: {', '.join(active) or 'none'}."


def missing_checkpoint_tables(save_dir: Path, metadata: dict) -> list[str]:
    if "dataframe_dict_members" not in metadata:
        return []  # Older saves did not include a manifest.
    members = metadata["dataframe_dict_members"]
    if not isinstance(members, dict) or not isinstance(members.get("tables"), list):
        # A malformed manifest is not evidence that all checkpoint tables exist.
        return ["invalid table manifest"]
    return [str(name) for name in members["tables"]
            if not isinstance(name, str) or Path(name).name != name
            or not (save_dir / "tables" / f"{name}.parquet").is_file()]


def list_available_saves(config: GameConfig) -> List[Dict[str, Any]]:
    """
    Scans the save directory and returns metadata for each valid save slot.

    The result is sorted by timestamp (newest first) so UIs can display
    the list in the most useful order without any additional sorting.

    Args:
        config: The active game configuration used to resolve the save path.

    Returns:
        A list of dicts, each containing at minimum:
        - 'name': The save slot name (directory basename).
        - 'timestamp': ISO-format creation timestamp string.
        - 'tick': The simulation tick at the time of the save.
    """
    save_root = config.project_root / "user_data" / "saves"
    try:
        candidates = list(save_root.iterdir())
    except FileNotFoundError:
        return []
    except OSError as error:
        logger.warning("Cannot list save slots at %s: %s", save_root, error)
        return []

    saves: List[Dict[str, Any]] = []
    for candidate in candidates:
        if not candidate.is_dir() or candidate.name.startswith("."):
            continue

        meta_file = candidate / "meta.json"
        if not meta_file.is_file():
            continue

        try:
            with open(meta_file, "rb") as f:
                data = orjson.loads(f.read())
            recovered = False
            missing = missing_checkpoint_tables(candidate, data)
            if missing:
                backup = save_backup_path(save_root, candidate.name)
                try:
                    backup_data = orjson.loads((backup / "meta.json").read_bytes())
                    members = backup_data.get("dataframe_dict_members", {})
                    if (isinstance(members, dict) and isinstance(members.get("tables"), list)
                            and not missing_checkpoint_tables(backup, backup_data)
                            and not save_mod_compatibility_error(backup_data, config.active_mods)):
                        data, missing, recovered = backup_data, [], True
                except (OSError, ValueError, TypeError, AttributeError):
                    pass
            summary = _save_summary(candidate.name, data, config.active_mods)
            summary["recovered_from_backup"] = recovered
            if missing:
                summary["load_error"] = f"Save is incomplete: missing checkpoint tables {', '.join(missing)}."
            saves.append(summary)
        except Exception as error:
            logger.warning("Skipping unreadable save metadata at %s: %s", meta_file, error)
            continue

    # Match the loader's recovery rule when the primary generation is absent
    # or was left without metadata.
    for backup in candidates:
        if not (backup.name.startswith(".") and backup.name.endswith(".backup")):
            continue
        save_name = backup.name[1 : -len(".backup")]
        try:
            validate_save_name(save_name)
            if not backup.is_dir() or any(row["name"] == save_name for row in saves):
                continue
            with open(backup / "meta.json", "rb") as f:
                data = orjson.loads(f.read())
            summary = _save_summary(save_name, data, config.active_mods)
            summary["recovered_from_backup"] = True
            missing = missing_checkpoint_tables(backup, data)
            if missing:
                # A backup-only slot must meet the same completeness check as a primary.
                summary["load_error"] = f"Save is incomplete: missing checkpoint tables {', '.join(missing)}."
            saves.append(summary)
        except Exception as error:
            logger.warning("Skipping unreadable save backup at %s: %s", backup, error)
            continue

    return sorted(saves, key=lambda s: s["timestamp"], reverse=True)


def _save_summary(name: str, data: Dict[str, Any], active_mods) -> Dict[str, Any]:
    globals_data = data.get("globals") if isinstance(data.get("globals"), dict) else {}
    time_data = data.get("time") if isinstance(data.get("time"), dict) else {}
    return {
        "name": name,
        "load_error": save_mod_compatibility_error(data, active_mods),
        # Optional metadata from older saves must remain sortable and displayable.
        "timestamp": str(data.get("timestamp") or ""),
        # Robustly handle saves that predate the 'globals' key.
        "tick": globals_data.get("tick", 0),
        "country_tag": globals_data.get("player_tag", ""),
        "scenario": globals_data.get("scenario_name", ""),
        "game_time": time_data.get("date_str", ""),
    }
