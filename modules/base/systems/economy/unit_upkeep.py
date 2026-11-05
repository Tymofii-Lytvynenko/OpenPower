"""Shared calculations for the unit-level contributions to military upkeep."""
from __future__ import annotations

import math
import polars as pl


BASE_UNIT_COST = 500_000.0
_READINESS_STATUSES = ("parked", "ready", "fortified")
_MAX_DESIGN_MAINTENANCE = 1_000_000_000_000.0


def readiness_upkeep_by_country(state, factors: dict[str, float]) -> pl.DataFrame | None:
    """Aggregate readiness weighting and design maintenance for the budget."""
    units = state.tables.get("units")
    if units is None or "owner" not in units.columns or "strength" not in units.columns:
        return None
    strength = pl.col("strength").cast(pl.Float64)
    unit_lf = units.lazy().with_columns(
        pl.col("owner").cast(pl.Utf8).alias("id"),
        # Nonfinite strength must not contaminate the country budget aggregate.
        pl.when(strength.is_finite()).then(strength.clip(lower_bound=0.0))
        .otherwise(0.0).alias("_maintenance_strength"),
    )
    if "readiness_status" in units.columns and factors:
        # Match the per-unit estimate when a stored status has surrounding whitespace.
        status = pl.col("readiness_status").cast(pl.Utf8).str.strip_chars().str.to_lowercase()
        factor_expr = pl.lit(1.0)
        for readiness, factor in factors.items():
            factor_expr = pl.when(status == readiness).then(pl.lit(factor)).otherwise(factor_expr)
        unit_lf = unit_lf.with_columns(factor_expr.alias("_readiness_factor"))
    else:
        unit_lf = unit_lf.with_columns(pl.lit(1.0).alias("_readiness_factor"))

    maintenance_lf = None
    designs = state.tables.get("unit_designs")
    if designs is not None and "id" in designs.columns and "maintenance_cost" in designs.columns and "design_id" in units.columns:
        cost = pl.col("maintenance_cost").cast(pl.Float64)
        design_lf = designs.lazy().select(
            pl.col("id").cast(pl.Utf8).alias("_maintenance_design_id"),
            # Nonfinite costs otherwise contaminate the budget or become the maximum cost.
            pl.when(cost.is_finite()).then(cost.clip(0.0, _MAX_DESIGN_MAINTENANCE))
            .otherwise(0.0).alias("_maintenance_per_unit"),
        )
        maintenance_lf = (
            unit_lf.join(design_lf, left_on="design_id", right_on="_maintenance_design_id", how="left")
            .group_by("id")
            .agg((pl.col("_maintenance_strength") * pl.col("_maintenance_per_unit").fill_null(0.0)).sum().alias("_design_maintenance"))
        )
    readiness_lf = unit_lf.group_by("id").agg(
        pl.col("_maintenance_strength").sum().alias("_total_unit_strength"),
        (pl.col("_maintenance_strength") * pl.col("_readiness_factor")).sum().alias("_weighted_unit_strength"),
    )
    if maintenance_lf is not None:
        readiness_lf = readiness_lf.join(maintenance_lf, on="id", how="left")
    else:
        readiness_lf = readiness_lf.with_columns(pl.lit(0.0).alias("_design_maintenance"))
    return readiness_lf.with_columns(
        pl.when(pl.col("_total_unit_strength") > 0.0)
        .then(pl.col("_weighted_unit_strength") / pl.col("_total_unit_strength"))
        .otherwise(1.0)
        .alias("_readiness_upkeep_factor")
    ).select("id", "_readiness_upkeep_factor", "_design_maintenance").collect()


def readiness_upkeep_factors(state) -> dict[str, float]:
    """Return the same bounded readiness multipliers used by the budget system."""
    configured = state.globals.get("military_readiness_upkeep_factors", {})
    if not isinstance(configured, dict):
        return {}

    factors: dict[str, float] = {}
    for status in _READINESS_STATUSES:
        if status not in configured:
            continue
        try:
            value = float(configured[status])
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(value):
            factors[status] = max(0.0, min(2.0, value))
    return factors


def unit_upkeep_by_id(state) -> dict[str, float]:
    """Allocate the current annual military budget formula across owned unit rows."""
    units = state.tables.get("units")
    countries = state.tables.get("countries")
    if units is None or countries is None or units.is_empty() or countries.is_empty():
        return {}
    if not {"id", "owner", "strength"}.issubset(units.columns):
        return {}
    if not {"id", "military_count"}.issubset(countries.columns):
        return {}

    countries_by_id = {str(row.get("id") or ""): row for row in countries.to_dicts()}
    designs = state.tables.get("unit_designs")
    designs_by_id = {} if designs is None else {
        str(row.get("id") or ""): row for row in designs.to_dicts()
    }
    factors = readiness_upkeep_factors(state)
    unit_rows = units.to_dicts()

    # The national budget applies one strength-weighted readiness factor to the
    # country's total military count, which can differ from the unit-row sum.
    # Allocate that exact national base expense across the current unit rows.
    by_owner: dict[str, list[tuple[str, float, float, float]]] = {}
    for unit in unit_rows:
        unit_id = str(unit.get("id") or "")
        owner = str(unit.get("owner") or "")
        country = countries_by_id.get(owner)
        if not unit_id or country is None:
            continue

        strength = max(0.0, _finite_number(unit.get("strength"), 0.0))
        status = str(unit.get("readiness_status") or "").strip().lower()
        readiness_factor = factors.get(status, 1.0)
        design = designs_by_id.get(str(unit.get("design_id") or ""), {})
        maintenance = max(
            0.0,
            min(_MAX_DESIGN_MAINTENANCE, _finite_number(design.get("maintenance_cost"), 0.0)),
        )
        by_owner.setdefault(owner, []).append((unit_id, strength, readiness_factor, maintenance))

    result: dict[str, float] = {}
    for owner, records in by_owner.items():
        total_strength = sum(strength for _, strength, _, _ in records)
        if total_strength <= 0.0:
            for unit_id, _, _, _ in records:
                result[unit_id] = 0.0
            continue

        weighted_readiness = sum(
            strength * factor for _, strength, factor, _ in records
        ) / total_strength
        country = countries_by_id[owner]
        military_count = max(0.0, _finite_number(country.get("military_count"), 0.0))
        human_development = _finite_number(country.get("human_dev"), 0.5)
        base_expense = military_count * BASE_UNIT_COST * human_development * weighted_readiness
        for unit_id, strength, _, maintenance in records:
            expense = base_expense * strength / total_strength + strength * maintenance
            if math.isfinite(expense):
                result[unit_id] = max(0.0, expense)
    return result


def _finite_number(value, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default
