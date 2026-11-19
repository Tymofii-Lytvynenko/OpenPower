"""Generate namespaced scenario estimates for the 2001 Other land data gaps."""

from __future__ import annotations

import argparse
import csv
import io
import sys
import zipfile
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "modules/base/data"
SOURCE_INPUT_PATH = DATA_DIR / "sources/2001/other_land_supplement_inputs_2001.tsv"
FAOSTAT_PATH = DATA_DIR / "sources/2001/faostat_land_use_2026.zip"
OUTPUT_PATH = DATA_DIR / "countries/countries_other_land_supplement_2001.tsv"

FAOSTAT_AREA_CODE = "186"
FAOSTAT_AREA_NAME = "Serbia and Montenegro"
FAOSTAT_YEAR = "2001"
FAOSTAT_ITEMS = {
    "6601": ("FAOSTAT_SCG_LAND", "land_area"),
    "6610": ("FAOSTAT_SCG_AGRICULTURE", "agricultural_land"),
    "6646": ("FAOSTAT_SCG_FOREST", "forest_land"),
    "6670": ("FAOSTAT_SCG_OTHER", "other_land"),
}

OUTPUT_COLUMNS = (
    "id",
    "scenario_other_land_2001_area_ha",
    "scenario_other_land_2001_pct",
    "scenario_other_land_2001_available",
    "scenario_other_land_2001_status",
    "scenario_other_land_2001_reference_period",
    "scenario_other_land_2001_method",
    "scenario_other_land_2001_quality",
    "scenario_other_land_2001_source_flag",
    "scenario_other_land_2001_scope",
    "scenario_other_land_2001_source_urls",
    "scenario_other_land_2001_source_note",
    "scenario_cia_land_use_other_2001_pct",
    "scenario_cia_land_use_other_2001_available",
    "scenario_cia_land_use_other_2001_reference_year",
    "scenario_cia_land_use_other_2001_scope",
    "scenario_cia_land_use_other_2001_method",
    "scenario_cia_land_use_other_2001_source_url",
    "scenario_cia_land_use_other_2001_source_note",
)

FAOSTAT_URL = "https://www.fao.org/faostat/en/#data/RL"
MNE_FRA_URL = "https://www.fao.org/4/al572E/al572E.pdf"
MNE_AGRICULTURE_URL = (
    "https://documents1.worldbank.org/curated/en/818271468760747059/pdf/"
    "288030YF0Ag0sector0review01public1.pdf"
)
CIA_FACTBOOK_URL = "https://www.gutenberg.org/ebooks/27638"


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def _decimal(value: str | int | Decimal | None) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError(f"Expected a decimal value, got {value!r}") from exc
    if not number.is_finite():
        raise ValueError(f"Expected a finite number, got {value!r}")
    return number


def _format_decimal(value: Decimal, places: int = 4) -> str:
    quantum = Decimal(1).scaleb(-places)
    return str(value.quantize(quantum, rounding=ROUND_HALF_UP))


def _format_area(value: Decimal) -> str:
    if value == value.to_integral_value():
        return format(value.quantize(Decimal("1")), "f")
    return format(value.normalize(), "f")


def _unique_urls(*urls: str) -> str:
    return ";".join(dict.fromkeys(url for url in urls if url))


def _load_input_observations(
    path: Path = SOURCE_INPUT_PATH,
) -> dict[str, dict[str, str]]:
    observations: dict[str, dict[str, str]] = {}
    for row in _read_tsv(path):
        record_id = row["record_id"].strip()
        if not record_id or record_id in observations:
            raise ValueError(f"Missing or duplicate source record id: {record_id!r}")
        observations[record_id] = row
    return observations


def _read_faostat_scg(path: Path = FAOSTAT_PATH) -> dict[str, tuple[Decimal, str]]:
    with zipfile.ZipFile(path) as archive:
        member = "Inputs_LandUse_E_All_Data_(Normalized).csv"
        with archive.open(member) as raw_stream:
            text_stream = io.TextIOWrapper(raw_stream, encoding="utf-8-sig", newline="")
            rows = csv.DictReader(text_stream)
            values: dict[str, tuple[Decimal, str]] = {}
            for row in rows:
                item_code = row["Item Code"]
                if (
                    row["Area Code"] != FAOSTAT_AREA_CODE
                    or row["Area"] != FAOSTAT_AREA_NAME
                    or row["Year"] != FAOSTAT_YEAR
                    or row["Element Code"] != "5110"
                    or item_code not in FAOSTAT_ITEMS
                ):
                    continue
                _, measure = FAOSTAT_ITEMS[item_code]
                if measure in values:
                    raise ValueError(f"Duplicate FAOSTAT value for {measure}")
                thousand_hectares = _decimal(row["Value"])
                if thousand_hectares is None:
                    raise ValueError(f"Missing FAOSTAT value for {measure}")
                values[measure] = (thousand_hectares * 1000, row["Flag"])

    expected = {measure for _, measure in FAOSTAT_ITEMS.values()}
    if set(values) != expected:
        raise ValueError(f"Incomplete FAOSTAT source values: {sorted(values)}")
    return values


