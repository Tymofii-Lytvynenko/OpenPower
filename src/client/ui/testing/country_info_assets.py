"""Source-backed assets for deterministic Country Information UI scenarios."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import polars as pl


@dataclass(frozen=True, slots=True)
class CompactRegionMapData:
    """RegionMapData-compatible map buffer scaled for screenshot-sized previews."""

    width: int
    height: int
    packed_map: np.ndarray


def load_country_info_regions(project_root: Path, country_tags: list[str]) -> pl.DataFrame:
    region_dir = Path(project_root) / "modules" / "base" / "data" / "regions"
    regions_path = region_dir / "regions.tsv"
    populations_path = region_dir / "regions_pop.tsv"
    if not regions_path.is_file() or not populations_path.is_file():
        raise FileNotFoundError(f"Country Information fixture data is missing under {region_dir}")

    regions = pl.read_csv(regions_path, separator="\t", infer_schema_length=1000, schema_overrides={"hex": pl.String})
    populations = pl.read_csv(populations_path, separator="\t", infer_schema_length=1000,
                              schema_overrides={"hex": pl.String})
    regions = regions.filter(pl.col("owner").is_in(country_tags))
    populations = populations.select("hex", "_owner", "pop_14", "pop_15_64", "pop_65")
    joined = regions.join(populations, on="hex", how="left")

    # These packed color IDs must match the IDs encoded in the technical region map.
    joined = joined.with_columns(
        pl.col("hex").map_elements(
            lambda value: int(str(value).lstrip("#"), 16), return_dtype=pl.Int32,
        ).alias("id"),
        pl.col("area_km2").cast(pl.Float64, strict=False).fill_null(0.0),
        *[
            pl.col(column).cast(pl.Int64, strict=False).fill_null(0)
            for column in ("pop_14", "pop_15_64", "pop_65")
        ],
    )
    return joined.with_columns(
        pl.sum_horizontal("pop_14", "pop_15_64", "pop_65").alias("population"),
        pl.col("owner").alias("controller"),
    ).select(
        "id", "name", "owner", "controller", "type", "macro_region", "area_km2",
        "pop_14", "pop_15_64", "pop_65", "population",
    )


def load_compact_region_map(project_root: Path, max_dimension: int = 2048) -> CompactRegionMapData:
    map_path = Path(project_root) / "modules" / "base" / "data" / "regions" / "regions.png"
    image = cv2.imread(str(map_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Could not read the technical region map: {map_path}")

    height, width = image.shape[:2]
    scale = min(1.0, max_dimension / max(width, height))
    if scale < 1.0:
        target_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        image = cv2.resize(image, target_size, interpolation=cv2.INTER_NEAREST)

    height, width = image.shape[:2]
    blue, green, red = cv2.split(image)
    packed_map = (
        blue.astype(np.int32)
        | (green.astype(np.int32) << 8)
        | (red.astype(np.int32) << 16)
    )
    return CompactRegionMapData(width, height, packed_map)
