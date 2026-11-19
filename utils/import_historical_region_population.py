"""Import WorldPop's modeled 2001 population counts into OpenPower map regions."""
from __future__ import annotations

import argparse
import csv
import hashlib
import math
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import pycountry
import rasterio
from rasterio.errors import NotGeoreferencedWarning

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "modules" / "base" / "data"
REGION_TABLE = DATA / "regions" / "regions.tsv"
REGION_POPULATION_TABLE = DATA / "regions" / "regions_pop.tsv"
REGION_MASK = DATA / "regions" / "regions.png"
REGION_PROVENANCE = DATA / "sources" / "2001" / "regional_population_provenance.tsv"
REGION_POPULATION_BASELINE = DATA / "sources" / "2001" / "regional_population_legacy_baseline.tsv"
REGION_POPULATION_OVERRIDES = DATA / "sources" / "2001" / "regional_population_overrides.tsv"
RASTER_PROVENANCE = DATA / "sources" / "2001" / "worldpop_regional_raster_sources.tsv"
CACHE_ROOT = ROOT / ".cache" / "worldpop" / "2001"

WORLDPOP_BASE = "https://data.worldpop.org/GIS"
POPULATION_DATASET = "Global_2000_2020_1km"
AGE_SEX_DATASET = "AgeSex_structures/Global_2000_2020_1km/unconstrained"
POPULATION_DOI = "10.5258/SOTON/WP00670"
AGE_SEX_DOI = "10.5258/SOTON/WP00654"

MAP_WIDTH = 16_000
MAP_HEIGHT = 8_000
MAP_LEFT = -180.0
MAP_TOP = 90.0
MAP_RIGHT = 180.0
MAP_BOTTOM = -90.0

CHILD_AGE_STARTS = (0, 1, 5, 10)
OLDER_AGE_STARTS = (65, 70, 75, 80)
SEXES = ("f", "m")
# Large factors mean the source grid barely intersects the game map's source-country regions.
MAX_SPATIAL_RECONCILIATION_FACTOR = 5.0

# WorldPop has no separate UMI raster; use the USA raster for those map regions
# when it has valid cells there.
REGION_SOURCE_FALLBACKS = {"UMI": ("USA",)}

REGION_POPULATION_FIELDS = ["hex", "_owner", "_iso_region", "pop_14", "pop_15_64", "pop_65"]
REGION_POPULATION_OVERRIDE_FIELDS = [
    "hex",
    "owner",
    "source_iso3",
    "year",
    "total_population",
    "pop_14",
    "pop_15_64",
    "pop_65",
    "source_status",
    "source",
    "source_doi",
    "source_url",
    "method",
]
REGION_PROVENANCE_FIELDS = [
    "hex",
    "owner",
    "source_iso3",
    "year",
    "pop_14",
    "pop_15_64",
    "pop_65",
    "valid_1km_cells",
    "spatial_reconciliation_factor",
    "cohort_reconciliation_factor",
    "source_status",
    "source",
    "source_doi",
    "source_url",
    "method",
]
RASTER_PROVENANCE_FIELDS = [
    "source_iso3",
    "asset_type",
    "sex",
    "age_start",
    "year",
    "resolution",
    "source_doi",
    "source_url",
    "cache_size_bytes",
    "sha256",
    "status",
    "note",
]


class SourceRasterNotPublished(Exception):
    """Raised when WorldPop does not publish a requested country raster."""


def read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        return list(reader.fieldnames or ()), list(reader)


def region_source_iso3(region: dict[str, str]) -> str:
    """Resolve the ISO 3166-2 country prefix before falling back to game owner."""
    prefix = region.get("iso_region", "").split("-", 1)[0].upper()
    country = pycountry.countries.get(alpha_2=prefix) if len(prefix) == 2 else None
    return country.alpha_3 if country is not None else region["owner"]


