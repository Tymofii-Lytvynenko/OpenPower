"""Index active wars and resolve their participating countries."""

from dataclasses import dataclass
from typing import Any

import polars as pl


@dataclass(frozen=True, slots=True)
class WarRecord:
    war_id: str
    side_a: frozenset[str]
    side_b: frozenset[str]
    status: str


@dataclass(frozen=True, slots=True)
class ConflictContext:
    war_id: str
    side_a_members: frozenset[str]
    side_b_members: frozenset[str]
    side_a_tags: frozenset[str]
    side_b_tags: frozenset[str]
    roles: dict[str, str] | None = None
    bases: dict[str, str] | None = None


class WarIndex:
    """Resolves active wartime relationships without coupling combat to table shape."""

    def __init__(self, active_wars: list[WarRecord]):
        self._active_wars = active_wars

    @classmethod
    def from_table(cls, wars: pl.DataFrame | None) -> "WarIndex":
        if wars is None or wars.is_empty():
            return cls([])

        records: list[WarRecord] = []
        for index, row in enumerate(wars.to_dicts(), start=1):
            status = str(row.get("status") or "active").lower()
            if status not in {"active", "ongoing", ""}:
                continue

            side_a = cls._normalize_side(row.get("side_a"))
            side_b = cls._normalize_side(row.get("side_b"))
            if not side_a or not side_b:
                continue

            records.append(
                WarRecord(
                    war_id=str(row.get("id") or f"war-{index:03d}"),
                    side_a=frozenset(side_a),
                    side_b=frozenset(side_b),
                    status=status or "active",
                )
            )

        return cls(sorted(records, key=lambda record: record.war_id))

    def active_battle_for_region(self, owners: set[str]) -> ConflictContext | None:
        for war in self._active_wars:
            present_a = frozenset(tag for tag in owners if tag in war.side_a)
            present_b = frozenset(tag for tag in owners if tag in war.side_b)
            if present_a and present_b:
                return ConflictContext(
                    war_id=war.war_id,
                    side_a_members=war.side_a,
                    side_b_members=war.side_b,
                    side_a_tags=present_a,
                    side_b_tags=present_b,
                )
        return None

    def is_hostile(self, left: str | None, right: str | None) -> bool:
        if not left or not right or left == right:
            return False

        for war in self._active_wars:
            if (left in war.side_a and right in war.side_b) or (left in war.side_b and right in war.side_a):
                return True
        return False

    @staticmethod
    def _normalize_side(value: Any) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, list):
            return {str(tag).strip().upper() for tag in value if str(tag).strip()}
        if isinstance(value, tuple):
            return {str(tag).strip().upper() for tag in value if str(tag).strip()}
        if isinstance(value, str):
            return {tag.strip().upper() for tag in value.split(",") if tag.strip()}
        return set()