def _source_value(
    observations: dict[str, dict[str, str]], record_id: str
) -> tuple[Decimal, dict[str, str]]:
    try:
        row = observations[record_id]
    except KeyError as exc:
        raise ValueError(f"Missing source observation {record_id}") from exc
    value = _decimal(row["value"])
    if value is None:
        raise ValueError(f"Source observation {record_id} has no value")
    return value, row


def _verify_faostat_ledger(
    observations: dict[str, dict[str, str]],
    faostat: dict[str, tuple[Decimal, str]],
) -> None:
    for item_code, (record_id, measure) in FAOSTAT_ITEMS.items():
        ledger_value, ledger_row = _source_value(observations, record_id)
        archived_value, archived_flag = faostat[measure]
        if ledger_value != archived_value or ledger_row["source_flag"] != archived_flag:
            raise ValueError(
                f"Source ledger does not match cached FAOSTAT item {item_code}"
            )

    land = faostat["land_area"][0]
    agriculture = faostat["agricultural_land"][0]
    forest = faostat["forest_land"][0]
    other = faostat["other_land"][0]
    if land - agriculture - forest != other:
        raise ValueError(
            "FAOSTAT Other land does not reconcile to its component series"
        )


def _base_row(country_id: str) -> dict[str, str]:
    return {column: "" for column in OUTPUT_COLUMNS} | {"id": country_id}


def _unavailable_row(
    country_id: str,
    *,
    status: str,
    reference_period: str,
    scope: str,
    source_urls: str,
    source_note: str,
    quality: str = "unavailable",
) -> dict[str, str]:
    row = _base_row(country_id)
    row.update(
        {
            "scenario_other_land_2001_available": "false",
            "scenario_other_land_2001_status": status,
            "scenario_other_land_2001_reference_period": reference_period,
            "scenario_other_land_2001_quality": quality,
            "scenario_other_land_2001_scope": scope,
            "scenario_other_land_2001_source_urls": source_urls,
            "scenario_other_land_2001_source_note": source_note,
            "scenario_cia_land_use_other_2001_available": "false",
        }
    )
    return row


