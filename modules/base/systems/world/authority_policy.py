"""Shared authority rules for commands that target a national government."""

from __future__ import annotations

from typing import Any


TRUSTED_SYSTEM_ACTORS = frozenset({"SERVER", "AI", "AI_SYSTEM"})
LOCAL_CLIENT_ACTORS = frozenset({"LOCAL_ADMIN", "LOCAL_PLAYER"})


def player_controls_country(state: Any, player_id: Any, country_id: Any) -> bool:
    actor = str(player_id or "").strip()
    country = _tag(country_id)
    mapping = state.globals.get("player_country_map", {})
    if isinstance(mapping, dict) and _tag(mapping.get(actor)) == country:
        return True
    if _tag(actor) in LOCAL_CLIENT_ACTORS and _tag(state.globals.get("player_tag")) == country:
        return True
    return _tag(actor) == country or _tag(actor) in TRUSTED_SYSTEM_ACTORS


def _tag(value: Any) -> str:
    return str(value or "").strip().upper()
