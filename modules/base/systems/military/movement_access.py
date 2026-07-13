"""Treaty-aware authorization for a unit's final destination."""

from __future__ import annotations

import json
from typing import Any

import polars as pl

from src.shared.treaties import normalize_country_tags


class MovementAccessPolicy:
    """Keeps treaty rights out of movement interpolation and rendering code."""

    def can_station(self, state, unit_owner: str, target_region: dict[str, Any]) -> bool:
        territory_owner = self._tag(target_region.get("owner"))
        owner = self._tag(unit_owner)
        if not territory_owner or territory_owner == owner:
            return True
        if self._at_war(state.tables.get("countries_wars"), owner, territory_owner):
            return True
        return self._has_stationing_right(state.tables.get("treaty_effects"), owner, territory_owner)

    def can_transit(self, state, unit_owner: str, target_region: dict[str, Any]) -> bool:
        """Allow passage through a region without treating it as a stationing destination."""
        territory_owner = self._tag(target_region.get("owner"))
        owner = self._tag(unit_owner)
        if not territory_owner or territory_owner == owner:
            return True
        if self._at_war(state.tables.get("countries_wars"), owner, territory_owner):
            return True
        effects = state.tables.get("treaty_effects")
        return self._has_stationing_right(effects, owner, territory_owner) or self._has_transit_right(effects, owner, territory_owner)

    def _has_transit_right(self, effects: pl.DataFrame | None, owner: str, territory_owner: str) -> bool:
        if effects is None or effects.is_empty():
            return False
        for row in effects.to_dicts():
            if self._tag(row.get("country_id")) == owner and str(row.get("effect") or "") == "transit_rights":
                if territory_owner in self._detail_tags(row.get("detail")):
                    return True
        return False

    def _has_stationing_right(self, effects: pl.DataFrame | None, owner: str, territory_owner: str) -> bool:
        if effects is None or effects.is_empty():
            return False
        for row in effects.to_dicts():
            if self._tag(row.get("country_id")) != owner or str(row.get("effect") or "") != "stationing_rights":
                continue
            if territory_owner in self._detail_tags(row.get("detail")):
                return True
        return False

    def _at_war(self, wars: pl.DataFrame | None, left: str, right: str) -> bool:
        if wars is None or wars.is_empty():
            return False
        for war in wars.to_dicts():
            if str(war.get("status") or "active").lower() != "active":
                continue
            side_a = set(normalize_country_tags(war.get("side_a")))
            side_b = set(normalize_country_tags(war.get("side_b")))
            if (left in side_a and right in side_b) or (left in side_b and right in side_a):
                return True
        return False

    def _detail_tags(self, value: Any) -> tuple[str, ...]:
        try:
            parsed = json.loads(str(value or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return ()
        return normalize_country_tags(parsed)

    def _tag(self, value: Any) -> str:
        return str(value or "").strip().upper()
