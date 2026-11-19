import polars as pl
import math
from typing import Optional

from src.core.map.geo import EquirectangularProjection, GeoCoordinate

def image_to_world(x: float, y: float, map_height: float) -> tuple[float, float]:
    """
    Converts a single point from Image Space (Top-Left) 
    to Game World coordinates (Origin: Bottom-Left).
    """
    return float(x), map_height - float(y)

def calculate_centroid(
    regions_df: pl.DataFrame,
    map_height: float,
    map_width: Optional[float] = None,
) -> Optional[tuple[float, float]]:
    """
    Calculates the geometric center (World Coordinates) for a DataFrame of regions.
    
    Usage:
        - Center camera on a specific Country (Pass all regions owned by 'USA')
        - Center camera on a specific Province (Pass all regions in 'Texas')
    """
    if regions_df.is_empty():
        return None

    width = map_width or _infer_map_width(regions_df)
    if {"latitude", "longitude"}.issubset(set(regions_df.columns)):
        geo_center = _calculate_geo_centroid(regions_df)
        if geo_center is not None:
            projection = EquirectangularProjection(width, map_height)
            pixel = projection.geo_to_pixel(geo_center)
            return image_to_world(pixel.x, pixel.y, map_height)
        
    # 1. Calculate Average in Image Space (Raw Data)
    # We use Polars mean() which ignores nulls automatically
    if not {"center_x", "center_y"}.issubset(regions_df.columns):
        # A missing camera hint should not prevent the game session from starting.
        return None
    # Ignore invalid points as a pair so the two axes describe the same regions.
    centers = regions_df.select(
        pl.col("center_x").cast(pl.Float64, strict=False),
        pl.col("center_y").cast(pl.Float64, strict=False),
    ).filter(pl.col("center_x").is_finite() & pl.col("center_y").is_finite())
    avg_x = centers["center_x"].mean()
    avg_y = centers["center_y"].mean()
    
    if avg_x is None or avg_y is None:
        return None

    # 2. Convert result to World Space (Inverted Y)
    return image_to_world(avg_x, avg_y, map_height) # type: ignore


def _calculate_geo_centroid(regions_df: pl.DataFrame) -> Optional[GeoCoordinate]:
    sum_x = 0.0
    sum_y = 0.0
    sum_z = 0.0
    count = 0

    for row in regions_df.select(["latitude", "longitude"]).iter_rows(named=True):
        latitude = row["latitude"]
        longitude = row["longitude"]
        if latitude is None or longitude is None:
            continue

        try:
            latitude, longitude = float(latitude), float(longitude)
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(latitude) or not math.isfinite(longitude):
            continue

        lat = math.radians(latitude)
        lon = math.radians(longitude)
        cos_lat = math.cos(lat)
        sum_x += cos_lat * math.cos(lon)
        sum_y += math.sin(lat)
        sum_z += cos_lat * math.sin(lon)
        count += 1

    if count == 0:
        return None

    length = math.sqrt(sum_x * sum_x + sum_y * sum_y + sum_z * sum_z)
    if length <= 1e-9:
        return None

    latitude = math.degrees(math.asin(sum_y / length))
    longitude = math.degrees(math.atan2(sum_z, sum_x))
    return GeoCoordinate(latitude=latitude, longitude=longitude)


def _infer_map_width(regions_df: pl.DataFrame) -> float:
    if "center_x" not in regions_df.columns:
        return 1.0

    values = regions_df["center_x"].cast(pl.Float64, strict=False)
    max_x = values.filter(values.is_finite()).max()
    return max(1.0, float(max_x or 0.0) + 1.0)
