"""
Save file discovery utility.

This module provides a read-only helper for listing available save files.
It is safe to import from any layer (client, server, engine, modules) because
it only performs filesystem I/O and has no dependencies on simulation state.
"""

import orjson
from pathlib import Path
from typing import Any, Dict, List

from src.shared.config import GameConfig


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
        if not candidate.is_dir():
            continue

        meta_file = candidate / "meta.json"
        if not meta_file.exists():
            continue

        try:
            with open(meta_file, "rb") as f:
                data = orjson.loads(f.read())
            saves.append({
                "name": candidate.name,
                "timestamp": data.get("timestamp", ""),
                # Robustly handle saves that predate the 'globals' key
                "tick": data.get("globals", {}).get("tick", 0),
            })
        except Exception:
            # Corrupt or locked file — skip silently to keep the UI functional
            continue

    return sorted(saves, key=lambda s: s["timestamp"], reverse=True)
