"""Generate a unique-country extension for scoped Palestinian reserve context."""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "modules/base/data"
SOURCE_PATH = DATA_DIR / "sources/2001/palestinian_natural_reserves_2001_candidate.tsv"
OUTPUT_PATH = DATA_DIR / "countries/countries_palestinian_reserves_context_2001.tsv"

OBSERVATION_YEARS = ("2000", "2001")
SOURCE_COLUMNS = (
    "reported_period",
    "precision",
    "source_name",
    "source_url",
    "source_location",
    "geographic_scope",
    "coverage_limit",
    "handling_note",
)
OUTPUT_COLUMNS = ("id",) + tuple(
    column
    for year in OBSERVATION_YEARS
    for column in (
        f"countryinfo_pna_west_bank_natural_reserves_{year}_area_km2",
        f"countryinfo_pna_west_bank_natural_reserves_{year}_area_km2_available",
        *(
            f"countryinfo_pna_west_bank_natural_reserves_{year}_area_km2_{source}"
            for source in SOURCE_COLUMNS
        ),
    )
)


def _read_tsv(path: Path = SOURCE_PATH) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def build_rows(source_rows: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    rows_by_year: dict[str, dict[str, str]] = {}
    for source in _read_tsv() if source_rows is None else source_rows:
        if source.get("country_id", "").strip().upper() != "PSE":
            raise ValueError("Reserve context extension accepts only PSE records.")
        if source.get("scenario_year") != "2001":
            raise ValueError(
                "Palestinian reserve candidates must retain the 2001 scenario year."
            )
        if (
            source.get("indicator") != "natural_reserves_area"
            or source.get("unit") != "km2"
        ):
            raise ValueError("Unexpected Palestinian reserve candidate measure.")

        year = source.get("observation_year", "").strip()
        if year not in OBSERVATION_YEARS or year in rows_by_year:
            raise ValueError(
                f"Missing, unexpected, or duplicate observation year: {year!r}"
            )
        required = (
            "value",
            "reported_period",
            "precision",
            "source_name",
            "source_url",
            "source_location",
            "geographic_scope",
            "coverage_limit",
            "handling_note",
        )
        if any(not source.get(field, "").strip() for field in required):
            raise ValueError(
                f"Reserve candidate {year} is missing required source context."
            )
        rows_by_year[year] = source

    if set(rows_by_year) != set(OBSERVATION_YEARS):
        raise ValueError(
            f"Expected reserve candidate years {OBSERVATION_YEARS}, got {tuple(sorted(rows_by_year))}."
        )

    output = {column: "" for column in OUTPUT_COLUMNS}
    output["id"] = "PSE"
    for year, source in rows_by_year.items():
        prefix = f"countryinfo_pna_west_bank_natural_reserves_{year}_area_km2"
        output[prefix] = source["value"].strip()
        output[f"{prefix}_available"] = "true"
        for source_column in SOURCE_COLUMNS:
            output[f"{prefix}_{source_column}"] = source[source_column].strip()
    return [output]


def render_tsv(rows: list[dict[str, str]]) -> str:
    if len(rows) != 1 or rows[0].get("id") != "PSE":
        raise ValueError("The reserve extension must contain one unique PSE row.")
    if len(set(OUTPUT_COLUMNS)) != len(OUTPUT_COLUMNS):
        raise ValueError(
            "The reserve extension schema contains duplicate column names."
        )
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
        help="verify the checked-in extension matches the source ledger",
    )
    args = parser.parse_args(argv)
    output = render_tsv(build_rows())
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
