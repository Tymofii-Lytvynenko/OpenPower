from __future__ import annotations

import math
from typing import Any

import polars as pl

from src.engine.interfaces import ISystem
from src.server.state import GameState
from src.shared.actions import ActionBuildUnit, ActionMoveUnit


UNIT_TABLE = "units"
NO_TARGET_REGION = -1
DEFAULT_UNIT_TYPE = "army"
DEFAULT_MOVE_MINUTES = 1440

UNIT_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.Utf8,
    "owner": pl.Utf8,
    "unit_type": pl.Utf8,
    "strength": pl.Int64,
    "current_region_id": pl.Int32,
    "source_region_id": pl.Int32,
    "target_region_id": pl.Int32,
    "departed_at_minute": pl.Int64,
    "arrival_at_minute": pl.Int64,
    "movement_progress": pl.Float64,
    "is_moving": pl.Boolean,
}


class MovementDurationPolicy:
    """Estimates direct movement duration from source and target region centers."""

    def estimate_minutes(
        self,
        regions: pl.DataFrame,
        source_region_id: int,
        target_region_id: int,
    ) -> int:
        centers = self._region_centers(regions)
        source = centers.get(source_region_id)
        target = centers.get(target_region_id)

        if source is None or target is None:
            return DEFAULT_MOVE_MINUTES

        max_x = max((x for x, _ in centers.values()), default=1.0)
        max_y = max((y for _, y in centers.values()), default=1.0)
        width = max(max_x, 1.0)
        height = max(max_y, 1.0)

        dx = abs(target[0] - source[0])
        dy = abs(target[1] - source[1])
        normalized_distance = math.sqrt((dx / width) ** 2 + (dy / height) ** 2)

        return int(max(360, min(10080, 720 + normalized_distance * 7200)))

    def _region_centers(self, regions: pl.DataFrame) -> dict[int, tuple[float, float]]:
        required = {"id", "center_x", "center_y"}
        if regions.is_empty() or not required.issubset(set(regions.columns)):
            return {}

        return {
            int(row["id"]): (float(row["center_x"]), float(row["center_y"]))
            for row in regions.select(["id", "center_x", "center_y"]).iter_rows(named=True)
            if row["id"] is not None
        }


class UnitFactory:
    """Creates normalized unit records without coupling callers to table details."""

    def create(
        self,
        unit_id: str,
        owner: str,
        unit_type: str,
        strength: int,
        region_id: int,
        current_minute: int,
    ) -> dict[str, Any]:
        safe_strength = max(1, int(strength))
        return {
            "id": unit_id,
            "owner": owner,
            "unit_type": unit_type or DEFAULT_UNIT_TYPE,
            "strength": safe_strength,
            "current_region_id": int(region_id),
            "source_region_id": int(region_id),
            "target_region_id": NO_TARGET_REGION,
            "departed_at_minute": int(current_minute),
            "arrival_at_minute": int(current_minute),
            "movement_progress": 0.0,
            "is_moving": False,
        }


