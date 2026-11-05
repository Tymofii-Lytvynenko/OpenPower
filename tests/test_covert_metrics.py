import polars as pl

from modules.base.systems.military.covert_metrics import (
    cell_metric_frames, metric_count, metric_value, population_metric_frame,
)


def test_cell_metrics_count_only_eligible_assignments_and_normalize_countries():
    cells = pl.DataFrame([
        {"country_id": " aaa ", "target_country_id": "BBB", "location_country_id": "AAA", "assignment": "domestic_security", "status": "active"},
        {"country_id": "AAA", "target_country_id": "BBB", "location_country_id": "BBB", "assignment": "domestic_security", "status": "active"},
        {"country_id": " aaa ", "target_country_id": " bbb ", "location_country_id": "BBB", "assignment": "espionage", "status": "preparing"},
        {"country_id": "AAA", "target_country_id": "BBB", "location_country_id": "BBB", "assignment": "espionage", "status": "retired"},
    ])
    security, espionage = cell_metric_frames(cells)
    assert metric_count(security, country_id="AAA") == 1
    assert metric_count(espionage, country_id="AAA", target_country_id="BBB") == 1
    assert metric_count(espionage, country_id="BBB", target_country_id="AAA") == 0


def test_population_metrics_ignore_nonfinite_and_missing_values():
    regions = pl.DataFrame([
        {"owner": " aaa ", "population": 20.0},
        {"owner": "AAA", "population": float("nan")},
        {"owner": "BBB", "population": None},
    ])
    population = population_metric_frame(regions)
    assert metric_value(population, "population", country_id="AAA") == 20.0
    assert metric_value(population, "population", country_id="BBB") == 0.0
    assert metric_value(population_metric_frame(None), "population", country_id="AAA") == 0
