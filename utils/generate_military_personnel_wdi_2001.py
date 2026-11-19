from __future__ import annotations

import csv
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "modules" / "base" / "data"
SOURCE_PATH = DATA / "sources" / "2001" / "MS.MIL.TOTL.P1.json"
MILITARY_PATH = DATA / "countries" / "countries_mil.tsv"
OUTPUT_PATH = DATA / "sources" / "2001" / "military_personnel_wdi_2001.tsv"
INDICATOR = "MS.MIL.TOTL.P1"
OBSERVATION_YEAR = "2001"
SCENARIO_YEAR = "2001"
SOURCE_NAME = "World Bank World Development Indicators; underlying source: IISS, The Military Balance"
SOURCE_URL = "https://api.worldbank.org/v2/country/all/indicator/MS.MIL.TOTL.P1?date=2001&format=json&per_page=300"
SOURCE_METHOD = (
    "Exact published WDI value matched by ISO3 code for 2001. The indicator counts active-duty "
    "armed forces and qualifying paramilitary personnel, excludes reservists, and may include "
    "IISS estimates where country data is uncertain."
)
FIELDNAMES = (
    "iso3",
    "military_count",
    "observation_year",
    "scenario_year",
    "indicator",
    "source",
    "source_url",
    "source_method",
    "source_release",
    "source_snapshot_sha256",
)


def _integer_value(value: Any, iso3: str) -> int:
    try:
        numeric = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"WDI value for {iso3} is not numeric: {value!r}.") from exc
    if not numeric.is_finite() or numeric != numeric.to_integral_value():
        raise ValueError(f"WDI value for {iso3} is not an integer personnel count: {value!r}.")
    return int(numeric)


def build_wdi_personnel_ledger(
    source_payload: list[Any],
    military_rows: Iterable[dict[str, str]],
    source_snapshot_sha256: str,
) -> list[dict[str, str]]:
    """Build a non-mutating ledger of exact WDI matches for the game roster."""
    if len(source_payload) != 2 or not isinstance(source_payload[0], dict) or not isinstance(source_payload[1], list):
        raise ValueError("WDI source snapshot must contain API metadata followed by observation rows.")
    metadata, observations = source_payload
    source_release = str(metadata.get("lastupdated", "")).strip()
    if not source_release:
        raise ValueError("WDI source snapshot has no release date.")

    countries: dict[str, dict[str, str]] = {}
    for row in military_rows:
        iso3 = str(row.get("id", "")).strip().upper()
        if not iso3 or iso3 in countries:
            raise ValueError(f"Military roster has a missing or duplicate country ID: {iso3!r}.")
        countries[iso3] = row

    observed_by_iso3: dict[str, int] = {}
    for observation in observations:
        if not isinstance(observation, dict) or observation.get("date") != OBSERVATION_YEAR:
            continue
        if observation.get("indicator", {}).get("id") != INDICATOR:
            continue
        iso3 = str(observation.get("countryiso3code", "")).strip().upper()
        if iso3 not in countries or observation.get("value") is None:
            continue
        if iso3 in observed_by_iso3:
            raise ValueError(f"WDI source snapshot has duplicate 2001 observations for {iso3}.")
        observed_by_iso3[iso3] = _integer_value(observation["value"], iso3)

    ledger: list[dict[str, str]] = []
    for iso3 in sorted(observed_by_iso3):
        value = observed_by_iso3[iso3]
        current_value = _integer_value(countries[iso3].get("military_count", ""), iso3)
        if current_value != value:
            raise ValueError(
                f"WDI observation for {iso3} ({value}) differs from countries_mil.tsv ({current_value}); "
                "the source ledger will not overwrite the game data."
            )
        ledger.append(
            {
                "iso3": iso3,
                "military_count": str(value),
                "observation_year": OBSERVATION_YEAR,
                "scenario_year": SCENARIO_YEAR,
                "indicator": INDICATOR,
                "source": SOURCE_NAME,
                "source_url": SOURCE_URL,
                "source_method": SOURCE_METHOD,
                "source_release": source_release,
                "source_snapshot_sha256": source_snapshot_sha256.lower(),
            }
        )
    return ledger


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def main() -> None:
    source_bytes = SOURCE_PATH.read_bytes()
    source_payload = json.loads(source_bytes.decode("utf-8-sig"))
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    ledger = build_wdi_personnel_ledger(source_payload, _read_tsv(MILITARY_PATH), source_hash)

    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=FIELDNAMES, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(ledger)

    print(f"Wrote {len(ledger)} exact WDI personnel matches from snapshot {source_hash}.")


if __name__ == "__main__":
    main()
