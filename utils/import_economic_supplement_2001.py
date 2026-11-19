"""Build separate, source-specific 2001 country economic supplements."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "modules/base/data"
COUNTRY_IDS_PATH = DATA_DIR / "countries/countries.tsv"
SOURCE_LEDGER_PATH = DATA_DIR / "sources/2001/economic_supplement_2001.tsv"
COUNTRY_EXTENSION_PATH = DATA_DIR / "countries/countries_economic_supplement_2001.tsv"
SCENARIO_YEAR = 2001

FIELDS = {
    "historical_gdp_snaama_current_usd_2001": "current US$",
    "historical_gdp_per_capita_snaama_current_usd_2001": "current US$/person",
    "historical_cpi_inflation_source_supplement_pct_2001": "%/year or December-to-December",
    "historical_unemployment_reported_supplement_pct_2001": "% of labor force, source-defined coverage",
}
LEDGER_COLUMNS = (
    "country_id",
    "field",
    "scenario_year",
    "observation_year",
    "value",
    "unit",
    "series_id",
    "source_name",
    "source_release",
    "source_url",
    "source_note",
)
PROVENANCE_COLUMN = "historical_economic_supplement_provenance_json"


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


def read_supplement_records(
    country_ids: list[str], path: Path = SOURCE_LEDGER_PATH
) -> dict[str, dict[str, dict]]:
    allowed_ids = set(country_ids)
    records: dict[str, dict[str, dict]] = {country_id: {} for country_id in country_ids}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if tuple(reader.fieldnames or ()) != LEDGER_COLUMNS:
            raise ValueError(f"Unexpected source ledger columns: {path}")
        for line_number, row in enumerate(reader, start=2):
            country_id = str(row.get("country_id") or "").strip().upper()
            field = str(row.get("field") or "").strip()
            if country_id not in allowed_ids:
                raise ValueError(
                    f"Unknown country ID {country_id!r} at {path}:{line_number}"
                )
            if field not in FIELDS:
                raise ValueError(
                    f"Unsupported supplement field {field!r} at {path}:{line_number}"
                )
            try:
                scenario_year = int(row["scenario_year"])
                observation_year = int(row["observation_year"])
                value = float(row["value"])
            except (TypeError, ValueError, OverflowError) as error:
                raise ValueError(
                    f"Invalid year or value at {path}:{line_number}"
                ) from error
            if scenario_year != SCENARIO_YEAR or observation_year != SCENARIO_YEAR:
                raise ValueError(
                    f"Only exact 2001 observations are accepted at {path}:{line_number}"
                )
            if not math.isfinite(value):
                raise ValueError(f"Non-finite value at {path}:{line_number}")
            if country_id in records and field in records[country_id]:
                raise ValueError(f"Duplicate {field} observation for {country_id}")

            provenance = {
                "scenario_year": scenario_year,
                "observation_year": observation_year,
                "unit": str(row.get("unit") or "").strip(),
                "series_id": str(row.get("series_id") or "").strip(),
                "source": str(row.get("source_name") or "").strip(),
                "source_release": str(row.get("source_release") or "").strip(),
                "source_url": str(row.get("source_url") or "").strip(),
                "source_note": str(row.get("source_note") or "").strip(),
            }
            if any(
                not provenance[key]
                for key in (
                    "unit",
                    "series_id",
                    "source",
                    "source_release",
                    "source_url",
                    "source_note",
                )
            ):
                raise ValueError(f"Incomplete provenance at {path}:{line_number}")
            if not provenance["source_url"].startswith("https://"):
                raise ValueError(
                    f"Expected a direct HTTPS source URL at {path}:{line_number}"
                )

            records[country_id][field] = {"value": value, "provenance": provenance}
    return records


def write_country_extension(
    country_ids: list[str],
    records: dict[str, dict[str, dict]],
    path: Path = COUNTRY_EXTENSION_PATH,
) -> None:
    columns = ["id"]
    for field in FIELDS:
        columns.extend((field, f"{field}_available"))
    columns.append(PROVENANCE_COLUMN)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=columns, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        for country_id in country_ids:
            country_records = records.get(country_id, {})
            row = {"id": country_id}
            provenance = {}
            for field in FIELDS:
                observation = country_records.get(field)
                row[field] = format(observation["value"], ".15g") if observation else ""
                row[f"{field}_available"] = "true" if observation else "false"
                if observation:
                    provenance[field] = observation["provenance"]
            row[PROVENANCE_COLUMN] = json.dumps(
                provenance, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
            writer.writerow(row)


def main() -> None:
    country_ids = read_country_ids()
    records = read_supplement_records(country_ids)
    write_country_extension(country_ids, records)
    count = sum(len(country_records) for country_records in records.values())
    print(
        f"Wrote {COUNTRY_EXTENSION_PATH.relative_to(ROOT)} "
        f"({len(country_ids)} countries, {count} source-backed observations)"
    )


if __name__ == "__main__":
    main()
