import csv
import json

from utils.generate_economic_gameplay_proxies_2001 import (
    CPI,
    GDP,
    GDP_PER_CAPITA,
    LEDGER_OUTPUT_PATH,
    OUTPUT_PATH,
    UNEMPLOYMENT,
    generate_rows,
    render_ledger_tsv,
    render_tsv,
)


def test_macro_proxies_cover_only_unresolved_core_gaps_with_explicit_quality():
    rows = generate_rows()
    by_key = {(row["id"], row["target_field"]): row for row in rows}

    assert len(rows) == 16
    assert len(by_key) == len(rows)
    assert sum(row["available"] == "true" for row in rows) == 12
    assert sum(row["available"] == "false" for row in rows) == 4
    assert {key for key, row in by_key.items() if row["available"] == "false"} == {
        ("ATA", GDP),
        ("ATA", GDP_PER_CAPITA),
        ("ATA", CPI),
        ("ATA", UNEMPLOYMENT),
    }

    ssd_inputs = json.loads(by_key[("SSD", GDP_PER_CAPITA)]["source_inputs_json"])
    assert ssd_inputs[0]["country_id"] == "SDN"
    assert ssd_inputs[0]["value"] == by_key[("SSD", GDP_PER_CAPITA)]["value"]
    assert by_key[("SSD", GDP)]["confidence"] == "very_low"
    assert by_key[("VAT", GDP)]["confidence"] == "very_low"
    assert by_key[("PRK", CPI)]["confidence"] == "very_low"
    assert by_key[("SOM", CPI)]["confidence"] == "very_low"
    assert by_key[("AND", UNEMPLOYMENT)]["value"] == "0.000000"
    assert by_key[("AND", UNEMPLOYMENT)]["observation_year"] == ""
    assert (
        "not an observed 2001 ILO unemployment rate"
        in by_key[("AND", UNEMPLOYMENT)]["source_note"]
    )

    for row in rows:
        if row["available"] != "true":
            continue
        assert row["estimate_type"] == "gameplay_proxy"
        assert row["source_inputs_json"]
        assert row["source_urls"]
        assert (
            "proxy" in row["source_note"].lower()
            or "prior" in row["source_note"].lower()
        )
        if row["target_field"] == CPI:
            assert float(row["value"]) > -100
        elif row["target_field"] in {GDP, GDP_PER_CAPITA}:
            assert float(row["value"]) > 0
        elif row["target_field"] == UNEMPLOYMENT:
            assert 0 <= float(row["value"]) <= 100


def test_gameplay_proxy_table_is_deterministic_and_keeps_core_fields_separate():
    rows = generate_rows()
    expected = render_tsv(rows)
    checked_in = OUTPUT_PATH.read_text(encoding="utf-8")

    assert checked_in == expected
    with OUTPUT_PATH.open(encoding="utf-8", newline="") as stream:
        reread = list(csv.DictReader(stream, delimiter="\t"))
    assert len(reread) == len({row["id"] for row in rows})
    assert len({row["id"] for row in reread}) == len(reread)
    assert all("_gameplay_proxy_" in column for column in reread[0] if column != "id")
    assert render_tsv(generate_rows()) == expected

    ledger_expected = render_ledger_tsv(rows)
    assert LEDGER_OUTPUT_PATH.read_text(encoding="utf-8") == ledger_expected
    with LEDGER_OUTPUT_PATH.open(encoding="utf-8", newline="") as stream:
        ledger = list(csv.DictReader(stream, delimiter="\t"))
    assert len(ledger) == 16

    input_values = json.loads(
        next(
            row["source_inputs_json"]
            for row in rows
            if row["id"] == "SSD" and row["target_field"] == GDP
        )
    )
    assert input_values[0]["country_id"] == "SDN"
    assert input_values[1]["country_id"] == "SSD"
    assert input_values[1]["population_2001"] > 0
