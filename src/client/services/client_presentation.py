"""Resolve presentation extensions attached by the application composition root."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def contribution_for(state: Any, key: str) -> Any:
    """Return a presentation contribution or explain which mod API is missing."""

    contributions = getattr(state, "client_presentation", None)
    if not isinstance(contributions, Mapping):
        raise RuntimeError(
            "This UI operation requires a ClientGameStateView with mod presentation data."
        )
    try:
        return contributions[key]
    except KeyError as exc:
        raise RuntimeError(
            f"No active mod provides client presentation contribution '{key}'."
        ) from exc
