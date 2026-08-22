"""Persists military control separately from political ownership."""

from __future__ import annotations

from typing import Any

import polars as pl

from src.shared.events import EventNewHour
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase


OCCUPATION_SCHEMA = {
    "region_id": pl.Int32,
    "controller_country_id": pl.Utf8,
    "garrison_strength": pl.Int64,
    "resistance": pl.Float64,
    "occupation_status": pl.Utf8,
    "started_at_minute": pl.Int64,
    "updated_at_minute": pl.Int64,
    "contested": pl.Boolean,
}


class OccupationSystem(ISystem):
    """Maintains occupation rows after combat has selected a controller."""

    access = SystemAccess(
        reads=frozenset({"regions", "units", "occupations", "countries_wars"}),
        writes=frozenset({"regions", "occupations"}),
        phase=SystemPhase.POST_PROCESS,
    )

    @property
    def id(self) -> str:
        return "base.occupation"

    @property
    def dependencies(self) -> list[str]:
        return ["base.combat"]

    def update(self, state: GameState, delta_time: float) -> None:
        regions = state.tables.get("regions")
        units = state.tables.get("units")
        if regions is None or units is None:
            self._update_table_if_changed(
                state,
                "occupations",
                pl.DataFrame(schema=OCCUPATION_SCHEMA),
            )
            return
        existing = state.tables.get("occupations")
        if existing is not None and not any(isinstance(event, EventNewHour) for event in state.events):
            return
        rows = existing.to_dicts() if existing is not None and not existing.is_empty() else []
        by_region = {int(row.get("region_id") or 0): row for row in rows}
        unit_rows = units.to_dicts()
        now = int(state.time.total_minutes)
        for region in regions.to_dicts():
            region_id = int(region.get("id") or 0)
            controller = str(region.get("controller") or "").strip().upper()
            owner = str(region.get("owner") or "").strip().upper()
            if not controller or not owner or controller == owner:
                continue
            garrison = sum(
                max(0, int(unit.get("strength") or 0))
                for unit in unit_rows
                if int(unit.get("current_region_id") or 0) == region_id
                and str(unit.get("owner") or "").strip().upper() == controller
                and not bool(unit.get("is_moving"))
            )
            previous = by_region.get(region_id, {})
            by_region[region_id] = {
                "region_id": region_id,
                "controller_country_id": controller,
                "garrison_strength": garrison,
                "resistance": 0.0,
                "occupation_status": "active" if garrison > 0 else "contested",
                "started_at_minute": int(
                    previous.get("started_at_minute")
                    if previous.get("started_at_minute") is not None
                    else now
                ),
                "updated_at_minute": now,
                "contested": garrison <= 0,
            }
        frame = (
            pl.DataFrame(list(by_region.values()), schema=OCCUPATION_SCHEMA)
            if by_region
            else pl.DataFrame(schema=OCCUPATION_SCHEMA)
        )
        self._update_table_if_changed(state, "occupations", frame)

    def _update_table_if_changed(self, state: GameState, name: str, frame: pl.DataFrame) -> bool:
        current = state.tables.get(name)
        if current is not None and current.equals(frame):
            return False
        state.update_table(name, frame)
        return True
