import csv
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "modules/base/data/sources/2001/area_source_conflicts_2001.tsv"


def _read_ledger():
    with LEDGER.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _decimal(value):
    return Decimal(value) if value else None


def test_ledger_covers_country_rows_and_keeps_composite_yugoslavia_separate():
    rows = _read_ledger()
    country_rows = [row for row in rows if row["row_kind"] == "country"]
    composite_rows = [row for row in rows if row["row_kind"] == "unmapped_cia_composite_profile"]

    assert len(country_rows) == 199
    assert len({row["country_id"] for row in country_rows}) == 199
    assert len(composite_rows) == 1
    assert composite_rows[0]["cia_profile_name"] == "Yugoslavia"
    assert composite_rows[0]["cia_total_km2"] == "102350"
    assert composite_rows[0]["cia_land_km2"] == "102136"
    assert composite_rows[0]["cia_water_km2"] == "214"
    assert composite_rows[0]["cia_water_minus_wdi_surface_land_km2"] == ""


def test_wdi_residual_and_cia_tuple_arithmetic_are_reproducible():
    rows = [row for row in _read_ledger() if row["row_kind"] == "country"]
    wdi_pairs = 0
    cia_trios = 0
    comparisons = 0
    material_conflicts = 0
    large_conflicts = 0

    for row in rows:
        surface = _decimal(row["wdi_surface_km2"])
        land = _decimal(row["wdi_land_km2"])
        wdi_residual = _decimal(row["wdi_surface_minus_land_km2"])
        if surface is not None and land is not None:
            wdi_pairs += 1
            assert wdi_residual == surface - land

        cia_total = _decimal(row["cia_total_km2"])
        cia_land = _decimal(row["cia_land_km2"])
        cia_water = _decimal(row["cia_water_km2"])
        if cia_total is not None and cia_land is not None and cia_water is not None:
            cia_trios += 1
            assert _decimal(row["cia_total_minus_land_and_water_km2"]) == 0
            assert cia_total == cia_land + cia_water

        delta = _decimal(row["cia_water_minus_wdi_surface_land_km2"])
        if delta is not None:
            comparisons += 1
            assert cia_water is not None
            assert wdi_residual is not None
            assert delta == cia_water - wdi_residual
            absolute_delta = abs(delta)
            assert _decimal(row["absolute_delta_km2"]) == absolute_delta
            is_material = absolute_delta > 100
            assert row["absolute_delta_over_100_km2"] == str(is_material).lower()
            assert row["comparison_classification"] == (
                "material_conflict_abs_delta_gt_100_km2"
                if is_material
                else "within_100_km2_not_proof_of_equivalence"
            )
            material_conflicts += is_material
            large_conflicts += absolute_delta > 1000
        else:
            assert row["absolute_delta_km2"] == ""
            assert row["absolute_delta_over_100_km2"] == ""

    assert wdi_pairs == 191
    assert cia_trios == 193
    assert comparisons == 190
    assert material_conflicts == 94
    assert large_conflicts == 60


def test_published_examples_preserve_signed_delta_direction():
    rows = {row["country_id"]: row for row in _read_ledger() if row["row_kind"] == "country"}

    assert rows["CAN"]["wdi_surface_minus_land_km2"] == "6674910"
    assert rows["CAN"]["cia_water_km2"] == "755170"
    assert rows["CAN"]["cia_water_minus_wdi_surface_land_km2"] == "-5919740"
    assert rows["RUS"]["wdi_surface_minus_land_km2"] == "717800"
    assert rows["RUS"]["cia_water_minus_wdi_surface_land_km2"] == "-638400"
    assert rows["UKR"]["wdi_surface_minus_land_km2"] == "24200"
    assert rows["UKR"]["cia_water_minus_wdi_surface_land_km2"] == "-24200"


def test_factbook_nonseparate_entities_are_never_allocated_as_country_tuples():
    rows = {row["country_id"]: row for row in _read_ledger() if row["row_kind"] == "country"}

    for country_id in ("KOS", "MNE", "SRB", "SSD", "TLS"):
        row = rows[country_id]
        assert row["cia_scope_match_status"] == "not_separate_in_2001"
        assert row["cia_total_km2"] == ""
        assert row["cia_land_km2"] == ""
        assert row["cia_water_km2"] == ""

    assert rows["SDN"]["cia_scope_match_status"] == "exact_profile_match"
    assert rows["SDN"]["cia_profile_name"] == "Sudan"
    assert rows["SSD"]["cia_profile_name"] == "Sudan"
    assert rows["SSD"]["cia_total_km2"] == ""

    antarctica = rows["ATA"]
    assert antarctica["cia_total_km2"] == "14000000"
    assert antarctica["cia_land_km2"] == "14000000"
    assert antarctica["cia_water_km2"] == ""
