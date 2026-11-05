"""Snapshot aggregates used when resolving covert operations."""

import polars as pl


def cell_metric_frames(cells: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    normalized = cells.with_columns(
        pl.col("country_id").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase().alias("_country"),
        pl.col("target_country_id").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase().alias("_target"),
        pl.col("location_country_id").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase().alias("_location"),
        pl.col("assignment").cast(pl.Utf8, strict=False).fill_null("").alias("_assignment"),
        pl.col("status").cast(pl.Utf8, strict=False).fill_null("").alias("_status"),
    )
    security = (
        normalized.filter(
            (pl.col("_assignment") == "domestic_security")
            & (pl.col("_status") == "active")
            & (pl.col("_country") == pl.col("_location"))
        )
        .group_by("_country")
        .agg(pl.len().cast(pl.Int64).alias("count"))
        .rename({"_country": "country_id"})
    )
    espionage = (
        normalized.filter(
            (pl.col("_assignment") == "espionage")
            & pl.col("_status").is_in(["active", "preparing"])
        )
        .group_by(["_country", "_target"])
        .agg(pl.len().cast(pl.Int64).alias("count"))
        .rename({"_country": "country_id", "_target": "target_country_id"})
    )
    return security, espionage


def metric_value(metrics: pl.DataFrame | None, value_column: str, **keys: str):
    if metrics is None or metrics.is_empty():
        return 0
    filters = [pl.col(column) == value for column, value in keys.items()]
    matches = metrics.filter(pl.all_horizontal(filters)).get_column(value_column)
    return matches[0] if len(matches) else 0


def metric_count(metrics: pl.DataFrame | None, **keys: str) -> int:
    return int(metric_value(metrics, "count", **keys) or 0)


def population_metric_frame(regions: pl.DataFrame | None) -> pl.DataFrame:
    population_column = next(
        (column for column in ("population", "total_population") if regions is not None and column in regions.columns),
        None,
    )
    if regions is None or "owner" not in regions.columns or population_column is None:
        return pl.DataFrame(schema={"country_id": pl.Utf8, "population": pl.Float64})
    value = pl.col(population_column).cast(pl.Float64, strict=False)
    return (
        regions.select(
            pl.col("owner").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase().alias("country_id"),
            pl.when(value.is_finite()).then(value).otherwise(0.0).alias("population"),
        )
        .group_by("country_id")
        .agg(pl.col("population").sum())
    )
