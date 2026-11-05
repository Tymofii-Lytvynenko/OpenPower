"""Build bounded intelligence estimates from current world tables."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import polars as pl

from modules.base.systems.military.capability_catalog import canonical_role


@dataclass(frozen=True, slots=True)
class IntelligenceSnapshotServices:
    normalize_tag: Callable[[Any], str]
    finite_number: Callable[[Any], float]
    table_value_by_key: Callable[[Any, str, Any, str, Any], Any]
    metric_value: Callable[..., Any]
    country_population: Callable[[Any, str], float]


def build_intelligence_snapshot(
    state: Any,
    target: Mapping[str, Any],
    mission_type: str,
    confidence: float,
    confidence_factors: Mapping[str, Any] | None,
    population_by_country: pl.DataFrame | None,
    *,
    services: IntelligenceSnapshotServices,
) -> dict[str, Any]:
    country_id = services.normalize_tag(target.get("id"))
    if mission_type == "military_espionage":
        return _military_snapshot(
            state, country_id, confidence, confidence_factors
        )
    return _government_snapshot(
        state,
        target,
        country_id,
        confidence,
        population_by_country,
        services,
    )


def target_regional_telecom_capacity(
    state: Any,
    cell: Mapping[str, Any],
    target: Mapping[str, Any],
    *,
    services: IntelligenceSnapshotServices,
) -> float:
    region_id = 0
    route_frame = state.tables.get("covert_cell_routes")
    if route_frame is not None and {
        "cell_id",
        "destination_region_id",
        "status",
    }.issubset(route_frame.columns):
        route_match = route_frame.filter(
            (pl.col("cell_id").cast(pl.Utf8, strict=False).fill_null("") == str(cell.get("id") or ""))
            & pl.col("status")
            .cast(pl.Utf8, strict=False)
            .fill_null("")
            .is_in(["arrived", "in_transit"])
        ).select(pl.col("destination_region_id").cast(pl.Int64, strict=False)).head(1)
        if not route_match.is_empty():
            region_id = int(route_match.item() or 0)
    if region_id <= 0:
        governments = state.tables.get("country_governments")
        if governments is not None and {
            "country_id",
            "capital_region_id",
        }.issubset(governments.columns):
            capital = services.table_value_by_key(
                governments,
                "country_id",
                services.normalize_tag(target.get("id")),
                "capital_region_id",
                0,
            )
            region_id = int(capital or 0)

    regions = state.tables.get("regions")
    if regions is None or "id" not in regions.columns:
        return 1.0
    column = "telecom_capacity" if "telecom_capacity" in regions.columns else "communications"
    if column not in regions.columns:
        return 1.0
    region_value = None
    if region_id > 0:
        match = regions.filter(
            pl.col("id").cast(pl.Int64, strict=False) == region_id
        ).select(pl.col(column).cast(pl.Float64, strict=False)).head(1)
        if not match.is_empty():
            region_value = match.item()
    if region_value is None:
        target_id = services.normalize_tag(target.get("id"))
        ownership_filters = [
            pl.col(name)
            .cast(pl.Utf8, strict=False)
            .fill_null("")
            .str.strip_chars()
            .str.to_uppercase()
            == target_id
            for name in ("owner", "controller")
            if name in regions.columns
        ]
        if ownership_filters:
            match = (
                regions.with_columns(
                    pl.col("id").cast(pl.Int64, strict=False).alias("_region_sort")
                )
                .filter(pl.any_horizontal(ownership_filters))
                .sort("_region_sort")
                .select(pl.col(column).cast(pl.Float64, strict=False))
                .head(1)
            )
            if not match.is_empty():
                region_value = match.item()
    return (
        1.0
        if region_value is None
        else max(0.0, min(1.0, services.finite_number(region_value)))
    )


def _military_snapshot(
    state: Any,
    country_id: str,
    confidence: float,
    confidence_factors: Mapping[str, Any] | None,
) -> dict[str, Any]:
    units = state.tables.get("units")
    owned = pl.DataFrame()
    if units is not None and "owner" in units.columns:
        owned = units.filter(
            pl.col("owner")
            .cast(pl.Utf8, strict=False)
            .fill_null("")
            .str.strip_chars()
            .str.to_uppercase()
            == country_id
        )
    unit_count = owned.height
    if "readiness_status" in owned.columns:
        ready_count = owned.filter(
            pl.col("readiness_status")
            .cast(pl.Utf8, strict=False)
            .fill_null("")
            .is_in(["", "ready"])
        ).height
    else:
        ready_count = unit_count

    role_counts = _unit_role_counts(state, owned, unit_count)
    tracks = state.tables.get("research_tracks")
    production = state.tables.get("production_orders")
    weapon_quantity = _strategic_weapon_quantity(state, country_id)
    return {
        "unit_count_estimate": unit_count,
        "ready_count_estimate": ready_count,
        "unit_role_count_estimates": dict(sorted(role_counts.items())),
        "research_track_count": 0
        if tracks is None
        else tracks.filter(pl.col("country_id") == country_id).height,
        "active_production_orders": 0
        if production is None
        else production.filter(
            (pl.col("country_id") == country_id)
            & pl.col("status").is_in(["queued", "paused"])
        ).height,
        "strategic_weapon_quantity_estimate": weapon_quantity,
        "confidence": confidence,
        "confidence_factors": dict(sorted((confidence_factors or {}).items())),
    }


def _unit_role_counts(
    state: Any, owned: pl.DataFrame, unit_count: int
) -> dict[str, int]:
    role_counts: dict[str, int] = {}
    if not unit_count or "design_id" not in owned.columns:
        return role_counts

    role_units = owned.select(
        pl.col("design_id")
        .cast(pl.Utf8, strict=False)
        .fill_null("")
        .alias("_design_id"),
        pl.col("unit_type")
        .cast(pl.Utf8, strict=False)
        .fill_null("")
        .alias("_unit_type")
        if "unit_type" in owned.columns
        else pl.lit("").alias("_unit_type"),
    )
    design_table = state.tables.get("unit_designs")
    if design_table is not None and {"id", "class_name"}.issubset(
        design_table.columns
    ):
        design_roles = (
            design_table.select(
                pl.col("id")
                .cast(pl.Utf8, strict=False)
                .fill_null("")
                .alias("_design_id"),
                pl.col("class_name")
                .cast(pl.Utf8, strict=False)
                .fill_null("")
                .alias("_class_name"),
            )
            .unique(subset=["_design_id"], keep="last", maintain_order=True)
        )
        role_units = role_units.join(
            design_roles, on="_design_id", how="left", maintain_order="left"
        )
        class_name = pl.col("_class_name")
    else:
        role_units = role_units.with_columns(pl.lit("").alias("_class_name"))
        class_name = pl.col("_class_name")

    role_units = role_units.with_columns(
        pl.when(class_name != "")
        .then(class_name)
        .when(pl.col("_unit_type") != "")
        .then(pl.col("_unit_type"))
        .otherwise(pl.lit("generic_unit"))
        .alias("_role_name")
    )
    # Canonicalize only the small distinct role vocabulary, then aggregate all units in Polars.
    distinct_roles = role_units.get_column("_role_name").unique().to_list()
    role_lookup = pl.DataFrame(
        {
            "_role_name": distinct_roles,
            "_role": [canonical_role(role) for role in distinct_roles],
        }
    )
    grouped_roles = (
        role_units.join(role_lookup, on="_role_name", how="left")
        .group_by("_role")
        .agg(pl.len().alias("count"))
    )
    return {
        role: int(count)
        for role, count in grouped_roles.select("_role", "count").iter_rows()
    }


def _strategic_weapon_quantity(state: Any, country_id: str) -> int:
    weapons = state.tables.get("strategic_weapons")
    if weapons is None or not {"country_id", "quantity"}.issubset(weapons.columns):
        return 0
    quantity = weapons.filter(
        pl.col("country_id").cast(pl.Utf8, strict=False).fill_null("")
        == country_id
    ).select(pl.col("quantity").cast(pl.Int64, strict=False).fill_null(0).sum())
    return int(quantity.item() or 0)


def _government_snapshot(
    state: Any,
    target: Mapping[str, Any],
    country_id: str,
    confidence: float,
    population_by_country: pl.DataFrame | None,
    services: IntelligenceSnapshotServices,
) -> dict[str, Any]:
    governments = state.tables.get("country_governments")
    government_type = services.table_value_by_key(
        governments, "country_id", country_id, "government_type", "unknown"
    )
    laws = state.tables.get("country_laws")
    law_ids = []
    if laws is not None and {"country_id", "law_id"}.issubset(laws.columns):
        law_ids = [
            str(value or "")
            for value in laws.filter(pl.col("country_id") == country_id)
            .get_column("law_id")
            .head(10)
            .to_list()
        ]
    population = (
        services.metric_value(
            population_by_country, "population", country_id=country_id
        )
        if population_by_country is not None
        else services.country_population(state, country_id)
    )
    return {
        "government_estimate": str(government_type or "unknown"),
        "economic_output_estimate": max(0.0, services.finite_number(target.get("gdp"))),
        "population_estimate": max(0.0, population),
        "budget_research_ratio_estimate": min(
            1.0, max(0.0, services.finite_number(target.get("budget_research_ratio")))
        ),
        "law_ids": law_ids,
        "confidence": confidence,
    }
