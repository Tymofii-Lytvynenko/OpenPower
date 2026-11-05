"""Apply covert resource production changes to authoritative economy tables."""

from __future__ import annotations

import math

import polars as pl
from src.shared.region_control import region_controlled_by_country


def resource_production_total(state, country_tag: str, resource_id: str) -> float:
    """Return current production for a country/resource using regional data first."""
    country = _tag(country_tag)
    resource = _resource(resource_id)
    if not country or not resource:
        return 0.0

    regional, indexes, has_regional_rows = _controlled_regional_rows(state, country, resource)
    if regional is not None and has_regional_rows:
        if not indexes:
            return 0.0
        rows = regional.to_dicts()
        total = math.fsum(_nonnegative(rows[index].get("domestic_production")) for index in indexes)
        return total

    national = getattr(state, "tables", {}).get("domestic_production")
    if national is None or not {"country_id", "game_resource_id", "domestic_production"}.issubset(national.columns):
        return 0.0
    rows = national.filter(
        (pl.col("country_id").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase() == country)
        & (pl.col("game_resource_id").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_lowercase() == resource)
    )
    return math.fsum(_nonnegative(value) for value in rows.get_column("domestic_production").to_list())


# The REFERENCE server allocates national production changes by each controlled region's share.
def apply_resource_production_delta(
    state,
    country_tag: str,
    resource_id: str,
    delta: float,
) -> float:
    """Distribute a production change across the country's existing source rows."""
    country = _tag(country_tag)
    resource = _resource(resource_id)
    requested_delta = _finite(delta)
    if not country or not resource or requested_delta == 0.0:
        return 0.0

    regional, indexes, has_regional_rows = _controlled_regional_rows(state, country, resource)
    if regional is not None and has_regional_rows:
        if not indexes:
            return 0.0
        rows = regional.to_dicts()
        values = [_nonnegative(rows[index].get("domestic_production")) for index in indexes]
        total = math.fsum(values)
        if total <= 0.0:
            return 0.0
        actual_delta = 0.0
        for index, value in zip(indexes, values, strict=True):
            share = value / total
            updated = value + requested_delta * share
            if requested_delta < 0.0:
                updated = max(1.0, updated)
            rows[index]["domestic_production"] = updated
            actual_delta += updated - value
        state.update_table(
            "regional_production",
            pl.DataFrame(rows, schema=regional.schema, strict=False),
        )
        _adjust_national_total(state, country, resource, actual_delta)
        return actual_delta

    return _adjust_national_only(state, country, resource, requested_delta)


def _controlled_regional_rows(state, country: str, resource: str):
    regional = getattr(state, "tables", {}).get("regional_production")
    required = {"country_id", "region_id", "game_resource_id", "domestic_production"}
    if regional is None or not required.issubset(regional.columns):
        return None, [], False

    rows = regional.to_dicts()
    source_indexes = [
        index
        for index, row in enumerate(rows)
        if _tag(row.get("country_id")) == country and _resource(row.get("game_resource_id")) == resource
    ]
    if not source_indexes:
        return regional, [], False
    indexes = source_indexes

    regions = getattr(state, "tables", {}).get("regions")
    if regions is not None and "id" in regions.columns:
        region_by_id = {
            region_id: row
            for row in regions.to_dicts()
            if (region_id := _region_id(row.get("id"))) is not None
        }
        indexes = [
            index
            for index in indexes
            if (region := region_by_id.get(_region_id(rows[index].get("region_id")))) is not None
            and region_controlled_by_country(state, region, country)
        ]

    # Existing rows with no controlled regions must not silently fall back to national totals.
    return regional, indexes, True


def _adjust_national_total(state, country: str, resource: str, delta: float) -> None:
    national = getattr(state, "tables", {}).get("domestic_production")
    if national is None or not {"country_id", "game_resource_id", "domestic_production"}.issubset(national.columns):
        return
    rows = national.to_dicts()
    indexes = [
        index for index, row in enumerate(rows)
        if _tag(row.get("country_id")) == country and _resource(row.get("game_resource_id")) == resource
    ]
    if not indexes:
        return
    total = math.fsum(_nonnegative(rows[index].get("domestic_production")) for index in indexes)
    if total <= 0.0:
        return
    remaining = _finite(delta)
    for position, index in enumerate(indexes):
        value = _nonnegative(rows[index].get("domestic_production"))
        share = value / total
        change = remaining if position == len(indexes) - 1 else delta * share
        remaining -= change
        rows[index]["domestic_production"] = max(0.0, value + change)
    state.update_table("domestic_production", pl.DataFrame(rows, schema=national.schema, strict=False))


def _adjust_national_only(state, country: str, resource: str, delta: float) -> float:
    national = getattr(state, "tables", {}).get("domestic_production")
    required = {"country_id", "game_resource_id", "domestic_production"}
    if national is None or not required.issubset(national.columns):
        return 0.0

    rows = national.to_dicts()
    indexes = [
        index for index, row in enumerate(rows)
        if _tag(row.get("country_id")) == country and _resource(row.get("game_resource_id")) == resource
    ]
    if not indexes:
        return 0.0
    total = math.fsum(_nonnegative(rows[index].get("domestic_production")) for index in indexes)
    if total <= 0.0:
        return 0.0

    requested_delta = _finite(delta)
    actual_delta = 0.0
    for index in indexes:
        value = _nonnegative(rows[index].get("domestic_production"))
        share = value / total
        updated = value + requested_delta * share
        if requested_delta < 0.0:
            updated = max(1.0, updated)
        rows[index]["domestic_production"] = updated
        actual_delta += updated - value
    state.update_table("domestic_production", pl.DataFrame(rows, schema=national.schema, strict=False))
    return actual_delta


def _tag(value) -> str:
    return str(value or "").strip().upper()


def _resource(value) -> str:
    return str(value or "").strip().lower()


def _region_id(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _nonnegative(value) -> float:
    return max(0.0, _finite(value))


def _finite(value) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return result if math.isfinite(result) else 0.0