def generate_rows(
    *,
    input_path: Path = SOURCE_INPUT_PATH,
    faostat_path: Path = FAOSTAT_PATH,
) -> list[dict[str, str]]:
    observations = _load_input_observations(input_path)
    faostat = _read_faostat_scg(faostat_path)
    _verify_faostat_ledger(observations, faostat)

    mne_land, mne_land_source = _source_value(observations, "MNE_LAND")
    mne_agriculture, mne_ag_source = _source_value(observations, "MNE_AGRICULTURE")
    mne_forest, mne_forest_source = _source_value(observations, "MNE_FOREST")
    mne_other = mne_land - mne_agriculture - mne_forest
    if mne_other < 0:
        raise ValueError("Montenegro source categories exceed its land area")

    srb_land = faostat["land_area"][0] - mne_land
    srb_other = faostat["other_land"][0] - mne_other
    if srb_land <= 0 or srb_other < 0:
        raise ValueError("Derived Serbia scope has invalid land or Other land area")

    mne_note = (
        "Low-confidence residual estimate: land area (1,345,000 ha) and forest land "
        "(543,000 ha) are FAO FRA observations for 2000; agricultural land (517,830 ha) "
        "is from a World Bank 2003 annex citing the 2001 national yearbooks but does not "
        "state this row's observation year. Other land = land area - agricultural land - "
        "forest land = 284,170 ha. FAO FRA's forestry-category Other land value is not "
        "used because it follows a different classification."
    )
    mne_row = _base_row("MNE")
    mne_row.update(
        {
            "scenario_other_land_2001_area_ha": _format_area(mne_other),
            "scenario_other_land_2001_pct": _format_decimal(mne_other * 100 / mne_land),
            "scenario_other_land_2001_available": "true",
            "scenario_other_land_2001_status": "low_confidence_derived_estimate",
            "scenario_other_land_2001_reference_period": (
                "Land and forest: 2000; agricultural-land row year unspecified "
                "(World Bank annex cites 2001 yearbooks)"
            ),
            "scenario_other_land_2001_method": (
                "FAO land area - national agricultural land - FAO forest land"
            ),
            "scenario_other_land_2001_quality": "low",
            "scenario_other_land_2001_source_flag": "derived_from_adjacent_period_sources",
            "scenario_other_land_2001_scope": "Montenegro national territory",
            "scenario_other_land_2001_source_urls": _unique_urls(
                mne_land_source["source_url"],
                mne_ag_source["source_url"],
                mne_forest_source["source_url"],
            ),
            "scenario_other_land_2001_source_note": mne_note,
            "scenario_cia_land_use_other_2001_available": "false",
        }
    )

    srb_note = (
        "Low-confidence scope split of the exact 2001 FAOSTAT Serbia-and-Montenegro "
        "aggregate. Subtract the Montenegro residual estimate (284,170 ha) from the "
        "combined Other land value (1,439,020 ha), and subtract Montenegro land area "
        "(1,345,000 ha) from combined land area (10,200,000 ha). This gives Serbia, "
        "including Kosovo and excluding Montenegro: 1,154,850 ha / 8,855,000 ha = "
        f"{_format_decimal(srb_other * 100 / srb_land)}%. The FAOSTAT forest and Other "
        "land inputs carry flag I (imputed by a receiving agency); the split inherits "
        "that source limitation and the mixed 2000/2001 MNE inputs. Kosovo is not "
        "independently split from this Serbia scope."
    )
    srb_row = _base_row("SRB")
    srb_row.update(
        {
            "scenario_other_land_2001_area_ha": _format_area(srb_other),
            "scenario_other_land_2001_pct": _format_decimal(srb_other * 100 / srb_land),
            "scenario_other_land_2001_available": "true",
            "scenario_other_land_2001_status": "low_confidence_derived_aggregate_split",
            "scenario_other_land_2001_reference_period": (
                "FAOSTAT aggregate: 2001; Montenegro deduction: 2000 and "
                "agricultural-land year unspecified"
            ),
            "scenario_other_land_2001_method": (
                "FAOSTAT combined Other land and land area minus Montenegro residual "
                "and land area"
            ),
            "scenario_other_land_2001_quality": "low",
            "scenario_other_land_2001_source_flag": "I-derived",
            "scenario_other_land_2001_scope": "Serbia including Kosovo; Montenegro excluded",
            "scenario_other_land_2001_source_urls": _unique_urls(
                FAOSTAT_URL,
                mne_land_source["source_url"],
                mne_ag_source["source_url"],
                mne_forest_source["source_url"],
            ),
            "scenario_other_land_2001_source_note": srb_note,
            "scenario_cia_land_use_other_2001_available": "false",
        }
    )

    unavailable = []
    for country_id, status, note_key in (
        ("ATA", "not_applicable", "ATA_STATUS"),
        ("KOS", "territory_not_independently_split", "KOS_STATUS"),
        ("SSD", "territory_part_of_sudan_2001", "SSD_STATUS"),
        ("TWN", "no_faostat_comparable_agricultural_land_series", "TWN_STATUS"),
    ):
        source = observations[note_key]
        unavailable.append(
            _unavailable_row(
                country_id,
                status=status,
                reference_period=source["observation_year"],
                scope=source["source_scope"],
                source_urls=source["source_url"],
                source_note=source["note"],
                quality="not_applicable" if country_id == "ATA" else "unavailable",
            )
        )

    taiwan = next(row for row in unavailable if row["id"] == "TWN")
    cia_other, cia_source = _source_value(observations, "TWN_CIA_OTHER")
    taiwan.update(
        {
            "scenario_cia_land_use_other_2001_pct": _format_decimal(cia_other, 2),
            "scenario_cia_land_use_other_2001_available": "true",
            "scenario_cia_land_use_other_2001_reference_year": "2001",
            "scenario_cia_land_use_other_2001_scope": cia_source["source_scope"],
            "scenario_cia_land_use_other_2001_method": (
                "Direct CIA Factbook land-use `other` estimate; kept separate from "
                "FAOSTAT Other land"
            ),
            "scenario_cia_land_use_other_2001_source_url": cia_source["source_url"],
            "scenario_cia_land_use_other_2001_source_note": cia_source["note"],
        }
    )

    kosovo = next(row for row in unavailable if row["id"] == "KOS")
    kosovo_other, kosovo_source = _source_value(observations, "KOS_CIA_OTHER")
    kosovo.update(
        {
            "scenario_cia_land_use_other_2001_pct": _format_decimal(kosovo_other, 2),
            "scenario_cia_land_use_other_2001_available": "true",
            "scenario_cia_land_use_other_2001_reference_year": "2001",
            "scenario_cia_land_use_other_2001_scope": kosovo_source["source_scope"],
            "scenario_cia_land_use_other_2001_method": (
                "Direct CIA Factbook land-use `other` estimate; kept separate from "
                "FAOSTAT Other land"
            ),
            "scenario_cia_land_use_other_2001_source_url": kosovo_source["source_url"],
            "scenario_cia_land_use_other_2001_source_note": kosovo_source["note"],
        }
    )

    rows = [mne_row, srb_row, *unavailable]
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Generated duplicate country rows")
    return sorted(rows, key=lambda row: row["id"])


def render_tsv(rows: list[dict[str, str]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=OUTPUT_COLUMNS,
        delimiter="\t",
        lineterminator="\n",
        extrasaction="raise",
    )
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the generated table matches the checked-in output",
    )
    args = parser.parse_args(argv)
    output = render_tsv(generate_rows())
    if args.check:
        if (
            not OUTPUT_PATH.exists()
            or OUTPUT_PATH.read_text(encoding="utf-8") != output
        ):
            print(f"Generated data differ from {OUTPUT_PATH}", file=sys.stderr)
            return 1
        print(f"Verified {OUTPUT_PATH}")
        return 0
    OUTPUT_PATH.write_text(output, encoding="utf-8", newline="")
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
