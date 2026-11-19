import numpy as np

from utils.import_historical_region_population import (
    REGION_POPULATION_OVERRIDES,
    accumulate_values_by_region,
    geographic_centers_to_map_indices,
    load_region_population_overrides,
    load_region_roster,
    partition_population_cohorts,
    region_source_iso3,
)


def test_region_source_uses_geographic_subdivision_code_before_controller():
    assert region_source_iso3({"owner": "GBR", "iso_region": "AI-X01~"}) == "AIA"
    assert region_source_iso3({"owner": "CHN", "iso_region": "HK-X02~"}) == "HKG"
    assert region_source_iso3({"owner": "KOS", "iso_region": "XK-X01~"}) == "KOS"


def test_curated_region_population_observations_validate_and_preserve_source_years():
    regions, _ = load_region_roster()

    overrides = load_region_population_overrides(regions, REGION_POPULATION_OVERRIDES)

    assert overrides["#882BBC"]["year"] == 2001
    assert overrides["#882BBC"]["total_population"] == 4
    assert tuple(overrides["#882BBC"][field] for field in ("pop_14", "pop_15_64", "pop_65")) == (0, 4, 0)
    macquarie = overrides["#0B600A"]
    assert macquarie["year"] == 2001
    assert macquarie["total_population"] == 18
    assert tuple(macquarie[field] for field in ("pop_14", "pop_15_64", "pop_65")) == (0, 18, 0)
    assert macquarie["source_status"] == "modeled_station_staffing_2001"
    assert "rounded midpoint" in macquarie["method"]
    assert "not enumerated" in macquarie["method"]
    assert overrides["#3F6AF8"]["year"] == 2000
    assert overrides["#3F6AF8"]["total_population"] == 289
    assert sum(overrides["#3F6AF8"][field] for field in ("pop_14", "pop_15_64", "pop_65")) == 289
    maldives = [row for row in overrides.values() if row["owner"] == "MDV"]
    assert len(maldives) == 21
    assert sum(row["total_population"] for row in maldives) == 270_101

    assert overrides["#9BD870"]["total_population"] == 79_263
    assert overrides["#5D3F4A"]["total_population"] == 6_839
    kiribati = [overrides[hex_value] for hex_value in ("#9BD870", "#5D3F4A")]
    assert sum(row["total_population"] for row in kiribati) == 86_102
    assert all(row["year"] == 2001 for row in kiribati)

    assert overrides["#52F249"]["total_population"] == 21_382
    assert overrides["#B6CA28"]["total_population"] == 33_202
    marshall_islands = [overrides[hex_value] for hex_value in ("#52F249", "#B6CA28")]
    assert sum(row["total_population"] for row in marshall_islands) == 54_584
    assert sum(row["pop_14"] for row in marshall_islands) == 22_941
    assert sum(row["pop_65"] for row in marshall_islands) == 1_140


def test_curated_region_population_observation_rejects_owner_mismatch(tmp_path):
    invalid_overrides = tmp_path / "regional_population_overrides.tsv"
    invalid_overrides.write_text(
        "hex\towner\tsource_iso3\tyear\ttotal_population\tpop_14\tpop_15_64\tpop_65\t"
        "source_status\tsource\tsource_doi\tsource_url\tmethod\n"
        "#882BBC\tMUS\tMUS\t2001\t4\t0\t4\t0\tofficial\tCensus\t\thttps://example.org\tAssumption\n",
        encoding="utf-8",
    )

    try:
        load_region_population_overrides([{"hex": "#882BBC", "owner": "AUS"}], invalid_overrides)
    except ValueError as error:
        assert "owner does not match" in str(error)
    else:
        raise AssertionError("Owner mismatch should be rejected")


def test_geographic_cell_centers_map_to_equirectangular_mask_edges():
    longitude = np.array([-180.0, 0.0, 180.0])
    latitude = np.array([90.0, 0.0, -90.0])

    map_x, map_y = geographic_centers_to_map_indices(longitude, latitude)

    assert map_x.tolist() == [0, 8000, 15999]
    assert map_y.tolist() == [0, 4000, 7999]


def test_region_aggregation_ignores_background_and_nodata_pixels():
    totals = np.zeros(3, dtype=np.float64)
    coverage = np.zeros(3, dtype=np.int64)
    region_ids = np.array([[1, 1, 2, 0, 2]])
    values = np.array([[2.5, 3.5, 4.0, 50.0, -99999.0]], dtype=np.float32)

    accumulate_values_by_region(
        totals,
        coverage,
        region_ids,
        values,
        nodata=-99999.0,
        allowed_region_ids=np.array([True, True, True]),
    )

    assert totals.tolist() == [0.0, 6.0, 4.0]
    assert coverage.tolist() == [0, 2, 1]


def test_working_age_is_derived_and_negative_cohort_residual_is_reconciled():
    total = np.array([100.0, 50.0])
    children = np.array([20.0, 20.0])
    older = np.array([10.0, 40.0])

    under_15, ages_15_64, over_64, factors = partition_population_cohorts(total, children, older)

    assert np.allclose(under_15 + ages_15_64 + over_64, total)
    assert np.all(ages_15_64 >= 0)
    assert factors.tolist() == [1.0, 5.0 / 6.0]
