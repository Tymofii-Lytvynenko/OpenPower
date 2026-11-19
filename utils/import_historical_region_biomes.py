"""Assign RESOLVE ecoregion classifications to the OpenPower region map."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from http.client import IncompleteRead
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from shapely import make_valid
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "modules" / "base" / "data"
REGION_TABLE = DATA / "regions" / "regions.tsv"
OUTPUT_TABLE = DATA / "regions" / "regions_biomes.tsv"
SOURCE_SNAPSHOT = DATA / "sources" / "2001" / "resolve_ecoregions_2017.geojson.gz"
SOURCE_MANIFEST = DATA / "sources" / "2001" / "resolve_ecoregions_2017_manifest.json"

SERVICE_URL = (
    "https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/"
    "Resolve_Ecoregions/FeatureServer/0/query"
)
SOURCE_PAGE = "https://ecoregions2017.appspot.com/"
SOURCE_DATASET = "RESOLVE Ecoregions 2017"
SOURCE_LICENSE = "CC-BY 4.0"
ATTRIBUTION = "Dinerstein et al. (2017), RESOLVE Ecoregions"
OUT_FIELDS = "ECO_ID,ECO_NAME,BIOME_NAME,BIOME_NUM,REALM,ECO_BIOME_,LICENSE"
PAGE_SIZE = 50
MAP_WIDTH = 16_000
MAP_HEIGHT = 8_000

OUTPUT_FIELDS = [
    "hex",
    "biome",
    "biome_id",
    "ecoregion",
    "ecoregion_id",
    "ecological_realm",
    "biome_assignment_method",
    "assignment_distance_degrees",
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def write_tsv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def request_json(url: str) -> dict:
    request = Request(url, headers={
        "Accept-Encoding": "gzip",
        "User-Agent": "OpenPower historical-data importer",
    })
    with urlopen(request, timeout=120) as response:
        payload = response.read()
        if response.headers.get("Content-Encoding", "").lower() == "gzip":
            payload = gzip.decompress(payload)
    return json.loads(payload)


def source_query_url(offset: int, page_size: int) -> str:
    params = {
        "where": "1=1",
        "outFields": OUT_FIELDS,
        "outSR": "4326",
        "returnGeometry": "true",
        "resultOffset": str(offset),
        "resultRecordCount": str(page_size),
    "maxAllowableOffset": "0.0025",
    "geometryPrecision": "5",
        "f": "geojson",
    }
    return f"{SERVICE_URL}?{urlencode(params)}"


def download_source_snapshot() -> dict:
    features: list[dict] = []
    offset = 0
    seen_ids: set[int] = set()
    page_size = PAGE_SIZE
    while True:
        try:
            page = request_json(source_query_url(offset, page_size))
        except (IncompleteRead, OSError, TimeoutError, json.JSONDecodeError) as error:
            if page_size <= 1:
                raise RuntimeError(f"Could not retrieve RESOLVE page at offset {offset}") from error
            page_size = max(1, page_size // 2)
            continue
        page_features = page.get("features", [])
        if not page_features:
            break
        for feature in page_features:
            properties = feature.get("properties", {})
            if properties.get("LICENSE") != SOURCE_LICENSE:
                raise ValueError(f"Unexpected source license for ecoregion {properties.get('ECO_ID')}")
            ecoregion_id = int(properties["ECO_ID"])
            if ecoregion_id in seen_ids:
                raise ValueError(f"Duplicate RESOLVE ecoregion id: {ecoregion_id}")
            seen_ids.add(ecoregion_id)
            if not feature.get("geometry"):
                raise ValueError(f"Missing geometry for RESOLVE ecoregion {ecoregion_id}")
            features.append(feature)
        offset += len(page_features)
        if len(page_features) < page_size:
            break

    if not features:
        raise RuntimeError("The RESOLVE service returned no ecoregion features")
    features.sort(key=lambda feature: int(feature["properties"]["ECO_ID"]))
    return {"type": "FeatureCollection", "features": features}


def save_source_snapshot(source: dict) -> str:
    payload = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    SOURCE_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    with SOURCE_SNAPSHOT.open("wb") as raw_stream:
        with gzip.GzipFile(fileobj=raw_stream, mode="wb", mtime=0, filename="") as compressed_stream:
            compressed_stream.write(payload)
    return hashlib.sha256(SOURCE_SNAPSHOT.read_bytes()).hexdigest()


def load_source_snapshot() -> tuple[dict, str]:
    payload = gzip.decompress(SOURCE_SNAPSHOT.read_bytes())
    return json.loads(payload), hashlib.sha256(SOURCE_SNAPSHOT.read_bytes()).hexdigest()


def validate_source_features(source: dict) -> list[tuple[dict, object]]:
    features: list[tuple[dict, object]] = []
    ids: set[int] = set()
    for feature in source.get("features", []):
        properties = feature.get("properties", {})
        if properties.get("LICENSE") != SOURCE_LICENSE:
            raise ValueError(f"Unexpected source license for ecoregion {properties.get('ECO_ID')}")
        ecoregion_id = int(properties["ECO_ID"])
        if ecoregion_id in ids:
            raise ValueError(f"Duplicate RESOLVE ecoregion id: {ecoregion_id}")
        ids.add(ecoregion_id)
        geometry = shape(feature["geometry"])
        repaired = False
        if not geometry.is_valid:
            # ArcGIS returns one self-intersecting Rock and Ice polygon; repair it for point queries.
            geometry = make_valid(geometry)
            repaired = True
        if geometry.is_empty or not geometry.is_valid:
            raise ValueError(f"Invalid RESOLVE geometry for ecoregion {ecoregion_id}")
        properties = dict(properties)
        properties["_openpower_geometry_repaired"] = repaired
        required = ("ECO_NAME", "BIOME_NUM", "REALM")
        if any(properties.get(name) in (None, "") for name in required):
            raise ValueError(f"Missing classification attributes for ecoregion {ecoregion_id}")
        features.append((properties, geometry))
    if not features:
        raise ValueError("The source snapshot contains no ecoregion features")
    biome_names = {
        int(properties["BIOME_NUM"]): properties["BIOME_NAME"]
        for properties, _ in features
        if properties.get("BIOME_NAME") not in (None, "", "N/A")
    }
    for properties, _ in features:
        if properties.get("BIOME_NAME") in (None, "", "N/A"):
            properties["BIOME_NAME"] = biome_names.get(int(properties["BIOME_NUM"]))
        if not properties.get("BIOME_NAME"):
            raise ValueError(f"No source biome name for ecoregion {properties['ECO_ID']}")
    return features


def region_center(region: dict[str, str]) -> Point:
    x = float(region["center_x"])
    y = float(region["center_y"])
    longitude = x * 360.0 / MAP_WIDTH - 180.0
    latitude = 90.0 - y * 180.0 / MAP_HEIGHT
    return Point(longitude, latitude)


def assign_regions(regions: list[dict[str, str]], source_features: list[tuple[dict, object]]) -> tuple[list[dict], dict[str, int]]:
    geometries = [geometry for _, geometry in source_features]
    tree = STRtree(geometries)
    output: list[dict] = []
    methods = {"contained": 0, "nearest": 0}

    for region in regions:
        point = region_center(region)
        matches = tree.query(point, predicate="covered_by")
        if len(matches):
            source_index = min(matches, key=lambda index: int(source_features[int(index)][0]["ECO_ID"]))
            method = "contained"
            distance = 0.0
        else:
            # RESOLVE is terrestrial; nearest-polygon fallback covers offshore map centroids and tiny islands.
            source_index = tree.nearest(point)
            method = "nearest"
            distance = float(point.distance(geometries[int(source_index)]))

        properties = source_features[int(source_index)][0]
        methods[method] += 1
        output.append({
            "hex": region["hex"],
            "biome": properties["BIOME_NAME"],
            "biome_id": int(properties["BIOME_NUM"]),
            "ecoregion": properties["ECO_NAME"],
            "ecoregion_id": int(properties["ECO_ID"]),
            "ecological_realm": properties["REALM"],
            "biome_assignment_method": method,
            "assignment_distance_degrees": f"{distance:.8f}",
        })

    if len({row["hex"] for row in output}) != len(regions):
        raise ValueError("Biome assignments must preserve unique region keys")
    return output, methods


def write_manifest(
    source_sha256: str,
    source_features: list[tuple[dict, object]],
    region_count: int,
    methods: dict[str, int],
) -> None:
    manifest = {
        "dataset": SOURCE_DATASET,
        "source_year": 2017,
        "scenario_year": 2001,
        "source_is_historical_2001_observation": False,
        "classification_role": "spatial baseline applied to the 2001 scenario; not a 2001 ecological survey",
        "attribution": ATTRIBUTION,
        "license": SOURCE_LICENSE,
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "source_page": SOURCE_PAGE,
        "service_url": SERVICE_URL,
        "snapshot_path": str(SOURCE_SNAPSHOT.relative_to(ROOT)).replace("\\", "/"),
        "snapshot_sha256": source_sha256,
        "ecoregion_count": sum(int(properties["ECO_ID"]) != 0 for properties, _ in source_features),
        "source_feature_count": len(source_features),
        "special_rock_and_ice_feature_count": sum(
            int(properties["ECO_ID"]) == 0 for properties, _ in source_features
        ),
        "geometry_repaired_feature_count": sum(
            bool(properties.get("_openpower_geometry_repaired")) for properties, _ in source_features
        ),
        "geometry_generalization_degrees": 0.0025,
        "assigned_region_count": region_count,
        "assignment_method_counts": methods,
        "assignment_method": "OpenPower equirectangular region center; RESOLVE polygon containment, then nearest WGS84 polygon for unmatched centers",
        "output_table": str(OUTPUT_TABLE.relative_to(ROOT)).replace("\\", "/"),
    }
    SOURCE_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def import_biomes(refresh: bool = False) -> dict[str, int]:
    if refresh or not SOURCE_SNAPSHOT.exists():
        source = download_source_snapshot()
        source_sha256 = save_source_snapshot(source)
    else:
        source, source_sha256 = load_source_snapshot()

    source_features = validate_source_features(source)
    regions = read_tsv(REGION_TABLE)
    assignments, methods = assign_regions(regions, source_features)
    write_tsv(OUTPUT_TABLE, OUTPUT_FIELDS, assignments)
    write_manifest(source_sha256, source_features, len(assignments), methods)
    return methods


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Download the latest published source snapshot")
    args = parser.parse_args()
    methods = import_biomes(refresh=args.refresh)
    print(f"Assigned {sum(methods.values())} regions from RESOLVE Ecoregions 2017: {methods}")


if __name__ == "__main__":
    main()
