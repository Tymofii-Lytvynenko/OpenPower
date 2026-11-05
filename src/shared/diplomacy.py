"""Shared diplomatic-state queries used by views and authoritative policies."""

from __future__ import annotations

from typing import Any


def countries_at_war(state: Any, left_country: Any, right_country: Any) -> bool:
    """Return whether two countries are on opposite sides of an active war."""

    left = _tag(left_country)
    right = _tag(right_country)
    wars = state.tables.get("countries_wars")
    if not left or not right or left == right or wars is None:
        return False
    if not {"side_a", "side_b"}.issubset(wars.columns):
        return False

    for war in wars.iter_rows(named=True):
        if str(war.get("status") or "active").strip().casefold() != "active":
            continue
        side_a = {_tag(country) for country in (war.get("side_a") or ())}
        side_b = {_tag(country) for country in (war.get("side_b") or ())}
        if (left in side_a and right in side_b) or (right in side_a and left in side_b):
            return True
    return False


def _tag(value: Any) -> str:
    return str(value or "").strip().upper()
