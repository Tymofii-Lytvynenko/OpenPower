"""Vectorized movement updates for units that share a safe route profile."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

import numpy as np
import polars as pl

from modules.base.systems.military.movement_access import MovementAccessContext
from modules.base.systems.military.movement_constants import NO_TARGET_REGION
from modules.base.systems.military.movement_domains import (
    domain_route_compatible,
    unit_domain,
)
from modules.base.systems.military.war_policy import hostile_country_pairs
from src.shared.state import GameState


@dataclass(frozen=True)
class _FinalLegBatchProfile:
    owner: str
    target_region_id: int
    unit: dict[str, Any]


class _MovementAccessProvider(Protocol):
    def for_country(self, state: GameState, unit_owner: str) -> MovementAccessContext: ...


class MovementBatchUpdater:
    """Apply vectorized movement progress when contact checks are unnecessary."""

    def __init__(self, access_policy: _MovementAccessProvider) -> None:
        self._access_policy = access_policy

    def try_update_uncontested(
        self,
        state: GameState,
        units: pl.DataFrame,
        current_minute: int,
        final_leg_updater: Callable[
            [GameState, pl.DataFrame, int, pl.DataFrame], pl.DataFrame | None
        ],
    ) -> pl.DataFrame | None:
        if not self._can_attempt_uncontested_update(state, units):
            return None

        route_table = state.tables.get("unit_movement_routes")
        if route_table is not None and not route_table.is_empty():
            return final_leg_updater(state, units, current_minute, route_table)

        return self._update_unrouted_progress(units, current_minute)

    def _can_attempt_uncontested_update(self, state: GameState, units: pl.DataFrame) -> bool:
        required = {
            "id", "is_moving", "target_region_id", "departed_at_minute",
            "arrival_at_minute", "movement_progress",
        }
        if not required.issubset(units.columns):
            return False

        wars = state.tables.get("countries_wars")
        return wars is None or wars.is_empty() or not hostile_country_pairs(wars.to_dicts())

    def _update_unrouted_progress(
        self,
        units: pl.DataFrame,
        current_minute: int,
    ) -> pl.DataFrame | None:
        moving = units.get_column("is_moving").fill_null(False)
        targets = units.get_column("target_region_id").fill_null(NO_TARGET_REGION)
        active_mask = moving & targets.gt(0)
        arrivals = units.get_column("arrival_at_minute").fill_null(current_minute)
        if (active_mask & arrivals.le(current_minute)).any():
            return None

        departed = pl.col("departed_at_minute").fill_null(current_minute)
        duration = (
            pl.col("arrival_at_minute").fill_null(current_minute) - departed
        ).clip(lower_bound=1)
        progress = (
            (pl.lit(current_minute) - departed).cast(pl.Float64)
            / duration.cast(pl.Float64)
        ).clip(0.0, 1.0)
        all_units_active = moving.all() and targets.gt(0).all()
        if all_units_active:
            return self._update_all_active_progress(units, current_minute, arrivals)
        return self._update_mixed_progress(units, progress)

    def _update_all_active_progress(
        self,
        units: pl.DataFrame,
        current_minute: int,
        arrivals: pl.Series,
    ) -> pl.DataFrame:
        # NumPy avoids building and evaluating a Polars expression tree for this hot numeric-only path.
        departed_values = units.get_column("departed_at_minute").fill_null(current_minute).to_numpy()
        arrival_values = arrivals.to_numpy()
        duration_values = np.maximum(arrival_values - departed_values, 1)
        progress_values = np.clip(
            (current_minute - departed_values) / duration_values,
            0.0,
            1.0,
        )
        return units.with_columns(
            pl.Series("movement_progress", progress_values, dtype=pl.Float64)
        )

    def _update_mixed_progress(
        self,
        units: pl.DataFrame,
        progress: pl.Expr,
    ) -> pl.DataFrame:
        active_expression = (
            pl.col("is_moving").fill_null(False)
            & pl.col("target_region_id").fill_null(NO_TARGET_REGION).gt(0)
        )
        return units.with_columns(
            pl.when(active_expression)
            .then(progress)
            .otherwise(pl.lit(0.0))
            .alias("movement_progress"),
            active_expression.alias("is_moving"),
        )

    def try_update_final_leg(
        self,
        state: GameState,
        units: pl.DataFrame,
        current_minute: int,
        routes: pl.DataFrame,
    ) -> pl.DataFrame | None:
        if not self._has_final_leg_batch_shape(units, routes):
            return None

        profile = self._final_leg_profile(units, routes)
        if profile is None:
            return None

        regions = state.tables.get("regions")
        if regions is None or "id" not in regions.columns:
            return None
        target_rows = regions.filter(pl.col("id") == profile.target_region_id).head(1).to_dicts()
        if not target_rows:
            return None

        target_region = target_rows[0]
        access_context = self._access_policy.for_country(state, profile.owner)
        if not access_context.can_station(target_region):
            return None
        domain_allowed, _ = domain_route_compatible(
            unit_domain(profile.unit),
            target_region,
            True,
            False,
            regions.to_dicts(),
        )
        if not domain_allowed:
            return None

        return self._apply_final_leg_progress(units, routes, current_minute, state)

    def _has_final_leg_batch_shape(self, units: pl.DataFrame, routes: pl.DataFrame) -> bool:
        if not self._has_required_batch_columns(units, routes):
            return False
        if units.is_empty() or routes.height != units.height:
            return False
        if not self._all_units_are_moving(units):
            return False
        if not self._route_ids_match_units(units, routes):
            return False
        return True

    def _has_required_batch_columns(self, units: pl.DataFrame, routes: pl.DataFrame) -> bool:
        required_units = {
            "id", "owner", "unit_domain", "unit_type", "is_moving", "engagement_mode",
            "target_region_id", "target_latitude", "target_longitude", "current_region_id",
            "latitude", "longitude", "source_region_id", "source_latitude", "source_longitude",
            "departed_at_minute", "arrival_at_minute", "movement_progress",
        }
        required_routes = {
            "unit_id", "owner_country_id", "destination_region_id", "route_region_ids",
            "route_index", "has_custom_destination", "is_naval_invasion", "status",
            "rejection_reason", "updated_at_minute",
        }
        return required_units.issubset(units.columns) and required_routes.issubset(routes.columns)

    def _all_units_are_moving(self, units: pl.DataFrame) -> bool:
        return (
            units.get_column("is_moving").fill_null(False).all()
            and units.get_column("target_region_id").fill_null(NO_TARGET_REGION).min() > 0
            and not units.get_column("engagement_mode").fill_null("").str.strip_chars().ne("").any()
        )

    def _route_ids_match_units(self, units: pl.DataFrame, routes: pl.DataFrame) -> bool:
        if units.get_column("id").n_unique() != units.height:
            return False
        if routes.get_column("unit_id").n_unique() != routes.height:
            return False
        return set(units.get_column("id").to_list()) == set(routes.get_column("unit_id").to_list())

    def _final_leg_profile(
        self,
        units: pl.DataFrame,
        routes: pl.DataFrame,
    ) -> _FinalLegBatchProfile | None:
        route_profile = self._final_route_profile(routes)
        if route_profile is None:
            return None

        unit_profile = self._final_unit_profile(units, route_profile)
        if unit_profile is None:
            return None

        owner = str(unit_profile.get("owner") or "").strip().upper()
        target_region_id = int(unit_profile.get("target_region_id") or 0)
        return _FinalLegBatchProfile(owner, target_region_id, unit_profile)

    def _final_route_profile(self, routes: pl.DataFrame) -> dict[str, Any] | None:
        route_profile_columns = [
            "owner_country_id", "destination_region_id", "route_index",
            "has_custom_destination", "is_naval_invasion", "status",
        ]
        route_profiles = routes.select(route_profile_columns).unique()
        if route_profiles.height != 1 or routes.get_column("route_region_ids").n_unique() != 1:
            return None

        route_profile = route_profiles.row(0, named=True)
        route_regions = routes.get_column("route_region_ids")[0]
        route_regions = [] if route_regions is None else [int(value) for value in route_regions]
        if not self._is_final_standard_route(route_profile, route_regions):
            return None
        return route_profile

    def _is_final_standard_route(
        self,
        route_profile: dict[str, Any],
        route_regions: list[int],
    ) -> bool:
        is_final_segment = int(route_profile.get("route_index") or 0) == len(route_regions) - 1
        reaches_destination = bool(route_regions) and (
            route_regions[-1] == int(route_profile.get("destination_region_id") or 0)
        )
        is_standard_route = not bool(route_profile.get("has_custom_destination")) and not bool(
            route_profile.get("is_naval_invasion")
        )
        is_in_transit = str(route_profile.get("status") or "") == "in_transit"
        return all((bool(route_regions), is_final_segment, reaches_destination, is_standard_route, is_in_transit))

    def _final_unit_profile(
        self,
        units: pl.DataFrame,
        route_profile: dict[str, Any],
    ) -> dict[str, Any] | None:
        unit_profiles = units.select(["owner", "target_region_id", "unit_domain", "unit_type"]).unique()
        if unit_profiles.height != 1:
            return None

        unit_profile = unit_profiles.row(0, named=True)
        owner = str(unit_profile.get("owner") or "").strip().upper()
        route_owner = str(route_profile.get("owner_country_id") or "").strip().upper()
        profile_matches_route = all(
            (
                bool(owner),
                owner == route_owner,
                int(unit_profile.get("target_region_id") or 0)
                == int(route_profile.get("destination_region_id") or 0),
            )
        )
        if not profile_matches_route:
            return None
        return unit_profile

    def _apply_final_leg_progress(
        self,
        units: pl.DataFrame,
        routes: pl.DataFrame,
        current_minute: int,
        state: GameState,
    ) -> pl.DataFrame:
        due = pl.col("arrival_at_minute").fill_null(current_minute).le(current_minute)
        departed = pl.col("departed_at_minute").fill_null(current_minute)
        arrival = pl.col("arrival_at_minute").fill_null(current_minute)
        duration = (arrival - departed).clip(lower_bound=1)
        progress = ((pl.lit(current_minute) - departed).cast(pl.Float64) / duration.cast(pl.Float64)).clip(0.0, 1.0)
        updates = [
            pl.when(due).then(pl.col("target_region_id")).otherwise(pl.col("current_region_id")).cast(pl.Int32).alias("current_region_id"),
            pl.when(due).then(pl.col("target_latitude")).otherwise(pl.col("latitude")).alias("latitude"),
            pl.when(due).then(pl.col("target_longitude")).otherwise(pl.col("longitude")).alias("longitude"),
            pl.when(due).then(pl.col("target_region_id")).otherwise(pl.col("source_region_id")).cast(pl.Int32).alias("source_region_id"),
            pl.when(due).then(pl.col("target_latitude")).otherwise(pl.col("source_latitude")).alias("source_latitude"),
            pl.when(due).then(pl.col("target_longitude")).otherwise(pl.col("source_longitude")).alias("source_longitude"),
            pl.when(due).then(pl.lit(NO_TARGET_REGION)).otherwise(pl.col("target_region_id")).cast(pl.Int32).alias("target_region_id"),
            pl.when(due).then(pl.col("target_latitude")).otherwise(pl.col("target_latitude")).alias("target_latitude"),
            pl.when(due).then(pl.col("target_longitude")).otherwise(pl.col("target_longitude")).alias("target_longitude"),
            pl.when(due).then(pl.lit(current_minute)).otherwise(departed).cast(pl.Int64).alias("departed_at_minute"),
            pl.when(due).then(pl.lit(current_minute)).otherwise(arrival).cast(pl.Int64).alias("arrival_at_minute"),
            pl.when(due).then(pl.lit(0.0)).otherwise(progress).alias("movement_progress"),
            (~due).alias("is_moving"),
        ]
        if "unit_lifecycle" in units.columns:
            updates.append(
                pl.when(due)
                .then(pl.when(pl.col("unit_lifecycle") == "battle_retreating").then(pl.lit("battle_regrouping")).otherwise(pl.lit("available")))
                .otherwise(pl.col("unit_lifecycle"))
                .alias("unit_lifecycle")
            )
        updates.append(pl.when(due).then(pl.lit("")).otherwise(pl.col("engagement_mode")).alias("engagement_mode"))
        updated_units = units.with_columns(updates)

        due_ids = units.filter(due).get_column("id").to_list()
        arrived = pl.col("unit_id").is_in(due_ids)
        updated_routes = routes.with_columns(
            pl.when(arrived).then(pl.lit("arrived")).otherwise(pl.col("status")).alias("status"),
            pl.when(arrived).then(pl.lit("")).otherwise(pl.col("rejection_reason")).alias("rejection_reason"),
            pl.lit(current_minute).cast(pl.Int64).alias("updated_at_minute"),
        )
        if not routes.equals(updated_routes):
            state.update_table("unit_movement_routes", updated_routes)
        return updated_units
