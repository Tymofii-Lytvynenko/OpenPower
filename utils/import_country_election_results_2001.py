from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "modules/base/data/sources/2001/country_election_results_2001.tsv"
COUNTRIES_PATH = ROOT / "modules/base/data/countries/countries.tsv"
WORLD_PATH = ROOT / "modules/base/data/world/country_election_results.toml"
MANIFEST_PATH = (
    ROOT / "modules/base/data/sources/2001/country_election_results_2001.json"
)

SOURCE_COLUMNS = (
    "event_id",
    "country_id",
    "election_date",
    "additional_election_date",
    "result_date",
    "source_year",
    "geography",
    "result_label",
    "votes",
    "vote_share_pct",
    "seats",
    "general_seats",
    "special_seats",
    "result_scope",
    "source_name",
    "source_reference",
    "source_url",
    "source_note",
)
RUNTIME_COLUMNS = (
    "id",
    "event_id",
    "country_id",
    "election_date",
    "additional_election_date",
    "result_date",
    "source_year",
    "geography",
    "result_label",
    "votes",
    "vote_share_pct",
    "seats",
    "general_seats",
    "special_seats",
    "result_scope",
    "source_name",
    "source_reference",
    "source_url",
    "source_note",
)
EXPECTED_EVENTS: dict[str, dict[str, int | None]] = {
    "BGD_2001_parliamentary": {"rows": 55, "votes": 55_736_625, "seats": 300},
    "KOS_2001_assembly": {"rows": 26, "votes": 788_303, "seats": 120},
    "MNE_2001_parliamentary": {
        "rows": 16,
        "votes": 363_404,
        "seats": 77,
        "general_seats": 72,
        "special_seats": 5,
    },
    "TLS_2001_constituent_assembly": {
        "rows": 12,
        "votes": None,
        "seats": 75,
    },
    "DNK_2001_folketing": {"rows": 11, "votes": 3_449_668, "seats": 175},
    "SRB_2000_assembly": {"rows": 8, "votes": 3_660_849, "seats": 250},
}


def _slug(value: str) -> str:
    ascii_text = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .casefold()
    )
    return re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")


def _read_country_ids() -> set[str]:
    with COUNTRIES_PATH.open(encoding="utf-8-sig", newline="") as stream:
        return {
            row["id"].strip().upper() for row in csv.DictReader(stream, delimiter="\t")
        }


def _read_source_rows() -> list[dict[str, str]]:
    with SOURCE_PATH.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if tuple(reader.fieldnames or ()) != SOURCE_COLUMNS:
            raise ValueError(
                "Election result source columns do not match the expected schema."
            )
        return [dict(row) for row in reader]


def _parse_optional_int(value: str, field_name: str, record_id: str) -> int | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        parsed = int(cleaned)
    except ValueError as error:
        raise ValueError(
            f"Invalid {field_name} for election result {record_id}"
        ) from error
    if parsed < 0:
        raise ValueError(f"Negative {field_name} for election result {record_id}")
    return parsed


def _parse_optional_share(value: str, record_id: str) -> float | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        parsed = float(cleaned)
    except ValueError as error:
        raise ValueError(
            f"Invalid vote share for election result {record_id}"
        ) from error
    if not math.isfinite(parsed) or not 0.0 <= parsed <= 100.0:
        raise ValueError(f"Out-of-range vote share for election result {record_id}")
    return parsed


def _parse_date(
    value: str, field_name: str, record_id: str, *, optional: bool = False
) -> str:
    cleaned = value.strip()
    if optional and not cleaned:
        return ""
    try:
        return date.fromisoformat(cleaned).isoformat()
    except ValueError as error:
        raise ValueError(
            f"Invalid {field_name} for election result {record_id}"
        ) from error