def write_tsv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def load_region_roster() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    _, regions = read_tsv(REGION_TABLE)
    # Keep unsupported regions anchored to the pre-import table across repeat runs.
    baseline_path = REGION_POPULATION_BASELINE if REGION_POPULATION_BASELINE.exists() else REGION_POPULATION_TABLE
    population_fields, population_rows = read_tsv(baseline_path)
    if population_fields != REGION_POPULATION_FIELDS:
        raise ValueError(f"Unexpected population-table fields: {population_fields}")

    region_by_hex = {row["hex"].upper(): row for row in regions}
    population_by_hex = {row["hex"].upper(): row for row in population_rows}
    if len(region_by_hex) != len(regions) or len(population_by_hex) != len(population_rows):
        raise ValueError("Region and population tables must have unique hex keys")
    if region_by_hex.keys() != population_by_hex.keys():
        missing = sorted(region_by_hex.keys() - population_by_hex.keys())[:10]
        extra = sorted(population_by_hex.keys() - region_by_hex.keys())[:10]
        raise ValueError(f"Region population keys do not match regions.tsv; missing={missing}, extra={extra}")

    ordered_population = [population_by_hex[row["hex"].upper()] for row in regions]
    if len(regions) >= 65_535:
        raise ValueError("The uint16 map index cannot represent this many regions")
    return regions, ordered_population


def load_region_population_overrides(
    regions: list[dict[str, str]],
    path: Path = REGION_POPULATION_OVERRIDES,
) -> dict[str, dict[str, str | int]]:
    """Load source-backed regional observations that replace unsupported baselines."""
    fields, rows = read_tsv(path)
    if fields != REGION_POPULATION_OVERRIDE_FIELDS:
        raise ValueError(f"Unexpected regional population override fields in {path}")

    regions_by_hex = {region["hex"].upper(): region for region in regions}
    overrides: dict[str, dict[str, str | int]] = {}
    for row in rows:
        hex_value = row["hex"].upper()
        region = regions_by_hex.get(hex_value)
        if region is None:
            raise ValueError(f"Regional population override references unknown region {hex_value}")
        if row["owner"] != region["owner"]:
            raise ValueError(f"Regional population override owner does not match region {hex_value}")
        if hex_value in overrides:
            raise ValueError(f"Duplicate regional population override for region {hex_value}")

        total_population = int(row["total_population"])
        cohorts = tuple(int(row[field]) for field in ("pop_14", "pop_15_64", "pop_65"))
        if total_population < 0 or any(value < 0 for value in cohorts):
            raise ValueError(f"Regional population override must be non-negative for region {hex_value}")
        if sum(cohorts) != total_population:
            raise ValueError(f"Regional population cohorts must sum to the total for region {hex_value}")
        if not row["source_status"] or not row["source"] or not row["source_url"] or not row["method"]:
            raise ValueError(f"Regional population override needs source and method details for region {hex_value}")

        normalized: dict[str, str | int] = dict(row)
        normalized["hex"] = hex_value
        normalized["year"] = int(row["year"])
        normalized["total_population"] = total_population
        for field, value in zip(("pop_14", "pop_15_64", "pop_65"), cohorts, strict=True):
            normalized[field] = value
        overrides[hex_value] = normalized
    return overrides


def build_region_index_image(regions: list[dict[str, str]]) -> np.ndarray:
    """Map each colored game-map pixel to a compact region-row index."""
    color_lookup = np.zeros(1 << 24, dtype=np.uint16)
    for index, region in enumerate(regions, start=1):
        color_lookup[int(region["hex"].lstrip("#"), 16)] = index

    region_indexes = np.zeros((MAP_HEIGHT, MAP_WIDTH), dtype=np.uint16)
    with warnings.catch_warnings():
        # The game mask is deliberately pixel-only; mapgen.toml supplies its WGS84 bounds.
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with rasterio.open(REGION_MASK) as source:
            if (source.width, source.height) != (MAP_WIDTH, MAP_HEIGHT) or source.count < 3:
                raise ValueError("The region mask dimensions or RGB bands do not match mapgen.toml")
            rgb = source.read((1, 2, 3))

    # The mask is an equirectangular WGS84 image; row-by-row packing avoids a
    # second full-size 32-bit image while converting its RGB keys to row ids.
    for row in range(MAP_HEIGHT):
        red = rgb[0, row].astype(np.uint32)
        green = rgb[1, row].astype(np.uint32)
        blue = rgb[2, row].astype(np.uint32)
        packed = (red << 16) | (green << 8) | blue
        region_indexes[row] = color_lookup[packed]
    return region_indexes


