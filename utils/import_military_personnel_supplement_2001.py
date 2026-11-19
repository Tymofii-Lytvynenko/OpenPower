from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
MILITARY_PATH = ROOT / "modules" / "base" / "data" / "countries" / "countries_mil.tsv"
SUPPLEMENT_PATH = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "military_personnel_supplemental_2001.tsv"


def apply_personnel_supplement(
    military_rows: Iterable[dict[str, str]],
    supplement_rows: Iterable[dict[str, str]],
) -> list[dict[str, str]]:
    """Apply cited personnel observations without changing equipment-role inventories."""
    output_rows = [dict(row) for row in military_rows]
    row_by_country: dict[str, dict[str, str]] = {}
    for row in output_rows:
        country_id = str(row.get("id", "")).strip().upper()
        if not country_id or country_id in row_by_country:
            raise ValueError(f"Military inventory has a missing or duplicate country id: {country_id!r}.")
        row_by_country[country_id] = row

    seen_supplements: set[tuple[str, str]] = set()
    for supplement in supplement_rows:
        country_id = str(supplement.get("country_id", "")).strip().upper()
        field = str(supplement.get("field", "")).strip()
        key = (country_id, field)
        if key in seen_supplements:
            raise ValueError(f"Duplicate military personnel supplement for {country_id}/{field}.")
        seen_supplements.add(key)
        if field != "military_count" or str(supplement.get("scenario_year", "")) != "2001":
            raise ValueError(f"Unsupported military supplement contract for {country_id}/{field}.")
        for year_field in ("observation_year", "publication_year"):
            year_value = str(supplement.get(year_field, ""))
            if len(year_value) != 4 or not year_value.isdigit():
                raise ValueError(f"Military supplement for {country_id} needs a four-digit {year_field}.")
        if not all(
            supplement.get(column)
            for column in (
                "evidence_kind",
                "confidence",
                "source_name",
                "source_reference",
                "source_url",
                "source_scope",
                "method",
                "source_note",
            )
        ):
            raise ValueError(f"Military supplement for {country_id} is missing source attribution.")
        if country_id not in row_by_country:
            raise ValueError(f"Military supplement country {country_id} is not in countries_mil.tsv.")
        try:
            value = int(str(supplement.get("value", "")))
        except ValueError as exc:
            raise ValueError(f"Military supplement value for {country_id} must be an integer.") from exc
        if value < 0:
            raise ValueError(f"Military supplement value for {country_id} cannot be negative.")
        row_by_country[country_id][field] = str(value)

    return output_rows


def main() -> None:
    with SUPPLEMENT_PATH.open("r", encoding="utf-8-sig", newline="") as source:
        supplement_rows = list(csv.DictReader(source, delimiter="\t"))
    with MILITARY_PATH.open("r", encoding="utf-8-sig", newline="") as source:
        military_rows = list(csv.DictReader(source, delimiter="\t"))
        field_names = list(military_rows[0]) if military_rows else []

    output_rows = apply_personnel_supplement(military_rows, supplement_rows)
    with MILITARY_PATH.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=field_names, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Applied {len(supplement_rows)} cited military personnel supplements.")


if __name__ == "__main__":
    main()
