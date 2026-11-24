"""Allocate national land and inland-water benchmarks to the scenario map.

Land and inland water retain their separate national totals, because the
published surface totals sometimes use a different boundary or definition.
Arable, forest and other land are shares of land. Protected areas may overlap
those uses and retain the source's total-surface denominator.
"""

import csv
from collections import defaultdict
from pathlib import Path


DATA = Path(__file__).resolve().parents[1] / "modules/base/data"
FIELDS = (
    "land_area_km2", "inland_water_area_km2", "arable_area_km2",
    "forest_area_km2", "protected_area_km2", "other_land_area_km2",
)
# Biomes describe ecological potential. Their weights are scenario assumptions.
ARABLE = (0.65, 0.85, 0.5, 1.0, 0.5, 0.28, 0.8, 1.0, 0.75, 0.3, 0.025, 0.8, 0.08, 0.05)
FOREST = (1.0, 0.78, 0.9, 0.95, 1.0, 0.95, 0.34, 0.18, 0.25, 0.28, 0.06, 0.6, 0.04, 0.78)
# FAO FRA 2010, Ukraine table 1, reports 2,420 thousand hectares around the scenario date.
# https://www.fao.org/4/al654E/al654E.pdf
WATER_OVERRIDES_KM2 = {"UKR": 24_200.0}


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def observation(row, field):
    if row.get(f"{field}_available", "").lower() == "true" and row.get(field):
        return float(row[field])
    return None


def allocate(target, weights, capacities=None):
    if target is None:
        return [None] * len(weights)
    if not target:
        return [0.0] * len(weights)
    if capacities is None:
        scale = target / sum(weights)
        return [scale * weight for weight in weights]
    if target > sum(capacities) + 1e-6:
        raise ValueError(f"Target {target} exceeds available area {sum(capacities)}")
    # Capping the weighted split keeps each land-use class within each region.
    lower = 0.0
    upper = max(capacity / weight for capacity, weight in zip(capacities, weights, strict=True) if weight)
    for _ in range(64):
        scale = (lower + upper) / 2
        allocated = sum(min(capacity, weight * scale) for capacity, weight in zip(capacities, weights, strict=True))
        if allocated < target:
            lower = scale
        else:
            upper = scale
    return [min(capacity, weight * upper) for capacity, weight in zip(capacities, weights, strict=True)]


def country_areas(regions, country, biomes):
    map_areas = [max(0.0, float(row["area_km2"])) for row in regions]
    weights = map_areas if any(map_areas) else [1.0] * len(regions)
    land_target = observation(country, "reference_land_area_km2")
    water_target = WATER_OVERRIDES_KM2.get(country.get("id"), observation(country, "reference_water_area_km2"))
    surface_target = observation(country, "reference_total_area_km2")
    land = allocate(sum(map_areas) if land_target is None else land_target, weights)

    def biome_weights(profile):
        return [area * profile[biomes[row["hex"]] - 1] for row, area in zip(regions, weights, strict=True)]

    # The terrestrial biome table cannot locate bodies of inland water.
    water = allocate(water_target, weights)
    remaining = land
    land_use = []
    for field, profile in (
        ("arable_land_pct", ARABLE),
        ("forest_area_pct", FOREST),
        ("other_land_pct", (1.0,) * 14),
    ):
        share = observation(country, field)
        target = None if share is None or land_target is None else land_target * share / 100
        amounts = allocate(target, biome_weights(profile), remaining)
        land_use.append(amounts)
        if target is not None:
            remaining = [max(0.0, capacity - amount) for capacity, amount in zip(remaining, amounts, strict=True)]
    protected_share = observation(country, "terrestrial_protected_area_pct_2000")
    protected = allocate(
        None if protected_share is None or surface_target is None else surface_target * protected_share / 100,
        weights,  # The national designation data has no regional or biome breakdown.
        land,
    )
    return zip(land, water, land_use[0], land_use[1], protected, land_use[2], strict=True)


def main():
    by_country = defaultdict(list)
    region_dir = DATA / "regions"
    regions = read(region_dir / "regions.tsv")
    for region in regions:
        by_country[region["owner"]].append(region)
    countries = {row["id"]: row for row in read(DATA / "countries/countries_historical.tsv")}
    biomes = {row["hex"]: int(row["biome_id"]) for row in read(region_dir / "regions_biomes.tsv")}
    regional = {}
    for country, province_rows in by_country.items():
        for row, amounts in zip(province_rows, country_areas(province_rows, countries.get(country, {}), biomes), strict=True):
            regional[row["hex"]] = amounts

    columns = ("hex", *FIELDS, *(f"{field}_available" for field in FIELDS))
    with (region_dir / "regions_land.tsv").open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(columns)
        for row in regions:
            values = regional[row["hex"]]
            writer.writerow([
                row["hex"],
                *("" if value is None else f"{value:.8f}" for value in values),
                *(str(value is not None).lower() for value in values),
            ])


if __name__ == "__main__":
    main()
