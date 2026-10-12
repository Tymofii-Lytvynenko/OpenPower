"""Deterministic production-capacity calculations independent of game state."""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

import polars as pl


DEFAULT_PRODUCTION_COEFFICIENT = 48.0
_DAYS_PER_YEAR = 365.25
_TERMINAL_ORDER_STATES = {"cancelled", "completed", "delivered", "awaiting_deployment"}


def annual_production_capacity(
    national_output: Any,
    economic_health: Any,
    coefficient: Any = DEFAULT_PRODUCTION_COEFFICIENT,
) -> float:
    """Return output × bounded health × configured production coefficient."""

    output = _finite_nonnegative(national_output)
    health = min(1.0, max(0.0, _finite_nonnegative(economic_health)))
    scale = _finite_nonnegative(coefficient)
    return output * health * scale


def annual_production_capacity_frame(
    countries: pl.DataFrame | None,
    coefficient: Any = DEFAULT_PRODUCTION_COEFFICIENT,
) -> pl.DataFrame:
    """Calculate country capacity in Polars for use by the production allocator."""

    schema = {"_country": pl.Utf8, "_annual_capacity": pl.Float64}
    if countries is None or not {"id", "gdp"}.issubset(countries.columns):
        return pl.DataFrame(schema=schema)
    output = _finite_expr("gdp").clip(lower_bound=0.0)
    health = (
        _finite_expr("economic_health").clip(0.0, 1.0)
        if "economic_health" in countries.columns
        else pl.lit(1.0)
    )
    scale = _finite_nonnegative(coefficient)
    return (
        countries.select(
            pl.col("id").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase().alias("_country"),
            (output * health * scale).alias("_annual_capacity"),
        )
        .unique(subset=["_country"], keep="last", maintain_order=True)
    )


def allocate_production_capacity(
    orders: Iterable[dict[str, Any]],
    annual_capacity_by_country: dict[str, float],
    elapsed_year_fraction: float,
    allocation_policy: str = "priority",
) -> list[dict[str, Any]]:
    """Compatibility wrapper for callers that exchange records as dictionaries."""

    rows = list(orders)
    frame = pl.DataFrame(rows, strict=False) if rows else pl.DataFrame()
    return allocate_production_capacity_frame(
        frame, annual_capacity_by_country, elapsed_year_fraction, allocation_policy
    ).to_dicts()