class MilitarySystem(ISystem):
    def __init__(self):
        self._missing_columns = set()
        self._duration_policy = MovementDurationPolicy()
        self._unit_factory = UnitFactory()

    @property
    def id(self) -> str:
        return "base.military"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.population", "base.economy"]

    def update(self, state: GameState, delta_time: float) -> None:
        units = self._ensure_units_table(state)
        units = self._process_build_actions(state, units)
        units = self._process_move_actions(state, units)
        units = self._update_unit_movements(units, state.time.total_minutes)
        state.update_table(UNIT_TABLE, units)

        tick = state.globals.get("tick", 0)
        if tick % 7 == 0:
            self._update_manpower(state)

    def _ensure_units_table(self, state: GameState) -> pl.DataFrame:
        if UNIT_TABLE not in state.tables or state.tables[UNIT_TABLE].is_empty():
            units = self._create_initial_units(state)
            state.update_table(UNIT_TABLE, units)
            return units

        return self._normalize_units_table(state.get_table(UNIT_TABLE))

    def _create_initial_units(self, state: GameState) -> pl.DataFrame:
        if "regions" not in state.tables or "countries" not in state.tables:
            return self._empty_units()

        regions = state.get_table("regions")
        countries = state.get_table("countries")
        if regions.is_empty() or countries.is_empty() or "id" not in countries.columns:
            return self._empty_units()

        home_regions = self._home_regions_by_country(regions)
        country_strength = self._country_strengths(countries)
        current_minute = state.time.total_minutes
        rows = []

        for country_tag in countries["id"].to_list():
            clean_tag = str(country_tag)
            if clean_tag not in home_regions:
                continue

            rows.append(
                self._unit_factory.create(
                    unit_id=f"{clean_tag}-{DEFAULT_UNIT_TYPE}-001",
                    owner=clean_tag,
                    unit_type=DEFAULT_UNIT_TYPE,
                    strength=country_strength.get(clean_tag, 1),
                    region_id=home_regions[clean_tag],
                    current_minute=current_minute,
                )
            )

        return self._units_from_rows(rows)

    def _home_regions_by_country(self, regions: pl.DataFrame) -> dict[str, int]:
        required = {"id", "owner"}
        if regions.is_empty() or not required.issubset(set(regions.columns)):
            return {}

        score_columns = [col for col in ("pop_15_64", "area_km2") if col in regions.columns]
        selected: dict[str, tuple[int, float]] = {}

        for row in regions.iter_rows(named=True):
            owner = row.get("owner")
            region_id = row.get("id")
            if not owner or owner == "None" or region_id is None:
                continue

            score = 0.0
            for column in score_columns:
                value = row.get(column)
                if value is not None:
                    score += float(value)

            owner_key = str(owner)
            current = selected.get(owner_key)
            if current is None or score > current[1]:
                selected[owner_key] = (int(region_id), score)

        return {owner: region_id for owner, (region_id, _) in selected.items()}

    def _country_strengths(self, countries: pl.DataFrame) -> dict[str, int]:
        if "military_count" not in countries.columns:
            return {}

        return {
            str(row["id"]): max(1, int(row["military_count"] or 0))
            for row in countries.select(["id", "military_count"]).iter_rows(named=True)
            if row["id"] is not None
        }

    def _process_build_actions(self, state: GameState, units: pl.DataFrame) -> pl.DataFrame:
        actions_to_process = [a for a in state.current_actions if isinstance(a, ActionBuildUnit)]
        if not actions_to_process:
            return units

        countries = self._ensure_country_columns(state.get_table("countries"))
        home_regions = self._home_regions_by_country(state.get_table("regions"))
        rows = units.to_dicts()

        for action in actions_to_process:
            cost = 1_000_000 * action.count
            countries = countries.with_columns(
                pl.when(pl.col("id") == action.country_tag)
                .then(pl.col("military_count") + action.count)
                .otherwise(pl.col("military_count"))
                .alias("military_count"),
                pl.when(pl.col("id") == action.country_tag)
                .then(pl.col("money_reserves") - cost)
                .otherwise(pl.col("money_reserves"))
                .alias("money_reserves"),
            )

            home_region_id = home_regions.get(action.country_tag)
            if home_region_id is None:
                continue

            rows.append(
                self._unit_factory.create(
                    unit_id=self._next_unit_id(rows, action.country_tag, action.unit_type),
                    owner=action.country_tag,
                    unit_type=action.unit_type,
                    strength=action.count,
                    region_id=home_region_id,
                    current_minute=state.time.total_minutes,
                )
            )

        state.update_table("countries", countries)
        return self._units_from_rows(rows)

    def _process_move_actions(self, state: GameState, units: pl.DataFrame) -> pl.DataFrame:
        move_actions = [a for a in state.current_actions if isinstance(a, ActionMoveUnit)]
        if not move_actions or units.is_empty() or "regions" not in state.tables:
            return units

        valid_regions = set(state.get_table("regions")["id"].to_list())
        action_by_unit = {
            action.unit_id: action
            for action in move_actions
            if action.target_region_id in valid_regions
        }
        if not action_by_unit:
            return units

        rows = []
        now = int(state.time.total_minutes)
        regions = state.get_table("regions")

        for row in units.to_dicts():
            action = action_by_unit.get(str(row["id"]))
            if action is None:
                rows.append(row)
                continue

            source_region_id = int(row["current_region_id"])
            target_region_id = int(action.target_region_id)
            if source_region_id == target_region_id:
                row["target_region_id"] = NO_TARGET_REGION
                row["source_region_id"] = source_region_id
                row["departed_at_minute"] = now
                row["arrival_at_minute"] = now
                row["movement_progress"] = 0.0
                row["is_moving"] = False
                rows.append(row)
                continue

            duration = self._duration_policy.estimate_minutes(
                regions,
                source_region_id,
                target_region_id,
            )
            row["source_region_id"] = source_region_id
            row["target_region_id"] = target_region_id
            row["departed_at_minute"] = now
            row["arrival_at_minute"] = now + duration
            row["movement_progress"] = 0.0
            row["is_moving"] = True
            rows.append(row)

        return self._units_from_rows(rows)

    def _update_unit_movements(self, units: pl.DataFrame, current_minute: int) -> pl.DataFrame:
        if units.is_empty():
            return units

        rows = []
        for row in units.to_dicts():
            target_region_id = int(row["target_region_id"])
            if target_region_id <= 0 or not bool(row["is_moving"]):
                row["movement_progress"] = 0.0
                row["is_moving"] = False
                rows.append(row)
                continue

            departed_at = int(row["departed_at_minute"])
            arrival_at = int(row["arrival_at_minute"])
            duration = max(1, arrival_at - departed_at)
            progress = max(0.0, min(1.0, (current_minute - departed_at) / duration))

            if progress >= 1.0:
                row["current_region_id"] = target_region_id
                row["source_region_id"] = target_region_id
                row["target_region_id"] = NO_TARGET_REGION
                row["departed_at_minute"] = current_minute
                row["arrival_at_minute"] = current_minute
                row["movement_progress"] = 0.0
                row["is_moving"] = False
            else:
                row["movement_progress"] = progress
                row["is_moving"] = True

            rows.append(row)

        return self._units_from_rows(rows)

    def _ensure_country_columns(self, countries: pl.DataFrame) -> pl.DataFrame:
        if "military_count" not in countries.columns:
            if "military_count" not in self._missing_columns:
                print(f"[{self.id}] Column 'military_count' not found in 'countries'. Defaulting to 0.")
                self._missing_columns.add("military_count")
            countries = countries.with_columns(pl.lit(0).alias("military_count"))

        if "money_reserves" not in countries.columns:
            if "money_reserves" not in self._missing_columns:
                print(f"[{self.id}] Column 'money_reserves' not found in 'countries'. Defaulting to 0.")
                self._missing_columns.add("money_reserves")
            countries = countries.with_columns(pl.lit(0.0).alias("money_reserves"))

        return countries

    def _next_unit_id(self, unit_rows: list[dict[str, Any]], country_tag: str, unit_type: str) -> str:
        clean_unit_type = unit_type or DEFAULT_UNIT_TYPE
        prefix = f"{country_tag}-{clean_unit_type}"
        existing_ids = {str(row["id"]) for row in unit_rows}
        index = 1

        while True:
            unit_id = f"{prefix}-{index:03d}"
            if unit_id not in existing_ids:
                return unit_id
            index += 1

    def _normalize_units_table(self, units: pl.DataFrame) -> pl.DataFrame:
        defaults: dict[str, Any] = {
            "id": "",
            "owner": "",
            "unit_type": DEFAULT_UNIT_TYPE,
            "strength": 1,
            "current_region_id": 0,
            "source_region_id": 0,
            "target_region_id": NO_TARGET_REGION,
            "departed_at_minute": 0,
            "arrival_at_minute": 0,
            "movement_progress": 0.0,
            "is_moving": False,
        }

        for column, default_value in defaults.items():
            if column not in units.columns:
                units = units.with_columns(pl.lit(default_value).alias(column))

        return units.select([pl.col(column).cast(dtype) for column, dtype in UNIT_SCHEMA.items()])

    def _units_from_rows(self, rows: list[dict[str, Any]]) -> pl.DataFrame:
        if not rows:
            return self._empty_units()

        return pl.DataFrame(rows, schema=UNIT_SCHEMA)

    def _empty_units(self) -> pl.DataFrame:
        return pl.DataFrame(schema=UNIT_SCHEMA)

    def _update_manpower(self, state: GameState):
        regions = state.get_table("regions")

        if regions.is_empty() or "pop_15_64" not in regions.columns:
            return

        regions.group_by("owner").agg(pl.col("pop_15_64").sum().alias("total_core_manpower"))