def geographic_centers_to_map_indices(
    longitude: np.ndarray,
    latitude: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Project WGS84 cell centers to the equirectangular region mask."""
    map_x = np.floor((longitude - MAP_LEFT) * MAP_WIDTH / (MAP_RIGHT - MAP_LEFT)).astype(np.int32)
    map_y = np.floor((MAP_TOP - latitude) * MAP_HEIGHT / (MAP_TOP - MAP_BOTTOM)).astype(np.int32)
    return np.clip(map_x, 0, MAP_WIDTH - 1), np.clip(map_y, 0, MAP_HEIGHT - 1)


def raster_window_region_ids(
    transform: rasterio.Affine,
    row_offset: int,
    column_offset: int,
    height: int,
    width: int,
    region_index_image: np.ndarray,
) -> np.ndarray:
    """Return mask-region ids for the source grid cells in one TIFF block."""
    if abs(transform.b) > 1e-12 or abs(transform.d) > 1e-12 or transform.a <= 0 or transform.e >= 0:
        raise ValueError("WorldPop rasters must use an unrotated north-up geographic grid")
    columns = np.arange(column_offset, column_offset + width, dtype=np.float64)
    rows = np.arange(row_offset, row_offset + height, dtype=np.float64)
    longitude = transform.c + (columns + 0.5) * transform.a
    latitude = transform.f + (rows + 0.5) * transform.e
    map_x, _ = geographic_centers_to_map_indices(longitude, latitude[:1])
    _, map_y = geographic_centers_to_map_indices(longitude[:1], latitude)
    return region_index_image[map_y[:, None], map_x[None, :]]


def accumulate_values_by_region(
    totals: np.ndarray,
    coverage: np.ndarray,
    region_ids: np.ndarray,
    values: np.ndarray,
    nodata: float | None,
    allowed_region_ids: np.ndarray,
) -> None:
    valid = np.isfinite(values) & (values >= 0) & (region_ids > 0)
    if nodata is not None:
        valid &= values != nodata
    if not valid.any():
        return

    ids = region_ids[valid].astype(np.int64, copy=False)
    allowed = allowed_region_ids[ids]
    if not allowed.any():
        return
    ids = ids[allowed]
    selected_values = values[valid][allowed].astype(np.float64, copy=False)
    coverage += np.bincount(ids, minlength=len(coverage))
    totals += np.bincount(ids, weights=selected_values, minlength=len(totals))


def aggregate_raster_by_region(
    raster_path: Path,
    region_index_image: np.ndarray,
    allowed_region_ids: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float]:
    region_count = len(allowed_region_ids) - 1
    totals = np.zeros(region_count + 1, dtype=np.float64)
    coverage = np.zeros(region_count + 1, dtype=np.int64)
    raster_total = 0.0

    with rasterio.open(raster_path) as source:
        if source.crs is not None and source.crs.to_epsg() != 4326:
            raise ValueError(f"Expected WGS84 source raster, found {source.crs}: {raster_path}")
        for _, window in source.block_windows(1):
            values = source.read(1, window=window)
            valid_values = np.isfinite(values) & (values >= 0)
            if source.nodata is not None:
                valid_values &= values != source.nodata
            raster_total += float(values[valid_values].sum(dtype=np.float64))
            ids = raster_window_region_ids(
                source.transform,
                int(window.row_off),
                int(window.col_off),
                values.shape[0],
                values.shape[1],
                region_index_image,
            )
            accumulate_values_by_region(totals, coverage, ids, values, source.nodata, allowed_region_ids)
    return totals, coverage, raster_total


def partition_population_cohorts(
    total: np.ndarray,
    children: np.ndarray,
    older: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Derive a non-negative 15-64 cohort and reconcile small surface mismatches."""
    values = (total, children, older)
    if any(not np.isfinite(value).all() or np.any(value < 0) for value in values):
        raise ValueError("Population totals and age cohorts must be finite and non-negative")

    requested = children + older
    scale = np.ones_like(total, dtype=np.float64)
    exceeds_total = requested > total
    scale[exceeds_total] = np.divide(
        total[exceeds_total],
        requested[exceeds_total],
        out=np.zeros_like(total[exceeds_total], dtype=np.float64),
        where=requested[exceeds_total] > 0,
    )
    adjusted_children = children * scale
    adjusted_older = older * scale
    working_age = np.maximum(total - adjusted_children - adjusted_older, 0.0)
    return adjusted_children, working_age, adjusted_older, scale


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download_source_file(url: str, destination: Path) -> dict[str, int | str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size > 0:
        return {"size": destination.stat().st_size, "sha256": sha256_file(destination)}

    temporary = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(5):
        try:
            request = Request(url, headers={"User-Agent": "OpenPower historical scenario data importer/1.0"})
            with urlopen(request, timeout=180) as response, temporary.open("wb") as stream:
                expected = response.headers.get("Content-Length")
                size = 0
                digest = hashlib.sha256()
                while chunk := response.read(1024 * 1024):
                    stream.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            if expected and size != int(expected):
                raise IOError(f"Incomplete raster download: expected {expected} bytes, received {size}")
            temporary.replace(destination)
            return {"size": size, "sha256": digest.hexdigest()}
        except HTTPError as error:
            temporary.unlink(missing_ok=True)
            if error.code == 404:
                raise SourceRasterNotPublished(url) from error
            if error.code < 500 and error.code != 429:
                raise
            if attempt == 4:
                raise
        except (URLError, TimeoutError, OSError):
            temporary.unlink(missing_ok=True)
            if attempt == 4:
                raise
        time.sleep(min(2**attempt, 16))
    raise RuntimeError(f"Failed to download WorldPop raster: {url}")


def raster_specs(source_iso3: str) -> list[dict[str, str | int]]:
    country = source_iso3.lower()
    pop_url = (
        f"{WORLDPOP_BASE}/Population/{POPULATION_DATASET}/2001/{source_iso3}/"
        f"{country}_ppp_2001_1km_Aggregated.tif"
    )
    specs: list[dict[str, str | int]] = [
        {"asset_type": "population_total", "sex": "", "age_start": "", "url": pop_url}
    ]
    age_base = f"{WORLDPOP_BASE}/{AGE_SEX_DATASET}/2001/{source_iso3}"
    for sex in SEXES:
        for age_start in (*CHILD_AGE_STARTS, *OLDER_AGE_STARTS):
            filename = f"{country}_{sex}_{age_start}_2001_1km.tif"
            specs.append({
                "asset_type": "age_sex_cohort",
                "sex": sex,
                "age_start": age_start,
                "url": f"{age_base}/{filename}",
            })
    return specs


def raster_cache_path(source_iso3: str, asset_type: str, sex: str, age_start: str | int) -> Path:
    if asset_type == "population_total":
        name = "population_total.tif"
    else:
        name = f"age_{sex}_{age_start}.tif"
    return CACHE_ROOT / source_iso3 / name


def source_provenance_row(
    source_iso3: str,
    spec: dict[str, str | int],
    status: str,
    result: dict[str, int | str] | None = None,
    note: str = "",
) -> dict[str, str | int]:
    doi = POPULATION_DOI if spec["asset_type"] == "population_total" else AGE_SEX_DOI
    return {
        "source_iso3": source_iso3,
        "asset_type": spec["asset_type"],
        "sex": spec["sex"],
        "age_start": spec["age_start"],
        "year": 2001,
        "resolution": "1km",
        "source_doi": doi,
        "source_url": spec["url"],
        "cache_size_bytes": result["size"] if result else "",
        "sha256": result["sha256"] if result else "",
        "status": status,
        "note": note,
    }


def fetch_country_rasters(
    source_iso3: str,
    specs: list[dict[str, str | int]],
    max_workers: int,
) -> tuple[dict[tuple[str, str, str], Path], list[dict[str, str | int]]]:
    files: dict[tuple[str, str, str], Path] = {}
    provenance: list[dict[str, str | int]] = []
    total_spec, *age_specs = specs
    total_path = raster_cache_path(
        source_iso3,
        str(total_spec["asset_type"]),
        str(total_spec["sex"]),
        total_spec["age_start"],
    )
    try:
        total_result = download_source_file(str(total_spec["url"]), total_path)
    except SourceRasterNotPublished as error:
        provenance.append(source_provenance_row(
            source_iso3, total_spec, "not_published", note=str(error)
        ))
        return files, provenance
    provenance.append(source_provenance_row(source_iso3, total_spec, "verified", total_result))
    files[("population_total", "", "")] = total_path

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for spec in age_specs:
            path = raster_cache_path(
                source_iso3,
                str(spec["asset_type"]),
                str(spec["sex"]),
                spec["age_start"],
            )
            future = executor.submit(download_source_file, str(spec["url"]), path)
            futures[future] = (spec, path)

        for future in as_completed(futures):
            spec, path = futures[future]
            try:
                result = future.result()
            except SourceRasterNotPublished as error:
                provenance.append(source_provenance_row(
                    source_iso3, spec, "not_published", note=str(error)
                ))
                continue
            provenance.append(source_provenance_row(source_iso3, spec, "verified", result))
            key = (str(spec["asset_type"]), str(spec["sex"]), str(spec["age_start"]))
            files[key] = path
    return files, provenance


def aggregate_source_country(
    source_iso3: str,
    region_count: int,
    region_index_image: np.ndarray,
    max_workers: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, float, float, list[dict[str, str | int]]]:
    total = np.zeros(region_count + 1, dtype=np.float64)
    children = np.zeros(region_count + 1, dtype=np.float64)
    older = np.zeros(region_count + 1, dtype=np.float64)
    coverage = np.zeros(region_count + 1, dtype=np.int64)
    raw_total = 0.0
    raw_children = 0.0
    raw_older = 0.0

    allowed_region_ids = np.ones(region_count + 1, dtype=bool)

    specs = raster_specs(source_iso3)
    files, file_provenance = fetch_country_rasters(source_iso3, specs, max_workers)
    total_path = files.get(("population_total", "", ""))
    expected_age_keys = {
        ("age_sex_cohort", sex, str(age))
        for sex in SEXES
        for age in (*CHILD_AGE_STARTS, *OLDER_AGE_STARTS)
    }
    available_age_keys = {key for key in files if key[0] == "age_sex_cohort"}
    if total_path is None or available_age_keys != expected_age_keys:
        return total, children, older, coverage, raw_total, raw_children, raw_older, file_provenance

    total, coverage, raw_total = aggregate_raster_by_region(total_path, region_index_image, allowed_region_ids)
    for sex in SEXES:
        for age_start in CHILD_AGE_STARTS:
            band_total, _, band_raw_total = aggregate_raster_by_region(
                files[("age_sex_cohort", sex, str(age_start))],
                region_index_image,
                allowed_region_ids,
            )
            children += band_total
            raw_children += band_raw_total
        for age_start in OLDER_AGE_STARTS:
            band_total, _, band_raw_total = aggregate_raster_by_region(
                files[("age_sex_cohort", sex, str(age_start))],
                region_index_image,
                allowed_region_ids,
            )
            older += band_total
            raw_older += band_raw_total
    return total, children, older, coverage, raw_total, raw_children, raw_older, file_provenance


def rounded_population(value: float) -> int:
    return math.floor(value + 0.5)


def import_population_data(iso3_filter: set[str] | None, dry_run: bool) -> dict[str, int]:
    regions, population_rows = load_region_roster()
    population_overrides = load_region_population_overrides(regions)
    region_indexes = build_region_index_image(regions)
    region_count = len(regions)

    total = np.zeros(region_count + 1, dtype=np.float64)
    children = np.zeros(region_count + 1, dtype=np.float64)
    older = np.zeros(region_count + 1, dtype=np.float64)
    coverage = np.zeros(region_count + 1, dtype=np.int64)
    source_by_region: dict[int, str] = {}
    spatial_factor_by_region: dict[int, float] = {}
    raster_provenance: list[dict[str, str | int]] = []

    candidates_by_region: dict[int, tuple[str, ...]] = {}
    for index, region in enumerate(regions, start=1):
        primary = region_source_iso3(region)
        candidates = dict.fromkeys((
            primary,
            region["owner"],
            *REGION_SOURCE_FALLBACKS.get(region["owner"], ()),
        ))
        candidates_by_region[index] = tuple(candidates)
    all_sources = sorted({
        source
        for candidates in candidates_by_region.values()
        for source in candidates
        if source != "UMI"
    })
    if iso3_filter:
        unknown = iso3_filter - set(all_sources)
        if unknown:
            raise ValueError(f"Unknown source country code(s): {sorted(unknown)}")
        source_codes = sorted(iso3_filter)
    else:
        source_codes = all_sources

    results_by_source: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
    spatial_factor_by_source: dict[str, float] = {}
    for source_number, source_iso3 in enumerate(source_codes, start=1):
        print(f"[{source_number}/{len(source_codes)}] Downloading and aggregating WorldPop {source_iso3}…", flush=True)
        (
            local_total,
            local_children,
            local_older,
            local_coverage,
            raw_total,
            _raw_children,
            _raw_older,
            local_manifest,
        ) = aggregate_source_country(
            source_iso3,
            region_count,
            region_indexes,
            max_workers=6,
        )
        raster_provenance.extend(local_manifest)
        if not local_coverage.any():
            print(f"  no mapped source cells for {source_iso3}", flush=True)
            continue

        candidate_indexes = np.fromiter(
            (index for index, candidates in candidates_by_region.items() if source_iso3 in candidates),
            dtype=np.int64,
        )
        mapped_total = float(local_total[candidate_indexes].sum()) if candidate_indexes.size else 0.0
        spatial_factor = raw_total / mapped_total if mapped_total > 0 else 1.0
        if spatial_factor > MAX_SPATIAL_RECONCILIATION_FACTOR:
            for manifest_row in local_manifest:
                if manifest_row["asset_type"] == "population_total" and manifest_row["status"] == "verified":
                    manifest_row["note"] = (
                        f"Source raster sum={raw_total:.3f}; mapped candidate-region sum={mapped_total:.3f}; "
                        f"reconciliation factor={spatial_factor:.8f} exceeds the {MAX_SPATIAL_RECONCILIATION_FACTOR:.1f}x "
                        "quality limit, so this raster was retained as source evidence but excluded from region assignment."
                    )
            print(
                f"  insufficient map overlap for region assignment ({spatial_factor:.4f}x reconciliation); "
                "retaining existing region baselines",
                flush=True,
            )
            continue
        if mapped_total > 0:
            local_total *= spatial_factor
            local_children *= spatial_factor
            local_older *= spatial_factor
        for manifest_row in local_manifest:
            if manifest_row["asset_type"] == "population_total" and manifest_row["status"] == "verified":
                manifest_row["note"] = (
                    f"Source raster sum={raw_total:.3f}; mapped candidate-region sum={mapped_total:.3f}; "
                    f"spatial reconciliation factor={spatial_factor:.8f}."
                )
        results_by_source[source_iso3] = (local_total, local_children, local_older, local_coverage)
        spatial_factor_by_source[source_iso3] = spatial_factor
        covered_regions = int(np.count_nonzero(local_coverage[candidate_indexes]))
        source_population = rounded_population(float(local_total[candidate_indexes].sum()))
        print(
            f"  mapped {covered_regions} candidate regions; reconciled candidate population {source_population:,}; "
            f"source total {rounded_population(raw_total):,}; reconciliation {spatial_factor:.4f}x",
            flush=True,
        )

    for region_index, candidates in candidates_by_region.items():
        for candidate in candidates:
            candidate_result = results_by_source.get(candidate)
            if candidate_result is None or candidate_result[3][region_index] == 0:
                continue
            candidate_total, candidate_children, candidate_older, candidate_coverage = candidate_result
            total[region_index] = candidate_total[region_index]
            children[region_index] = candidate_children[region_index]
            older[region_index] = candidate_older[region_index]
            coverage[region_index] = candidate_coverage[region_index]
            source_by_region[region_index] = candidate
            spatial_factor_by_region[region_index] = spatial_factor_by_source[candidate]
            break

    adjusted_children, working_age, adjusted_older, reconciliation = partition_population_cohorts(
        total, children, older
    )
    population_by_hex = {row["hex"].upper(): row for row in population_rows}
    region_provenance: list[dict[str, str | int | float]] = []
    filled_count = 0
    retained_count = 0
    antarctic_zero_count = 0
    override_count = 0
    assumed_zero_territory_count = 0

    for index, region in enumerate(regions, start=1):
        hex_value = region["hex"].upper()
        population_row = population_by_hex[hex_value]
        source_iso3 = source_by_region.get(index, "")
        cell_count = int(coverage[index])
        observation_year: int | str = 2001 if cell_count else ""
        if cell_count and hex_value not in population_overrides:
            cohort_values = (
                rounded_population(float(adjusted_children[index])),
                rounded_population(float(working_age[index])),
                rounded_population(float(adjusted_older[index])),
            )
            for field, value in zip(("pop_14", "pop_15_64", "pop_65"), cohort_values, strict=True):
                population_row[field] = value
            status = "worldpop_2001_1km"
            source_title = "WorldPop Global1 population and age-sex estimates"
            doi = f"population {POPULATION_DOI}; age-sex {AGE_SEX_DOI}"
            source_url = (
                f"{WORLDPOP_BASE}/Population/{POPULATION_DATASET}/2001/{source_iso3}/"
                f"{source_iso3.lower()}_ppp_2001_1km_Aggregated.tif"
            )
            method = (
                "Sum 1km WGS84 cell counts whose centers fall in the 16000x8000 game-map region; "
                "pop_14 sums ages 0-14, pop_65 sums ages 65+, pop_15_64 is total minus those cohorts."
            )
            if not math.isclose(spatial_factor_by_region[index], 1.0, rel_tol=1e-5):
                method += " Region sums were proportionally reconciled to the WorldPop source-country raster total."
            if reconciliation[index] < 1.0:
                method += " Child and older cohorts were proportionally reconciled to the total raster."
            filled_count += 1
        elif hex_value in population_overrides:
            override = population_overrides[hex_value]
            cell_count = 0
            cohort_values = tuple(int(override[field]) for field in ("pop_14", "pop_15_64", "pop_65"))
            for field, value in zip(("pop_14", "pop_15_64", "pop_65"), cohort_values, strict=True):
                population_row[field] = value
            source_iso3 = str(override["source_iso3"])
            status = str(override["source_status"])
            source_title = str(override["source"])
            doi = str(override["source_doi"])
            source_url = str(override["source_url"])
            method = str(override["method"])
            observation_year = int(override["year"])
            override_count += 1
            if status == "assumed_zero_uninhabited_territory":
                assumed_zero_territory_count += 1
        elif region["owner"] == "ATA":
            cohort_values = (0, 0, 0)
            for field, value in zip(("pop_14", "pop_15_64", "pop_65"), cohort_values, strict=True):
                population_row[field] = value
            status = "assumed_zero_uninhabited_antarctica"
            source_title = "No permanent resident population baseline"
            doi = ""
            source_url = ""
            method = "Set to zero for the non-permanently inhabited Antarctic region; no WorldPop 1km file is published."
            antarctic_zero_count += 1
        else:
            cohort_values = tuple(int(population_row[field]) for field in ("pop_14", "pop_15_64", "pop_65"))
            status = "retained_unverified_legacy_baseline"
            source_title = "Existing OpenPower regional baseline; source year unknown"
            doi = ""
            source_url = ""
            method = "No WorldPop source cell was mapped to this region; existing values were retained and remain unverified."
            retained_count += 1

        region_provenance.append({
            "hex": hex_value,
            "owner": region["owner"],
            "source_iso3": source_iso3,
            "year": observation_year,
            "pop_14": cohort_values[0],
            "pop_15_64": cohort_values[1],
            "pop_65": cohort_values[2],
            "valid_1km_cells": cell_count,
            "spatial_reconciliation_factor": round(spatial_factor_by_region[index], 8) if cell_count else "",
            "cohort_reconciliation_factor": round(float(reconciliation[index]), 8) if cell_count else "",
            "source_status": status,
            "source": source_title,
            "source_doi": doi,
            "source_url": source_url,
            "method": method,
        })

    if not dry_run:
        write_tsv(REGION_POPULATION_TABLE, REGION_POPULATION_FIELDS, population_rows)
        write_tsv(REGION_PROVENANCE, REGION_PROVENANCE_FIELDS, region_provenance)
        raster_provenance.sort(key=lambda row: (row["source_iso3"], row["asset_type"], row["sex"], str(row["age_start"])))
        write_tsv(RASTER_PROVENANCE, RASTER_PROVENANCE_FIELDS, raster_provenance)

    return {
        "regions": region_count,
        "worldpop_regions": filled_count,
        "curated_regions": override_count - assumed_zero_territory_count,
        "retained_unverified": retained_count,
        "antarctica_zero": antarctic_zero_count,
        "assumed_zero_territory": assumed_zero_territory_count,
        "rasters": sum(row["status"] == "verified" for row in raster_provenance),
        "missing_rasters": sum(row["status"] == "not_published" for row in raster_provenance),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iso3", action="append", help="Process only the specified source country; requires --dry-run.")
    parser.add_argument("--dry-run", action="store_true", help="Download and inspect data without changing tracked data tables.")
    args = parser.parse_args()
    if args.iso3 and not args.dry_run:
        parser.error("--iso3 is a diagnostic filter and must be combined with --dry-run")
    summary = import_population_data(set(args.iso3) if args.iso3 else None, args.dry_run)
    mode = "Dry run" if args.dry_run else "Imported"
    print(
        f"{mode}: {summary['worldpop_regions']}/{summary['regions']} regions sourced from WorldPop; "
        f"{summary['curated_regions']} curated source and model overrides; "
        f"{summary['retained_unverified']} retained legacy baselines; "
        f"{summary['antarctica_zero']} Antarctic zeros and "
        f"{summary['assumed_zero_territory']} uninhabited-territory zero assumptions; "
        f"{summary['rasters']} raster files captured, {summary['missing_rasters']} unpublished."
    )


if __name__ == "__main__":
    main()