def allocate_production_capacity_frame(
    orders: pl.DataFrame,
    annual_capacity_by_country: Mapping[str, float] | pl.DataFrame,
    elapsed_year_fraction: float,
    allocation_policy: str = "priority",
) -> pl.DataFrame:
    """Allocate production work with table operations while retaining input row order."""

    elapsed = _finite_nonnegative(elapsed_year_fraction)
    proportional = str(allocation_policy or "priority").strip().lower() == "proportional"
    capacity_frame = _capacity_frame(annual_capacity_by_country)
    original_columns = list(orders.columns)
    prepared = orders.with_row_index("_row_order")
    defaults = {
        "id": (pl.Utf8, ""),
        "country_id": (pl.Utf8, ""),
        "priority": (pl.Int64, 1),
        "status": (pl.Utf8, "queued"),
        "work_required": (pl.Float64, 0.0),
        "remaining_work": (pl.Float64, None),
        "progress": (pl.Float64, 0.0),
        "assigned_capacity": (pl.Float64, 0.0),
        "blocking_reason": (pl.Utf8, ""),
        "eta_days": (pl.Int64, 0),
    }
    for column, (dtype, default) in defaults.items():
        if column not in prepared.columns:
            prepared = prepared.with_columns(pl.lit(default, dtype=dtype).alias(column))
    output_columns = list(dict.fromkeys([*original_columns, "remaining_work", "progress", "status", "eta_days", "assigned_capacity", "blocking_reason"]))

    prepared = (
        prepared.with_columns(
            pl.col("country_id").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase().alias("_country"),
            pl.col("id").cast(pl.Utf8, strict=False).fill_null("").alias("_id"),
            pl.col("status").cast(pl.Utf8, strict=False).fill_null("queued").str.strip_chars().str.to_lowercase().alias("_status"),
            pl.col("priority").cast(pl.Int64, strict=False).fill_null(1).clip(lower_bound=1).alias("_priority"),
            _finite_expr("work_required").clip(lower_bound=0.0).alias("_required"),
            _finite_expr("progress").clip(0.0, 1.0).alias("_progress"),
            _finite_expr("remaining_work").clip(lower_bound=0.0).alias("_remaining_input"),
        )
        .join(capacity_frame, on="_country", how="left", maintain_order="left")
        .with_columns(pl.col("_annual_capacity").fill_null(0.0).alias("_annual_capacity"))
        .with_columns(
            pl.when(
                (pl.col("remaining_work").is_null() | (pl.col("_remaining_input") == 0.0))
                & (pl.col("_progress") < 1.0)
            )
            .then(pl.col("_required") * (1.0 - pl.col("_progress")))
            .when(pl.col("_required") > 0.0)
            .then(pl.min_horizontal(pl.col("_required"), pl.col("_remaining_input")))
            .otherwise(0.0)
            .alias("_remaining")
        )
    )

    queued_mask = ~pl.col("_status").is_in(sorted(_TERMINAL_ORDER_STATES | {"paused"}))
    active_mask = (pl.col("_country") != "") & queued_mask
    passive_mask = (pl.col("_country") != "") & ~queued_mask
    active = (
        prepared.filter(active_mask)
        .sort(["_country", "_priority", "_id", "_row_order"], descending=[False, True, False, False])
        .with_columns(
            (pl.col("_annual_capacity") * elapsed).alias("_update_capacity"),
            pl.col("_remaining").sum().over("_country").alias("_total_demand"),
        )
    )
    if proportional:
        active = active.with_columns(
            pl.when((pl.col("_total_demand") > 0.0) & (pl.col("_annual_capacity") > 0.0) & (elapsed > 0.0))
            .then(pl.min_horizontal(pl.lit(1.0), pl.col("_update_capacity") / pl.col("_total_demand")))
            .otherwise(0.0)
            .alias("_allocation_ratio")
        ).with_columns((pl.col("_remaining") * pl.col("_allocation_ratio")).alias("_allocated"))
    else:
        active = active.with_columns(
            (pl.col("_remaining").cum_sum().over("_country") - pl.col("_remaining")).alias("_demand_before")
        ).with_columns(
            pl.min_horizontal(
                pl.col("_remaining"),
                (pl.col("_update_capacity") - pl.col("_demand_before")).clip(lower_bound=0.0),
            ).alias("_allocated")
        )

    active = active.with_columns(
        (pl.col("_remaining") - pl.col("_allocated")).clip(lower_bound=0.0).alias("_remaining_after")
    ).with_columns(
        (pl.col("_remaining_after").cum_sum().over("_country") - pl.col("_remaining_after")).alias("_demand_ahead")
    )
    complete = pl.col("_remaining_after") <= 1e-9
    eta = (
        ((pl.col("_demand_ahead") + pl.col("_remaining_after")) / pl.col("_annual_capacity") * _DAYS_PER_YEAR)
        .ceil()
        .cast(pl.Int64)
        .clip(lower_bound=1)
    )
    active = active.with_columns(
        pl.when(complete).then(0.0).otherwise(pl.col("_remaining_after")).alias("remaining_work"),
        pl.col("_allocated").alias("assigned_capacity"),
        pl.when(pl.col("_required") <= 0.0)
        .then(1.0)
        .otherwise((1.0 - pl.col("_remaining_after") / pl.col("_required")).clip(0.0, 1.0))
        .alias("progress"),
        pl.when((pl.col("_annual_capacity") <= 0.0) & (pl.col("_remaining_after") > 0.0))
        .then(pl.lit("No production capacity is available."))
        .when(pl.lit(not proportional) & (pl.col("_allocated") <= 0.0) & (pl.col("_remaining_after") > 0.0))
        .then(pl.lit("Waiting for higher-priority orders."))
        .otherwise(pl.lit(""))
        .alias("blocking_reason"),
        pl.when(complete).then(pl.lit("completed")).otherwise(pl.lit("queued")).alias("status"),
        pl.when(complete)
        .then(pl.lit(0, dtype=pl.Int64))
        .when(pl.col("_annual_capacity") <= 0.0)
        .then(pl.lit(-1, dtype=pl.Int64))
        .otherwise(eta)
        .alias("eta_days"),
    )
    active = active.select(prepared.columns)

    passive = prepared.filter(passive_mask).with_columns(
        pl.lit(0.0).alias("assigned_capacity"),
        pl.when(pl.col("_status") == "paused")
        .then(pl.lit("Order is paused."))
        .when(pl.col("_status").is_in(["completed", "delivered"]))
        .then(pl.lit(""))
        .otherwise(pl.col("blocking_reason"))
        .alias("blocking_reason"),
    )
    untouched = prepared.filter(pl.col("_country") == "")
    computed_columns = [
        "remaining_work", "progress", "status", "eta_days",
        "assigned_capacity", "blocking_reason",
    ]
    for column in computed_columns:
        dtype = active.schema[column]
        passive = passive.with_columns(pl.col(column).cast(dtype, strict=False).alias(column))
        untouched = untouched.with_columns(pl.col(column).cast(dtype, strict=False).alias(column))
    return (
        pl.concat([active, passive, untouched], how="vertical")
        .sort("_row_order")
        .select(output_columns)
    )


