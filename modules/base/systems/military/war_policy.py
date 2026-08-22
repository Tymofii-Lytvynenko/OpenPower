"""War-side relationship policy used by tactical military systems."""

from __future__ import annotations

from typing import Any, Iterable

from src.shared.treaties import normalize_country_tags


def hostile_country_pairs(war_rows: Iterable[dict[str, Any]]) -> set[frozenset[str]]:
    """Build a reusable index of countries on opposite sides of active wars."""
    pairs: set[frozenset[str]] = set()
    for war in war_rows:
        status = str(war.get("status") or "active").strip().lower()
        if status not in {"", "active", "ongoing"}:
            continue
        side_a = normalize_country_tags(war.get("side_a"))
        side_b = normalize_country_tags(war.get("side_b"))
        pairs.update(
            frozenset((left, right))
            for left in side_a
            for right in side_b
            if left != right
        )
    return pairs


def countries_are_hostile(war_rows: Iterable[dict[str, Any]], left: str, right: str) -> bool:
    """Check whether two country tags occupy opposite sides of an active war."""
    left_tag, right_tag = _tag(left), _tag(right)
    if not left_tag or left_tag == right_tag:
        return False
    return frozenset((left_tag, right_tag)) in hostile_country_pairs(war_rows)


def _tag(value: Any) -> str:
    return str(value or "").strip().upper()
