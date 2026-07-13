from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import polars as pl

from src.core.ai_framework import AITableContext, scheduled_countries


COUNTRY_DEFAULTS: dict[str, tuple[pl.DataType, Any]] = {
    "gdp": (pl.Float64, 0.0),
    "money_reserves": (pl.Float64, 0.0),
    "total_annual_revenue": (pl.Float64, 0.0),
    "total_annual_expense": (pl.Float64, 0.0),
    "human_dev": (pl.Float64, 0.5),
    "corruption": (pl.Float64, 0.5),
    "stability": (pl.Float64, 0.5),
    "military_count": (pl.Float64, 0.0),
    "research_capacity": (pl.Float64, 0.0),
    "budget_research_ratio": (pl.Float64, 0.0),
    "personal_income_tax_rate": (pl.Float64, 0.2),
}


def with_defaults(
    frame: pl.LazyFrame,
    defaults: Mapping[str, tuple[pl.DataType, Any]],
) -> pl.LazyFrame:
    schema = frame.collect_schema()
    expressions: list[pl.Expr] = []
    for name, (dtype, value) in defaults.items():
        if name in schema:
            expressions.append(pl.col(name).cast(dtype, strict=False).fill_null(value).alias(name))
        else:
            expressions.append(pl.lit(value, dtype=dtype).alias(name))
    return frame.with_columns(expressions) if expressions else frame


def country_frame(context: AITableContext, cadence_days: int) -> pl.LazyFrame:
    countries = context.table("countries")
    if countries is None:
        return pl.DataFrame(schema={"country_id": pl.Utf8}).lazy()
    schema = set(countries.collect_schema().names())
    if "corruption" not in schema and "corruption_index" in schema:
        countries = countries.with_columns(
            pl.col("corruption_index").cast(pl.Float64, strict=False).alias("corruption")
        )
    countries = with_defaults(countries, COUNTRY_DEFAULTS).with_columns(
        pl.max_horizontal(
            pl.col("research_capacity"),
            pl.col("gdp") * pl.col("budget_research_ratio"),
        ).alias("research_capacity")
    )
    return scheduled_countries(countries, context, cadence_days)


def relation_matrix(context: AITableContext) -> pl.LazyFrame:
    relations = context.table("countries_relations")
    if relations is None:
        return pl.DataFrame(
            schema={"source_country": pl.Utf8, "target_country": pl.Utf8, "relation": pl.Float64}
        ).lazy()
    schema = set(relations.collect_schema().names())
    source = "source" if "source" in schema else "source_country_id" if "source_country_id" in schema else ""
    target = "target" if "target" in schema else "target_country_id" if "target_country_id" in schema else ""
    value = "value" if "value" in schema else "relation" if "relation" in schema else ""
    if not source or not target or not value:
        return pl.DataFrame(
            schema={"source_country": pl.Utf8, "target_country": pl.Utf8, "relation": pl.Float64}
        ).lazy()

    normalized = relations.select(
        pl.col(source).cast(pl.Utf8).str.to_uppercase().alias("source_country"),
        pl.col(target).cast(pl.Utf8).str.to_uppercase().alias("target_country"),
        pl.col(value).cast(pl.Float64, strict=False).fill_null(0.0).alias("relation"),
    )
    return (
        normalized.filter(pl.col("source_country") != pl.col("target_country"))
        .group_by(["source_country", "target_country"])
        .agg(pl.col("relation").mean())
    )


def country_strength(context: AITableContext) -> pl.LazyFrame:
    countries = context.table("countries")
    if countries is None:
        return pl.DataFrame(schema={"country_id": pl.Utf8, "military_strength": pl.Float64}).lazy()
    countries = with_defaults(countries, {"military_count": (pl.Float64, 0.0)}).select(
        pl.col("id").cast(pl.Utf8).str.to_uppercase().alias("country_id"),
        pl.col("military_count").clip(lower_bound=0.0).alias("reported_strength"),
    )

    units = context.table("units")
    if units is None:
        return countries.select(
            "country_id",
            pl.col("reported_strength").alias("military_strength"),
        )
    schema = set(units.collect_schema().names())
    if not {"owner", "strength"}.issubset(schema):
        return countries.select(
            "country_id",
            pl.col("reported_strength").alias("military_strength"),
        )

    active = (
        units.select(
            pl.col("owner").cast(pl.Utf8).str.to_uppercase().alias("country_id"),
            pl.col("strength").cast(pl.Float64, strict=False).fill_null(0.0).clip(lower_bound=0.0),
        )
        .group_by("country_id")
        .agg(pl.col("strength").sum().alias("unit_strength"))
    )
    return (
        countries.join(active, on="country_id", how="left")
        .with_columns(pl.col("unit_strength").fill_null(0.0))
        .select(
            "country_id",
            pl.max_horizontal("reported_strength", "unit_strength").alias("military_strength"),
        )
    )


