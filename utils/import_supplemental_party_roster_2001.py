from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = (
    ROOT / "modules/base/data/sources/2001/country_party_roster_supplemental_2001.tsv"
)
COUNTRIES_PATH = ROOT / "modules/base/data/countries/countries.tsv"
WORLD_PATH = (
    ROOT / "modules/base/data/world/country_party_roster_supplemental_2001.toml"
)
MANIFEST_PATH = (
    ROOT / "modules/base/data/sources/2001/country_party_roster_supplemental_2001.json"
)

SOURCE_COLUMNS = (
    "country_id",
    "source_year",
    "display_name",
    "leaders_text",
    "leader_status",
    "source_country",
    "source_field",
    "source_entry",
    "source_name",
    "source_reference",
    "source_url",
    "source_note",
)
RUNTIME_COLUMNS = (
    "id",
    "country_id",
    "party_id",
    "display_name",
    "leaders_text",
    "leader_status",
    "source_country",
    "source_year",
    "source_field",
    "source_entry",
    "source_notes",
    "source_name",
    "source_reference",
    "source_url",
    "source_note",
)
EXPECTED_COUNTRY_COUNTS = {"KOS": 14, "MNE": 16, "PSE": 2, "SRB": 4, "SSD": 1, "TLS": 12}


def _slug(value: str) -> str:
    ascii_text = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .casefold()
    )
    return re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")


def _read_game_country_ids() -> set[str]:
    with COUNTRIES_PATH.open(encoding="utf-8-sig", newline="") as stream:
        return {row["id"] for row in csv.DictReader(stream, delimiter="\t")}


def _load_source_rows() -> list[dict[str, str]]:
    with SOURCE_PATH.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if tuple(reader.fieldnames or ()) != SOURCE_COLUMNS:
            raise ValueError(
                "Supplemental roster source columns do not match the expected schema."
            )
        return [dict(row) for row in reader]


def _build_rows(
    source_rows: list[dict[str, str]], country_ids: set[str]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    counts: Counter[str] = Counter()

    for source in source_rows:
        country_id = source["country_id"].strip().upper()
        try:
            source_year = int(source["source_year"])
        except ValueError as error:
            raise ValueError(f"Invalid source year for country {country_id}") from error
        display_name = source["display_name"].strip()
        party_id = _slug(display_name)
        record_id = f"{country_id}:{party_id}"

        if country_id not in country_ids:
            raise ValueError(
                f"Supplemental source refers to an unknown game country: {country_id}"
            )
        if not 1900 <= source_year <= 2001:
            raise ValueError(
                f"Supplemental source year is outside the 2001 scenario window: {record_id}"
            )
        if not display_name or not party_id or record_id in seen_ids:
            raise ValueError(
                f"Invalid or duplicate supplemental party record: {record_id}"
            )
        leader_status = source["leader_status"].strip()
        leaders_text = source["leaders_text"].strip()
        if leader_status not in {"not_reported", "reported"}:
            raise ValueError(f"Unsupported supplemental leader status: {record_id}")
        if (leader_status == "reported") != bool(leaders_text):
            raise ValueError(f"Supplemental leader attribution is incomplete: {record_id}")
        if not source["source_entry"].strip().startswith(display_name):
            raise ValueError(
                f"The source entry does not begin with its displayed label: {record_id}"
            )
        if not all(
            source[key].strip()
            for key in (
                "source_country",
                "source_field",
                "source_name",
                "source_reference",
                "source_url",
                "source_note",
            )
        ):
            raise ValueError(f"Missing row-level source attribution: {record_id}")
        if "Political parties and leaders" == source["source_field"]:
            raise ValueError(
                f"Supplemental rows must retain their distinct source field: {record_id}"
            )

        rows.append(
            {
                "id": record_id,
                "country_id": country_id,
                "party_id": party_id,
                "display_name": display_name,
                "leaders_text": leaders_text,
                "leader_status": leader_status,
                "source_country": source["source_country"].strip(),
                "source_year": source_year,
                "source_field": source["source_field"].strip(),
                "source_entry": source["source_entry"].strip(),
                "source_notes": "",
                "source_name": source["source_name"].strip(),
                "source_reference": source["source_reference"].strip(),
                "source_url": source["source_url"].strip(),
                "source_note": source["source_note"].strip(),
            }
        )
        seen_ids.add(record_id)
        counts[country_id] += 1

    if dict(counts) != EXPECTED_COUNTRY_COUNTS:
        raise ValueError(
            f"Supplemental coverage changed: expected {EXPECTED_COUNTRY_COUNTS}, got {dict(counts)}"
        )
    return rows


def _toml_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _write_world_toml(rows: list[dict[str, Any]]) -> None:
    lines: list[str] = []
    for row in rows:
        lines.append("[[country_party_roster_supplemental_2001]]")
        for column in RUNTIME_COLUMNS:
            value = row[column]
            if column == "source_year":
                lines.append(f"{column} = {int(value)}")
            else:
                lines.append(f"{column} = {_toml_string(value)}")
        lines.append("")
    WORLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    WORLD_PATH.write_text("\n".join(lines), encoding="utf-8")


def generate() -> dict[str, Any]:
    if not SOURCE_PATH.is_file():
        raise FileNotFoundError(
            f"The supplemental party source ledger is missing: {SOURCE_PATH}"
        )
    source_bytes = SOURCE_PATH.read_bytes()
    source_rows = _load_source_rows()
    rows = _build_rows(source_rows, _read_game_country_ids())
    _write_world_toml(rows)

    country_counts = dict(sorted(Counter(row["country_id"] for row in rows).items()))
    sources = {
        row["source_name"]: {
            "source_url": row["source_url"],
            "source_reference": row["source_reference"],
            "country_id": row["country_id"],
            "record_count": sum(
                1
                for candidate in rows
                if candidate["source_name"] == row["source_name"]
            ),
        }
        for row in rows
    }
    manifest = {
        "data_year": 2001,
        "data_file": SOURCE_PATH.name,
        "data_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "runtime_file": str(WORLD_PATH.relative_to(ROOT)).replace("\\", "/"),
        "runtime_sha256": hashlib.sha256(WORLD_PATH.read_bytes()).hexdigest(),
        "record_count": len(rows),
        "country_counts": country_counts,
        "sources": sources,
        "limitations": [
            "Rows are separately sourced electoral or political-context entities, not additions to the CIA Factbook extractor output.",
            "Kosovo rows include only the 14 entities reported as winning Assembly seats; the OSCE notes 26 contestants.",
            "Montenegro rows preserve the 16 electoral-list labels in the OSCE/ODIHR result table; these may be parties or coalitions.",
            "East Timor rows include the 12 parties reported as winning national seats from 16 registered parties.",
            "Serbia rows include only the four lists reported by the National Assembly history page as winning seats in the 23 December 2000 election.",
            "Palestinian rows preserve two exact Legislative Council outcome categories from the official 20 January 1996 results; these are historical election context, not a complete 2001 party roster.",
            "Each row's source_year is the year of the underlying election or source record; records may predate the 2001 scenario year.",
            "Supplemental leaders are shown only where the cited source explicitly names one; no vote shares, support, eligibility, or ruling-party status are added.",
            "The CIA Factbook lists the Sudan People's Liberation Army with Dr. John Garang as a political pressure group; its 2001 Sudan-wide entry supplies southern-territory context for SSD, not a separate country party roster or election result.",
            "No entries are attributed from the combined Yugoslavia Factbook record to Serbia, Kosovo, or Montenegro by this importer.",
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
                "country_counts": result["country_counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
