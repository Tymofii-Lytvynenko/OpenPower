"""Build the separate World Bank PIP international poverty baseline for 2001."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "modules/base/data"
COUNTRY_IDS_PATH = DATA_DIR / "countries/countries.tsv"
SOURCE_RESPONSE_PATH = DATA_DIR / "sources/2001/pip_2021_ppp_3usd_2001.json"
SOURCE_LEDGER_PATH = DATA_DIR / "sources/2001/pip_2021_ppp_3usd_2001.tsv"
COUNTRY_EXTENSION_PATH = DATA_DIR / "countries/countries_poverty_international_2001.tsv"

SOURCE_NAME = "World Bank Poverty and Inequality Platform (PIP)"
API_ENDPOINT = "https://api.worldbank.org/pip/v1/pip"
SOURCE_VERSION = "20260922_2021_01_02_PROD"
REPORTING_YEAR = 2001
POVERTY_LINE = 3.0
PPP_YEAR = 2021

VALUE_FIELD = "historical_poverty_global_3usd_2021_ppp_pct"
ALTERNATE_VALUE_FIELD = f"{VALUE_FIELD}_alternate"
AVAILABILITY_FIELD = f"{VALUE_FIELD}_available"
ALTERNATE_AVAILABILITY_FIELD = f"{ALTERNATE_VALUE_FIELD}_available"
UNAVAILABLE_NOTE_FIELD = "historical_poverty_global_3usd_2021_ppp_unavailable_note"

LEDGER_COLUMNS = (
    "country_id",
    "country_name",
    "reporting_year",
    "survey_year",
    "reporting_level",
    "survey_coverage",
    "population_scope",
    "welfare_type",
    "poverty_line_usd_2021_ppp",
    "poverty_line_ppp_year",
    "headcount_proportion",
    "ppp_conversion_factor",
    "survey_acronym",
    "distribution_type",
    "estimation_type",
    "survey_comparability",
    "is_interpolated",
    "source_version",
    "retrieved_utc",
    "source_url",
    "source_note",
)

EXTENSION_COLUMNS = (
    "id",
    VALUE_FIELD,
    AVAILABILITY_FIELD,
    f"{VALUE_FIELD}_reference_year",
    f"{VALUE_FIELD}_survey_year",
    f"{VALUE_FIELD}_poverty_line_usd_per_person_per_day",
    f"{VALUE_FIELD}_ppp_year",
    f"{VALUE_FIELD}_population_scope",
    f"{VALUE_FIELD}_welfare_type",
    f"{VALUE_FIELD}_survey_acronym",
    f"{VALUE_FIELD}_survey_coverage",
    f"{VALUE_FIELD}_reporting_level",
    f"{VALUE_FIELD}_distribution_type",
    f"{VALUE_FIELD}_estimation_type",
    f"{VALUE_FIELD}_survey_comparability",
    f"{VALUE_FIELD}_ppp_conversion_factor",
    f"{VALUE_FIELD}_source_version",
    f"{VALUE_FIELD}_retrieved_utc",
    f"{VALUE_FIELD}_source_url",
    f"{VALUE_FIELD}_source_note",
    ALTERNATE_VALUE_FIELD,
    ALTERNATE_AVAILABILITY_FIELD,
    f"{ALTERNATE_VALUE_FIELD}_survey_year",
    f"{ALTERNATE_VALUE_FIELD}_welfare_type",
    f"{ALTERNATE_VALUE_FIELD}_survey_acronym",
    f"{ALTERNATE_VALUE_FIELD}_source_url",
    UNAVAILABLE_NOTE_FIELD,
)


def read_country_ids(path: Path = COUNTRY_IDS_PATH) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        country_ids = [
            str(row.get("id") or "").strip().upper()
            for row in csv.DictReader(stream, delimiter="\t")
        ]
    if not country_ids or any(not country_id for country_id in country_ids):
        raise ValueError(f"Country roster has empty IDs: {path}")
    if len(set(country_ids)) != len(country_ids):
        raise ValueError(f"Country roster has duplicate IDs: {path}")
    return country_ids


def read_source_snapshot(path: Path = SOURCE_RESPONSE_PATH) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("source") != SOURCE_NAME:
        raise ValueError(f"Unexpected PIP source in snapshot: {path}")
    if payload.get("version") != SOURCE_VERSION:
        raise ValueError(f"Unexpected PIP version in snapshot: {path}")
    if payload.get("poverty_line_usd_per_person_per_day_2021_ppp") != POVERTY_LINE:
        raise ValueError(f"Unexpected PIP international poverty line: {path}")
    query = payload.get("query") or {}
    if (
        query.get("reporting_year") != REPORTING_YEAR
        or query.get("fill_gaps") is not False
        or query.get("reporting_level") != "national"
    ):
        raise ValueError(
            f"Snapshot query is not exact-year national survey data: {path}"
        )
    return payload


def _finite_number(value, *, field: str, row: dict) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"Invalid {field} for {row.get('country_code')}") from error
    if not math.isfinite(number):
        raise ValueError(f"Non-finite {field} for {row.get('country_code')}")
    return number


def _source_url(country_id: str) -> str:
    return (
        f"{API_ENDPOINT}?country={country_id}&year={REPORTING_YEAR}"
        f"&format=json&fill_gaps=FALSE&version={SOURCE_VERSION}"
        f"&povline={POVERTY_LINE:g}&reporting_level=national"
    )


def read_survey_records(
    country_ids: list[str], path: Path = SOURCE_RESPONSE_PATH
) -> tuple[dict[str, tuple[dict, dict | None]], dict[str, str]]:
    payload = read_source_snapshot(path)
    allowed_ids = set(country_ids)
    grouped: dict[str, list[dict]] = {}
    for row in payload.get("records") or []:
        country_id = str(row.get("country_code") or "").strip().upper()
        if country_id not in allowed_ids:
            raise ValueError(f"Unknown PIP country ID {country_id!r}")
        if int(row.get("reporting_year")) != REPORTING_YEAR:
            raise ValueError(f"Unexpected reporting year for {country_id}")
        survey_year = _finite_number(
            row.get("survey_year"), field="survey_year", row=row
        )
        if not REPORTING_YEAR <= survey_year < REPORTING_YEAR + 1:
            raise ValueError(
                f"Survey year is outside 2001 for {country_id}: {survey_year}"
            )
        if str(row.get("reporting_level") or "").strip().lower() != "national":
            raise ValueError(f"Non-national PIP record for {country_id}")
        if str(row.get("survey_coverage") or "").strip().lower() != "national":
            raise ValueError(f"PIP record is not nationally covered for {country_id}")
        if row.get("is_interpolated") is not False:
            raise ValueError(
                f"Interpolated or unclassified PIP record for {country_id}"
            )
        if str(row.get("estimation_type") or "").strip().lower() != "survey":
            raise ValueError(f"Non-survey estimate returned for {country_id}")
        if (
            _finite_number(row.get("poverty_line"), field="poverty_line", row=row)
            != POVERTY_LINE
        ):
            raise ValueError(f"Unexpected poverty line for {country_id}")
        headcount = _finite_number(row.get("headcount"), field="headcount", row=row)
        if not 0 <= headcount <= 1:
            raise ValueError(f"PIP headcount is outside [0, 1] for {country_id}")
        ppp = _finite_number(row.get("ppp"), field="ppp", row=row)
        if ppp <= 0:
            raise ValueError(f"Invalid PIP PPP conversion factor for {country_id}")
        if not row.get("survey_acronym") or row.get("welfare_type") not in {
            "income",
            "consumption",
        }:
            raise ValueError(f"Missing survey or welfare metadata for {country_id}")
        grouped.setdefault(country_id, []).append(row)

    result: dict[str, tuple[dict, dict | None]] = {}
    for country_id, records in grouped.items():
        if len(records) > 2:
            raise ValueError(
                f"More than two PIP welfare records returned for {country_id}"
            )
        # PIP sometimes reports both income and consumption from one survey; keep both.
        records = sorted(
            records,
            key=lambda row: (
                str(row.get("welfare_type") or "").lower() == "consumption",
                str(row.get("survey_acronym") or ""),
            ),
            reverse=True,
        )
        if len(records) == 2 and records[0].get("welfare_type") == records[1].get(
            "welfare_type"
        ):
            raise ValueError(
                f"Ambiguous duplicate PIP welfare records for {country_id}"
            )
        result[country_id] = (records[0], records[1] if len(records) == 2 else None)

    unsupported_codes = {
        str(country_id).strip().upper()
        for country_id in payload.get("codes_unsupported") or []
    }
    unavailable_notes = {}
    for country_id in country_ids:
        if country_id in result:
            continue
        if country_id in unsupported_codes:
            unavailable_notes[country_id] = (
                "Game country code is not listed by the PIP API."
            )
        else:
            unavailable_notes[country_id] = (
                "No exact-year, national survey record was returned by this PIP vintage."
            )
    return result, unavailable_notes


def _fmt(value, precision: str = ".12g") -> str:
    return "" if value is None else format(value, precision)


def source_note(row: dict, *, alternate: bool = False) -> str:
    selected_text = "alternate" if alternate else "primary"
    return (
        f"World Bank PIP {selected_text} survey-year record; reporting year 2001; "
        f"${POVERTY_LINE:g} per person per day in {PPP_YEAR} PPP; "
        f"{row['welfare_type']} welfare; {row['survey_coverage']} survey coverage. "
        "PIP headcount proportion is stored as percent. No gap filling or adjacent-year "
        "substitution was requested. The headcount covers people in households and is not "
        "reported as an age-specific rate. The published survey year and welfare type are retained."
    )


def write_source_ledger(
    country_records: dict[str, tuple[dict, dict | None]],
    retrieved_utc: str,
    path: Path = SOURCE_LEDGER_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=LEDGER_COLUMNS, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        for country_id in sorted(country_records):
            primary, alternate = country_records[country_id]
            for row, is_alternate in ((primary, False), (alternate, True)):
                if row is None:
                    continue
                writer.writerow(
                    {
                        "country_id": country_id,
                        "country_name": row.get("country_name") or "",
                        "reporting_year": REPORTING_YEAR,
                        "survey_year": _fmt(float(row["survey_year"])),
                        "reporting_level": row["reporting_level"],
                        "survey_coverage": row["survey_coverage"],
                        "population_scope": (
                            "Population living in households; PIP record is not age-disaggregated."
                        ),
                        "welfare_type": row["welfare_type"],
                        "poverty_line_usd_2021_ppp": _fmt(POVERTY_LINE),
                        "poverty_line_ppp_year": PPP_YEAR,
                        "headcount_proportion": _fmt(float(row["headcount"])),
                        "ppp_conversion_factor": _fmt(float(row["ppp"])),
                        "survey_acronym": row.get("survey_acronym") or "",
                        "distribution_type": row.get("distribution_type") or "",
                        "estimation_type": row.get("estimation_type") or "",
                        "survey_comparability": row.get("survey_comparability", ""),
                        "is_interpolated": str(
                            bool(row.get("is_interpolated"))
                        ).lower(),
                        "source_version": SOURCE_VERSION,
                        "retrieved_utc": retrieved_utc,
                        "source_url": _source_url(country_id),
                        "source_note": source_note(row, alternate=is_alternate),
                    }
                )


def write_country_extension(
    country_ids: list[str],
    records: dict[str, tuple[dict, dict | None]],
    unavailable_notes: dict[str, str],
    path: Path = COUNTRY_EXTENSION_PATH,
) -> None:
    payload = read_source_snapshot()
    retrieved_utc = str(payload.get("retrieved_utc") or "")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=EXTENSION_COLUMNS, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        for country_id in country_ids:
            primary_pair = records.get(country_id)
            row = {column: "" for column in EXTENSION_COLUMNS}
            row["id"] = country_id
            row[AVAILABILITY_FIELD] = "false"
            row[ALTERNATE_AVAILABILITY_FIELD] = "false"
            if primary_pair:
                primary, alternate = primary_pair
                headcount_pct = float(primary["headcount"]) * 100.0
                row[VALUE_FIELD] = _fmt(headcount_pct)
                row[AVAILABILITY_FIELD] = "true"
                row[f"{VALUE_FIELD}_reference_year"] = str(REPORTING_YEAR)
                row[f"{VALUE_FIELD}_survey_year"] = _fmt(float(primary["survey_year"]))
                row[f"{VALUE_FIELD}_poverty_line_usd_per_person_per_day"] = _fmt(
                    POVERTY_LINE
                )
                row[f"{VALUE_FIELD}_ppp_year"] = str(PPP_YEAR)
                row[f"{VALUE_FIELD}_population_scope"] = (
                    "Population living in households; PIP record is not age-disaggregated."
                )
                row[f"{VALUE_FIELD}_welfare_type"] = primary["welfare_type"]
                row[f"{VALUE_FIELD}_survey_acronym"] = (
                    primary.get("survey_acronym") or ""
                )
                row[f"{VALUE_FIELD}_survey_coverage"] = primary["survey_coverage"]
                row[f"{VALUE_FIELD}_reporting_level"] = primary["reporting_level"]
                row[f"{VALUE_FIELD}_distribution_type"] = (
                    primary.get("distribution_type") or ""
                )
                row[f"{VALUE_FIELD}_estimation_type"] = (
                    primary.get("estimation_type") or ""
                )
                row[f"{VALUE_FIELD}_survey_comparability"] = primary.get(
                    "survey_comparability", ""
                )
                row[f"{VALUE_FIELD}_ppp_conversion_factor"] = _fmt(
                    float(primary["ppp"])
                )
                row[f"{VALUE_FIELD}_source_version"] = SOURCE_VERSION
                row[f"{VALUE_FIELD}_retrieved_utc"] = retrieved_utc
                row[f"{VALUE_FIELD}_source_url"] = _source_url(country_id)
                row[f"{VALUE_FIELD}_source_note"] = source_note(primary)
                if alternate:
                    row[ALTERNATE_VALUE_FIELD] = _fmt(
                        float(alternate["headcount"]) * 100.0
                    )
                    row[ALTERNATE_AVAILABILITY_FIELD] = "true"
                    row[f"{ALTERNATE_VALUE_FIELD}_survey_year"] = _fmt(
                        float(alternate["survey_year"])
                    )
                    row[f"{ALTERNATE_VALUE_FIELD}_welfare_type"] = alternate[
                        "welfare_type"
                    ]
                    row[f"{ALTERNATE_VALUE_FIELD}_survey_acronym"] = (
                        alternate.get("survey_acronym") or ""
                    )
                    row[f"{ALTERNATE_VALUE_FIELD}_source_url"] = _source_url(country_id)
            else:
                row[UNAVAILABLE_NOTE_FIELD] = unavailable_notes[country_id]
            writer.writerow(row)


def _existing_extension_matches(path: Path) -> bool:
    country_ids = read_country_ids()
    records, unavailable_notes = read_survey_records(country_ids)
    expected = path.with_suffix(".expected.tsv")
    try:
        write_country_extension(country_ids, records, unavailable_notes, expected)
        return path.read_bytes() == expected.read_bytes()
    finally:
        expected.unlink(missing_ok=True)


def _existing_ledger_matches(
    country_records: dict[str, tuple[dict, dict | None]],
    retrieved_utc: str,
    path: Path = SOURCE_LEDGER_PATH,
) -> bool:
    expected = path.with_suffix(".expected.tsv")
    try:
        write_source_ledger(country_records, retrieved_utc, expected)
        return path.read_bytes() == expected.read_bytes()
    finally:
        expected.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check generated country data against the reviewed source snapshot.",
    )
    args = parser.parse_args()

    country_ids = read_country_ids()
    records, unavailable_notes = read_survey_records(country_ids)
    retrieved_utc = str(read_source_snapshot().get("retrieved_utc") or "")
    if args.check:
        if not _existing_extension_matches(
            COUNTRY_EXTENSION_PATH
        ) or not _existing_ledger_matches(records, retrieved_utc):
            raise SystemExit(
                "Generated country data does not match the source snapshot."
            )
        row_count = sum(
            1 + (alternate is not None) for _, alternate in records.values()
        )
        print(f"Validated {len(country_ids)} countries; {row_count} source rows.")
        return

    write_source_ledger(records, retrieved_utc)
    write_country_extension(country_ids, records, unavailable_notes)
    print(
        f"Wrote {COUNTRY_EXTENSION_PATH.relative_to(ROOT)} "
        f"({len(country_ids)} countries, {len(records)} with exact-year national surveys)."
    )


if __name__ == "__main__":
    main()