def active_war_pairs(context: AITableContext) -> pl.LazyFrame:
    wars = context.table("countries_wars")
    empty = pl.DataFrame(
        schema={
            "war_id": pl.Utf8,
            "source_country": pl.Utf8,
            "target_country": pl.Utf8,
            "source_side": pl.Utf8,
            "source_is_leader": pl.Boolean,
            "created_at": pl.Utf8,
        }
    ).lazy()
    if wars is None:
        return empty
    schema = set(wars.collect_schema().names())
    if not {"id", "side_a", "side_b"}.issubset(schema):
        return empty

    selected = wars
    if "status" in schema:
        selected = selected.filter(pl.col("status").fill_null("active").str.to_lowercase() == "active")
    if "created_at" not in schema:
        selected = selected.with_columns(pl.lit("").alias("created_at"))
    if "leader_a" not in schema:
        selected = selected.with_columns(pl.col("side_a").list.first().alias("leader_a"))
    if "leader_b" not in schema:
        selected = selected.with_columns(pl.col("side_b").list.first().alias("leader_b"))
    pairs = (
        selected.select(
            pl.col("id").cast(pl.Utf8).alias("war_id"),
            pl.col("side_a"),
            pl.col("side_b"),
            pl.col("leader_a").cast(pl.Utf8).str.to_uppercase(),
            pl.col("leader_b").cast(pl.Utf8).str.to_uppercase(),
            pl.col("created_at").cast(pl.Utf8, strict=False).fill_null(""),
        )
        .explode("side_a")
        .explode("side_b")
        .filter(pl.col("side_a").is_not_null() & pl.col("side_b").is_not_null())
    )
    forward = pairs.select(
        "war_id",
        pl.col("side_a").cast(pl.Utf8).str.to_uppercase().alias("source_country"),
        pl.col("side_b").cast(pl.Utf8).str.to_uppercase().alias("target_country"),
        pl.lit("a").alias("source_side"),
        (pl.col("side_a").cast(pl.Utf8).str.to_uppercase() == pl.col("leader_a"))
        .alias("source_is_leader"),
        "created_at",
    )
    reverse = pairs.select(
        "war_id",
        pl.col("side_b").cast(pl.Utf8).str.to_uppercase().alias("source_country"),
        pl.col("side_a").cast(pl.Utf8).str.to_uppercase().alias("target_country"),
        pl.lit("b").alias("source_side"),
        (pl.col("side_b").cast(pl.Utf8).str.to_uppercase() == pl.col("leader_b"))
        .alias("source_is_leader"),
        "created_at",
    )
    return pl.concat([forward, reverse], how="vertical_relaxed").unique(
        ["war_id", "source_country", "target_country"], maintain_order=True
    )


def active_war_members(context: AITableContext) -> pl.LazyFrame:
    pairs = active_war_pairs(context)
    return pairs.select(
        "war_id",
        pl.col("source_country").alias("country_id"),
    ).unique()


def treaty_member_rows(context: AITableContext, include_pending: bool = False) -> pl.LazyFrame:
    table_name = "pending_treaties" if include_pending else "countries_treaties"
    treaties = context.table(table_name)
    empty = pl.DataFrame(
        schema={
            "treaty_id": pl.Utf8,
            "treaty_type": pl.Utf8,
            "country_id": pl.Utf8,
            "status": pl.Utf8,
            "open_to_new_members": pl.Boolean,
        }
    ).lazy()
    if treaties is None:
        return empty
    schema = set(treaties.collect_schema().names())
    id_column = "id" if "id" in schema else ""
    type_column = "treaty_type" if "treaty_type" in schema else "type" if "type" in schema else ""
    if not id_column or not type_column:
        return empty

    list_columns = [name for name in ("members", "side_a", "side_b") if name in schema]
    if not list_columns:
        return empty
    membership = pl.concat_list([
        pl.col(name).fill_null(pl.lit([], dtype=pl.List(pl.Utf8)))
        for name in list_columns
    ]).list.unique().alias("_members")
    selected = treaties.with_columns(membership)
    status_expr = (
        pl.col("status").cast(pl.Utf8).fill_null("pending")
        if "status" in schema
        else pl.lit("pending" if include_pending else "active")
    )
    open_expr = (
        pl.col("open_to_new_members").cast(pl.Boolean).fill_null(False)
        if "open_to_new_members" in schema
        else pl.lit(False)
    )
    return (
        selected.select(
            pl.col(id_column).cast(pl.Utf8).alias("treaty_id"),
            pl.col(type_column).cast(pl.Utf8).str.to_lowercase().alias("treaty_type"),
            status_expr.alias("status"),
            open_expr.alias("open_to_new_members"),
            "_members",
        )
        .explode("_members")
        .filter(pl.col("_members").is_not_null())
        .select(
            "treaty_id",
            "treaty_type",
            pl.col("_members").cast(pl.Utf8).str.to_uppercase().alias("country_id"),
            "status",
            "open_to_new_members",
        )
        .unique()
    )


def canonical_pair_key(left: str = "source_country", right: str = "target_country") -> pl.Expr:
    return pl.concat_list(pl.col(left), pl.col(right)).list.sort().list.join(":")
