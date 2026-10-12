"""Polars-backed geometry preparation for repeated route searches."""

from __future__ import annotations

from math import pi

import polars as pl


def edge_distance_index(
    regions: pl.DataFrame | None,
    adjacency: dict[int, set[int]],
) -> dict[tuple[int, int], float]:
    """Compute geographic distance once for each undirected graph edge."""
    coordinates = _geographic_coordinates(regions)
    if coordinates is None or not adjacency:
        return {}

    pairs = [
        (source_id, target_id)
        for source_id, neighbors in adjacency.items()
        for target_id in neighbors
        if source_id < target_id
    ]
    if not pairs:
        return {}

    edges = pl.DataFrame(
        {
            "source_region_id": [source for source, _ in pairs],
            "target_region_id": [target for _, target in pairs],
        },
        schema={
            "source_region_id": pl.Int64,
            "target_region_id": pl.Int64,
        },
    )
    source_coordinates = coordinates.rename(
        {
            "region_id": "source_region_id",
            "latitude": "source_latitude",
            "longitude": "source_longitude",
        }
    )
    target_coordinates = coordinates.rename(
        {
            "region_id": "target_region_id",
            "latitude": "target_latitude",
            "longitude": "target_longitude",
        }
    )
    joined = edges.join(source_coordinates, on="source_region_id", how="inner").join(
        target_coordinates, on="target_region_id", how="inner"
    )

    radians_per_degree = pi / 180.0
    latitude_delta = (
        (pl.col("target_latitude") - pl.col("source_latitude"))
        * radians_per_degree
    )
    longitude_delta_degrees = pl.col("target_longitude") - pl.col("source_longitude")
    longitude_delta = (
        ((longitude_delta_degrees + 180.0) % 360.0) - 180.0
    ) * radians_per_degree
    latitude_1 = pl.col("source_latitude") * radians_per_degree
    latitude_2 = pl.col("target_latitude") * radians_per_degree
    haversine = (
        (latitude_delta / 2.0).sin().pow(2)
        + latitude_1.cos() * latitude_2.cos() * (longitude_delta / 2.0).sin().pow(2)
    )
    measured = joined.with_columns(
        (haversine.clip(0.0, 1.0).sqrt().arcsin() * (2.0 * 6371.0)).alias(
            "distance_km"
        )
    )
    return {
        (int(source), int(target)): float(distance)
        for source, target, distance in measured.select(
            "source_region_id", "target_region_id", "distance_km"
        ).iter_rows()
    }


def _geographic_coordinates(regions: pl.DataFrame | None) -> pl.DataFrame | None:
    if regions is None or regions.is_empty() or "id" not in regions.columns:
        return None

    columns = set(regions.columns)
    if {"latitude", "longitude"}.issubset(columns):
        coordinates = regions.select(
            pl.col("id").cast(pl.Int64, strict=False).alias("region_id"),
            pl.col("latitude")
            .cast(pl.Float64, strict=False)
            .clip(-90.0, 90.0)
            .alias("latitude"),
            pl.col("longitude").cast(pl.Float64, strict=False).alias("longitude"),
        )
    elif {"center_x", "center_y"}.issubset(columns):
        width = max(float(regions["center_x"].max() or 1.0) + 1.0, 1.0)
        height = max(float(regions["center_y"].max() or 1.0) + 1.0, 1.0)
        coordinates = regions.select(
            pl.col("id").cast(pl.Int64, strict=False).alias("region_id"),
            (90.0 - pl.col("center_y").cast(pl.Float64, strict=False) / height * 180.0)
            .clip(-90.0, 90.0)
            .alias("latitude"),
            (pl.col("center_x").cast(pl.Float64, strict=False) / width * 360.0 - 180.0)
            .alias("longitude"),
        )
    else:
        return None

    return (
        coordinates.with_columns(
            ((pl.col("longitude") + 180.0) % 360.0 - 180.0).alias("longitude")
        )
        .filter(
            pl.col("region_id").is_not_null()
            & pl.col("latitude").is_finite()
            & pl.col("longitude").is_finite()
        )
        .unique(subset="region_id", keep="last", maintain_order=True)
    )
