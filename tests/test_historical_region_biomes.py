import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from shapely.geometry import Polygon, box, mapping

from utils.import_historical_region_biomes import (
    OUTPUT_FIELDS,
    assign_regions,
    validate_source_features,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "modules" / "base" / "data"


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def feature(ecoregion_id: int, name: str, biome: str, geometry):
    return ({
        "ECO_ID": ecoregion_id,
        "ECO_NAME": name,
        "BIOME_NAME": biome,
        "BIOME_NUM": 1,
        "REALM": "Test realm",
        "LICENSE": "CC-BY 4.0",
    }, geometry)


def test_region_centers_use_polygon_containment_and_nearest_fallback():
    source_features = [feature(10, "Test ecoregion", "Test biome", box(1, -1, 2, 1))]
    regions = [
        {"hex": "#000001", "center_x": str((1.5 + 180) * 16_000 / 360), "center_y": "4000"},
        {"hex": "#000002", "center_x": "8000", "center_y": "4000"},
    ]

    assignments, methods = assign_regions(regions, source_features)

    assert methods == {"contained": 1, "nearest": 1}
    assert [row["biome_assignment_method"] for row in assignments] == ["contained", "nearest"]
    assert assignments[0]["biome"] == "Test biome"
    assert assignments[0]["ecoregion_id"] == 10
    assert float(assignments[0]["assignment_distance_degrees"]) == 0.0
    assert float(assignments[1]["assignment_distance_degrees"]) > 0.0


def test_source_validation_repairs_invalid_geometry_and_resolves_source_biome_label():
    source = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "ECO_ID": 0,
                    "ECO_NAME": "Rock and Ice",
                    "BIOME_NAME": "N/A",
                    "BIOME_NUM": 11,
                    "REALM": "N/A",
                    "LICENSE": "CC-BY 4.0",
                },
                "geometry": mapping(Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])),
            },
            {
                "type": "Feature",
                "properties": {
                    "ECO_ID": 117,
                    "ECO_NAME": "Tundra ecoregion",
                    "BIOME_NAME": "Tundra",
                    "BIOME_NUM": 11,
                    "REALM": "Arctic",
                    "LICENSE": "CC-BY 4.0",
                },
                "geometry": mapping(box(2, 2, 3, 3)),
            },
        ],
    }

    features = validate_source_features(source)

    assert features[0][0]["_openpower_geometry_repaired"] is True
    assert features[0][0]["BIOME_NAME"] == "Tundra"
    assert features[0][1].is_valid


def test_resolve_snapshot_and_assignments_cover_every_map_region():
    regions = read_tsv(DATA / "regions" / "regions.tsv")
    biomes = read_tsv(DATA / "regions" / "regions_biomes.tsv")
    snapshot_path = DATA / "sources" / "2001" / "resolve_ecoregions_2017.geojson.gz"
    manifest_path = DATA / "sources" / "2001" / "resolve_ecoregions_2017_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot_bytes = snapshot_path.read_bytes()

    assert len(regions) == len(biomes) == 4559
    assert [row["hex"] for row in biomes] == [row["hex"] for row in regions]
    assert all(row["biome"] and row["ecoregion"] and row["ecological_realm"] for row in biomes)
    assert set(OUTPUT_FIELDS).issubset(biomes[0])
    assert Counter(row["biome_assignment_method"] for row in biomes) == manifest["assignment_method_counts"]
    assert manifest["source_year"] == 2017
    assert manifest["scenario_year"] == 2001
    assert manifest["source_is_historical_2001_observation"] is False
    assert manifest["license"] == "CC-BY 4.0"
    assert hashlib.sha256(snapshot_bytes).hexdigest() == manifest["snapshot_sha256"]
    assert manifest["source_feature_count"] == manifest["ecoregion_count"] + 1
    assert manifest["special_rock_and_ice_feature_count"] == 1
    assert manifest["geometry_repaired_feature_count"] > 0