def initialize_production_order_work(
    orders: pl.DataFrame,
    designs: pl.DataFrame | None,
) -> pl.DataFrame:
    """Fill missing work estimates through a keyed design-cost join."""

    if designs is not None and {"id", "cost"}.issubset(designs.columns):
        design_costs = (
            designs.select(
                pl.col("id").cast(pl.Utf8, strict=False).fill_null("").alias("design_id"),
                _finite_expr("cost").clip(lower_bound=0.0).alias("_design_cost"),
            )
            .unique(subset=["design_id"], keep="last", maintain_order=True)
        )
    else:
        design_costs = pl.DataFrame(schema={"design_id": pl.Utf8, "_design_cost": pl.Float64})
    if "design_id" in orders.columns:
        orders = orders.with_columns(pl.col("design_id").cast(pl.Utf8, strict=False).fill_null(""))
        orders = orders.join(
            design_costs,
            on="design_id",
            how="left",
            maintain_order="left",
        )
    else:
        orders = orders.with_columns(pl.lit(0.0).alias("_design_cost"))
    orders = orders.with_columns(pl.col("_design_cost").fill_null(0.0))

    required = _finite_expr("work_required")
    existing_cost = _finite_expr("unit_cost")
    resolved_cost = pl.when(existing_cost != 0.0).then(existing_cost).otherwise(pl.col("_design_cost"))
    quantity = pl.col("quantity").cast(pl.Int64, strict=False).fill_null(0).clip(lower_bound=0)
    progress = _finite_expr("progress").clip(0.0, 1.0)
    needs_work = required <= 0.0
    return (
        orders.with_columns(
            pl.when(needs_work).then(resolved_cost).otherwise(pl.col("unit_cost")).alias("unit_cost"),
            pl.when(needs_work).then(resolved_cost * quantity).otherwise(pl.col("work_required")).alias("work_required"),
            pl.when(needs_work)
            .then(resolved_cost * quantity * (1.0 - progress))
            .otherwise(pl.col("remaining_work"))
            .alias("remaining_work"),
        )
        .drop("_design_cost")
    )


def _capacity_frame(capacities: Mapping[str, float] | pl.DataFrame) -> pl.DataFrame:
    if isinstance(capacities, pl.DataFrame):
        if "_country" in capacities.columns:
            country_column = "_country"
        elif "country_id" in capacities.columns:
            country_column = "country_id"
        else:
            return pl.DataFrame(schema={"_country": pl.Utf8, "_annual_capacity": pl.Float64})
        value_column = "_annual_capacity" if "_annual_capacity" in capacities.columns else "annual_capacity"
        if value_column not in capacities.columns:
            return pl.DataFrame(schema={"_country": pl.Utf8, "_annual_capacity": pl.Float64})
        return (
            capacities.select(
                pl.col(country_column).cast(pl.Utf8, strict=False).fill_null("").alias("_country"),
                _finite_expr(value_column).clip(lower_bound=0.0).alias("_annual_capacity"),
            )
            .unique(subset=["_country"], keep="last", maintain_order=True)
        )
    if not capacities:
        return pl.DataFrame(schema={"_country": pl.Utf8, "_annual_capacity": pl.Float64})
    return pl.DataFrame({
        "_country": [str(country) for country in capacities],
        "_annual_capacity": [_finite_nonnegative(value) for value in capacities.values()],
    })


def _finite_expr(column: str) -> pl.Expr:
    value = pl.col(column).cast(pl.Float64, strict=False)
    return pl.when(value.is_finite()).then(value).otherwise(0.0)


def _tag(value: Any) -> str:
    return str(value or "").strip().upper()


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _number(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return result if math.isfinite(result) else 0.0


def _finite_nonnegative(value: Any) -> float:
    return max(0.0, _number(value))
