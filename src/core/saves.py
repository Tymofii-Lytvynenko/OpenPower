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
    if not save_root.exists():
        return []

    saves: List[Dict[str, Any]] = []
    for candidate in save_root.iterdir():
        if not candidate.is_dir() or candidate.name.startswith("."):
            continue

        meta_file = candidate / "meta.json"
        if not meta_file.exists():
            continue

        try:
            with open(meta_file, "rb") as f:
                data = orjson.loads(f.read())
            saves.append(_save_summary(candidate.name, data))
        except Exception as error:
            logger.warning("Skipping unreadable save metadata at %s: %s", meta_file, error)
            continue

    # If a process stopped between the two directory renames, expose the intact
    # prior generation as its normal slot until a later save replaces it.
    for backup in save_root.glob(".*.backup"):
        save_name = backup.name[1 : -len(".backup")]
        try:
            validate_save_name(save_name)
            if not backup.is_dir() or (save_root / save_name).exists():
                continue
            with open(backup / "meta.json", "rb") as f:
                data = orjson.loads(f.read())
            saves.append(_save_summary(save_name, data))
        except Exception as error:
            logger.warning("Skipping unreadable save backup at %s: %s", backup, error)
            continue

    return sorted(saves, key=lambda s: s["timestamp"], reverse=True)


def _save_summary(name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": name,
        "timestamp": data.get("timestamp", ""),
        # Robustly handle saves that predate the 'globals' key.
        "tick": data.get("globals", {}).get("tick", 0),
    }
