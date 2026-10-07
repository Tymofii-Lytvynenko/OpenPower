"""Treaty-aware authorization for a unit's final destination."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import polars as pl

from src.shared.treaties import normalize_country_tags


@dataclass(frozen=True)
class MovementAccessContext:
    """Precomputed rights for one country during a route search."""

    owner: str
    countries_at_war: frozenset[str]
    stationing_rights: frozenset[str]
    transit_rights: frozenset[str]

    def can_station(self, target_region: dict[str, Any]) -> bool:
        territory_owner = _tag(target_region.get("owner"))
        return (
            not territory_owner
            or territory_owner == self.owner
            or territory_owner in self.countries_at_war
            or territory_owner in self.stationing_rights
        )

    def can_transit(self, target_region: dict[str, Any]) -> bool:
        territory_owner = _tag(target_region.get("owner"))
        return (
            not territory_owner
            or territory_owner == self.owner
            or territory_owner in self.countries_at_war
            or territory_owner in self.stationing_rights
            or territory_owner in self.transit_rights
        )


class MovementAccessPolicy:
    """Keeps treaty rights out of movement interpolation and rendering code."""

    def for_country(self, state, unit_owner: str) -> MovementAccessContext:
        owner = _tag(unit_owner)
        at_war: set[str] = set()
        wars = state.tables.get("countries_wars")
        if wars is not None and not wars.is_empty():
            for war in wars.iter_rows(named=True):
                if str(war.get("status") or "active").lower() != "active":
                    continue
                side_a = set(normalize_country_tags(war.get("side_a")))
                side_b = set(normalize_country_tags(war.get("side_b")))
                if owner in side_a:
                    at_war.update(side_b)
                if owner in side_b:
                    at_war.update(side_a)

        stationing: set[str] = set()
        transit: set[str] = set()
        effects = state.tables.get("treaty_effects")
        if effects is not None and not effects.is_empty():
            for row in effects.iter_rows(named=True):
                if _tag(row.get("country_id")) != owner:
                    continue
                effect = str(row.get("effect") or "")
                if effect not in {"stationing_rights", "transit_rights"}:
                    continue
                tags = self._detail_tags(row.get("detail"))
                if effect == "stationing_rights":
                    stationing.update(tags)
                else:
                    transit.update(tags)

        return MovementAccessContext(
            owner=owner,
            countries_at_war=frozenset(at_war),
            stationing_rights=frozenset(stationing),
            transit_rights=frozenset(transit),
        )

    def can_station(self, state, unit_owner: str, target_region: dict[str, Any]) -> bool:
        return self.for_country(state, unit_owner).can_station(target_region)

    def can_transit(self, state, unit_owner: str, target_region: dict[str, Any]) -> bool:
        return self.for_country(state, unit_owner).can_transit(target_region)

    def _detail_tags(self, value: Any) -> tuple[str, ...]:
        try:
            parsed = json.loads(str(value or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return ()
        return normalize_country_tags(parsed)


def _tag(value: Any) -> str:
    return str(value or "").strip().upper()
