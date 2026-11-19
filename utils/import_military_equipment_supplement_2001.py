from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
MILITARY_PATH = ROOT / "modules" / "base" / "data" / "countries" / "countries_mil.tsv"
SUPPLEMENT_PATH = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "military_equipment_inventory_supplement_2001.tsv"
EQUIPMENT_FIELDS = frozenset(
    f"military_{role}_quantity_2001"
    for role in (
        "infantry",
        "infantry_vehicles",
        "air_defense",
        "mobile_launchers",
        "tanks",
        "artillery",
        "attack_helicopters",
        "transport_helicopters",
        "anti_submarine_helicopters",
        "fighters",
        "attack_aircraft",
        "bombers",
        "patrol_craft",
        "corvettes",
        "frigates",
        "destroyers",
        "attack_submarines",
        "ballistic_missile_submarines",
        "aircraft_carriers",
        "strategic_missiles",
    )
)
ATTRIBUTION_FIELDS = (
    "role",
    "observation_year",
    "source_date",
    "evidence_kind",
    "confidence",
    "count_basis",
    "source_name",
    "source_reference",
    "source_url",
    "source_note",
)


def apply_equipment_supplement(
    military_rows: Iterable[dict[str, str]],
    supplement_rows: Iterable[dict[str, str]],
) -> list[dict[str, str]]:
    """Apply cited 2001 equipment counts while leaving all other cells intact."""
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
            raise ValueError(f"Duplicate military equipment supplement for {country_id}/{field}.")
        seen_supplements.add(key)
        if str(supplement.get("scenario_year", "")) != "2001" or field not in EQUIPMENT_FIELDS:
            raise ValueError(f"Unsupported military equipment supplement contract for {country_id}/{field}.")
        role = str(supplement.get("role", "")).strip()
        if field != f"military_{role}_quantity_2001":
            raise ValueError(f"Military equipment supplement role does not match field for {country_id}/{field}.")
        if not all(str(supplement.get(column, "")).strip() for column in ATTRIBUTION_FIELDS):
            raise ValueError(f"Military equipment supplement for {country_id}/{field} is missing provenance.")
        if country_id not in row_by_country:
            raise ValueError(f"Military equipment supplement country {country_id} is not in countries_mil.tsv.")
        if field not in row_by_country[country_id]:
            raise ValueError(f"Military equipment supplement field {field} is missing from countries_mil.tsv.")
        try:
            value = int(str(supplement.get("value", "")))
        except ValueError as exc:
            raise ValueError(f"Military equipment supplement value for {country_id}/{field} must be an integer.") from exc
        if value < 0:
            raise ValueError(f"Military equipment supplement value for {country_id}/{field} cannot be negative.")
        row_by_country[country_id][field] = str(value)

    return output_rows


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply cited 2001 military-equipment inventory counts.")
    parser.add_argument("--check", action="store_true", help="Fail if the inventory differs from the source ledger.")
    arguments = parser.parse_args()

    supplement_rows = _read_tsv(SUPPLEMENT_PATH)
    military_rows = _read_tsv(MILITARY_PATH)
    field_names = list(military_rows[0]) if military_rows else []
    output_rows = apply_equipment_supplement(military_rows, supplement_rows)
    before_by_country = {row["id"].strip().upper(): row for row in military_rows}
    changed = sum(
        before_by_country[row["country_id"].strip().upper()].get(row["field"]) != row["value"]
        for row in supplement_rows
    )
    if arguments.check:
        if changed:
            raise SystemExit(f"{changed} equipment supplement value(s) differ from the evidence ledger.")
        print(f"Verified {len(supplement_rows)} equipment supplement value(s) against the ledger.")
        return

    with MILITARY_PATH.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=field_names, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)
    print(f"Applied {len(supplement_rows)} equipment supplement value(s); changed {changed} value(s).")


if __name__ == "__main__":
    main()