def _build_rows(
    source_rows: list[dict[str, str]], country_ids: set[str]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    labels_by_event: set[tuple[str, str]] = set()
    event_rows: dict[str, list[dict[str, Any]]] = {}

    for source in source_rows:
        event_id = source["event_id"].strip()
        country_id = source["country_id"].strip().upper()
        result_label = source["result_label"].strip()
        record_id = f"{event_id}:{_slug(result_label)}"
        if event_id not in EXPECTED_EVENTS:
            raise ValueError(f"Unexpected election event: {event_id}")
        if country_id not in country_ids:
            raise ValueError(
                f"Election result refers to an unknown game country: {country_id}"
            )
        if not result_label or not _slug(result_label) or record_id in seen_ids:
            raise ValueError(f"Invalid or duplicate election result: {record_id}")
        if (event_id, result_label.casefold()) in labels_by_event:
            raise ValueError(
                f"Duplicate result label in event {event_id}: {result_label}"
            )

        election_date = _parse_date(source["election_date"], "election date", record_id)
        additional_date = _parse_date(
            source["additional_election_date"],
            "additional election date",
            record_id,
            optional=True,
        )
        result_date = _parse_date(
            source["result_date"], "result date", record_id, optional=True
        )
        try:
            source_year = int(source["source_year"].strip())
        except ValueError as error:
            raise ValueError(
                f"Invalid source year for election result {record_id}"
            ) from error
        if source_year != date.fromisoformat(election_date).year:
            raise ValueError(
                f"Source year does not match the election date: {record_id}"
            )

        votes = _parse_optional_int(source["votes"], "votes", record_id)
        share = _parse_optional_share(source["vote_share_pct"], record_id)
        seats = _parse_optional_int(source["seats"], "seats", record_id)
        general_seats = _parse_optional_int(
            source["general_seats"], "general seats", record_id
        )
        special_seats = _parse_optional_int(
            source["special_seats"], "special seats", record_id
        )
        if seats is None or (votes is None and share is None):
            raise ValueError(
                f"Election result is missing an outcome value: {record_id}"
            )
        if (general_seats is None) != (special_seats is None):
            raise ValueError(
                f"Seat split is incomplete for election result {record_id}"
            )
        if general_seats is not None and general_seats + special_seats != seats:
            raise ValueError(f"Seat split does not sum to total seats: {record_id}")

        for field_name in (
            "geography",
            "result_scope",
            "source_name",
            "source_reference",
            "source_url",
            "source_note",
        ):
            if not source[field_name].strip():
                raise ValueError(
                    f"Missing {field_name} attribution for election result {record_id}"
                )
        if not source["source_url"].strip().startswith("https://"):
            raise ValueError(f"Election result source URL must be HTTPS: {record_id}")

        row = {
            "id": record_id,
            "event_id": event_id,
            "country_id": country_id,
            "election_date": election_date,
            "additional_election_date": additional_date,
            "result_date": result_date,
            "source_year": source_year,
            "geography": source["geography"].strip(),
            "result_label": result_label,
            "votes": votes,
            "vote_share_pct": share,
            "seats": seats,
            "general_seats": general_seats,
            "special_seats": special_seats,
            "result_scope": source["result_scope"].strip(),
            "source_name": source["source_name"].strip(),
            "source_reference": source["source_reference"].strip(),
            "source_url": source["source_url"].strip(),
            "source_note": source["source_note"].strip(),
        }
        rows.append(row)
        event_rows.setdefault(event_id, []).append(row)
        seen_ids.add(record_id)
        labels_by_event.add((event_id, result_label.casefold()))

    if set(event_rows) != set(EXPECTED_EVENTS):
        raise ValueError(
            f"Election result event coverage changed: {sorted(event_rows)}"
        )
    for event_id, expected in EXPECTED_EVENTS.items():
        grouped = event_rows[event_id]
        if len(grouped) != expected["rows"]:
            raise ValueError(
                f"Unexpected row count for {event_id}: expected {expected['rows']}, got {len(grouped)}"
            )
        for field in ("votes", "seats", "general_seats", "special_seats"):
            expected_total = expected.get(field)
            if expected_total is None:
                continue
            observed = sum(row[field] or 0 for row in grouped)
            if observed != expected_total:
                raise ValueError(
                    f"Unexpected {field} total for {event_id}: expected {expected_total}, got {observed}"
                )
    return rows


def _toml_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _write_world_toml(rows: list[dict[str, Any]]) -> None:
    lines: list[str] = []
    for row in rows:
        lines.append("[[country_election_results]]")
        for column in RUNTIME_COLUMNS:
            value = row[column]
            if value is None or value == "":
                continue
            if column == "source_year" or isinstance(value, int):
                lines.append(f"{column} = {int(value)}")
            elif isinstance(value, float):
                lines.append(f"{column} = {value!r}")
            else:
                lines.append(f"{column} = {_toml_string(value)}")
        lines.append("")
    WORLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    WORLD_PATH.write_text("\n".join(lines), encoding="utf-8")


def generate() -> dict[str, Any]:
    if not SOURCE_PATH.is_file():
        raise FileNotFoundError(
            f"The election result source ledger is missing: {SOURCE_PATH}"
        )
    source_bytes = SOURCE_PATH.read_bytes()
    rows = _build_rows(_read_source_rows(), _read_country_ids())
    _write_world_toml(rows)

    event_counts = dict(sorted(Counter(row["event_id"] for row in rows).items()))
    sources = {
        event_id: {
            "country_id": event_rows[0]["country_id"],
            "election_date": event_rows[0]["election_date"],
            "additional_election_date": event_rows[0]["additional_election_date"],
            "result_date": event_rows[0]["result_date"],
            "source_name": event_rows[0]["source_name"],
            "source_reference": event_rows[0]["source_reference"],
            "source_url": event_rows[0]["source_url"],
            "record_count": len(event_rows),
        }
        for event_id, event_rows in sorted(
            (
                (key, [row for row in rows if row["event_id"] == key])
                for key in event_counts
            )
        )
    }
    manifest = {
        "data_year": 2001,
        "data_file": SOURCE_PATH.name,
        "data_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "runtime_file": str(WORLD_PATH.relative_to(ROOT)).replace("\\", "/"),
        "runtime_sha256": hashlib.sha256(WORLD_PATH.read_bytes()).hexdigest(),
        "record_count": len(rows),
        "event_counts": event_counts,
        "events": sources,
        "limitations": [
            "Election outcomes are historical event records and are not party support, eligibility, or ruling-party status.",
            "Bangladesh includes the Election Commission's 55 party/independent aggregate rows for the 300 directly elected seats; it excludes reserved women’s seats and does not state a separate result-declaration date in the cited table.",
            "Kosovo contains all 26 entities in the certified result table; the aggregate result is 788,303 votes and 120 seats.",
            "Montenegro percentages preserve the source's printed values; listed votes sum to 363,404 while the report states 366,152 votes cast, including invalid votes in threshold calculations.",
            "Denmark includes the final aggregate count for Denmark proper: 175 Folketing seats and 103 nomination districts. Greenland's and the Faroe Islands' separately elected seats are outside the cited table; the ministry page does not separately date publication of the count.",
            "East Timor contains the 12 national-list parties with allocated seats; the source gives percentages but no per-party vote counts, and 13 district seats are separate.",
            "Serbia contains all eight lists in the RIK result report, including four with no mandates. Its final report covers polling on 23 December 2000 and 10 January 2001.",
            "PSE 1996 is intentionally omitted because this ledger covers the four election events requested for the 2001 roster gap.",
        ],
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    result = generate()
    print(
        json.dumps(
            {
                "record_count": result["record_count"],
                "event_counts": result["event_counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
