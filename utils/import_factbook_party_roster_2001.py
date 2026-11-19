"""Extract named political-party entries from the CIA World Factbook 2001."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pycountry

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "modules/base/data"
FACTBOOK_PATH = DATA / "sources/2001/factbook.txt"
COUNTRIES_PATH = DATA / "countries/countries.tsv"
EXTRACT_PATH = DATA / "sources/2001/country_party_roster_factbook_2001.tsv"
COVERAGE_PATH = DATA / "sources/2001/country_party_roster_coverage_2001.tsv"
MANIFEST_PATH = DATA / "sources/2001/country_party_roster_factbook_2001.json"
WORLD_PATH = DATA / "world/country_party_roster_2001.toml"
COVERAGE_WORLD_PATH = DATA / "world/country_party_roster_coverage_2001.toml"

SOURCE_NAME = "United States Central Intelligence Agency, The World Factbook 2001"
SOURCE_URL = "https://www.gutenberg.org/ebooks/27638"
SOURCE_TEXT_URL = "https://www.gutenberg.org/cache/epub/27638/pg27638.txt"
SOURCE_FIELD = "Political parties and leaders"
SOURCE_NOTE = (
    "The Factbook says information generally available as of 1 January 2001 was used; "
    "this field gives no field-specific estimate year, vote share, or support share."
)
ANTARCTICA_ROSTER_SCOPE_NOTE = (
    "The Factbook describes Antarctica as a continent with no conventional long form "
    "and a government framework based on the Antarctic Treaty; its People entry reports "
    "no indigenous inhabitants and multinational research-station staff. For this "
    "continent-level game profile, a national party roster does not apply. This is a "
    "scope classification, not a party count or ruling-party claim."
)

# The 2001 Factbook predates some current ISO names and codes.
FACTBOOK_COUNTRY_ALIASES = {
    "Bahamas, The": "BHS",
    "Gambia, The": "GMB",
    "Burma": "MMR",
    "Congo, Democratic Republic of the": "COD",
    "Congo, Republic of the": "COG",
    "Korea, North": "PRK",
    "Korea, South": "KOR",
    "Laos": "LAO",
    "Macedonia, The Former Yugoslav Republic of": "MKD",
    "Taiwan": "TWN",
    "Yugoslavia": "YUG",
    "West Bank": "PSE",
    "Gaza Strip": "PSX",
    "East Timor": "TLS",
    "Vietnam": "VNM",
    "Holy See (Vatican City)": "VAT",
    "Cote d'Ivoire": "CIV",
    "Russia": "RUS",
    "Turkey": "TUR",
    "Brunei": "BRN",
    "Cape Verde": "CPV",
    "Swaziland": "SWZ",
}

HEADING_RE = re.compile(r"^(.+?)    Geography\s*$", re.MULTILINE)
NON_PARTY_RE = re.compile(
    r"^(?:note\s*-|several other groups or parties\b|eight registered small parties\b)",
    re.IGNORECASE,
)

EXTRACT_COLUMNS = (
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
COVERAGE_COLUMNS = (
    "country_id",
    "source_country",
    "status",
    "party_record_count",
    "source_name",
    "source_reference",
    "source_url",
    "source_note",
)


def normalize_source_text(value: str) -> str:
    """Collapse source line wraps while retaining source wording and punctuation."""
    return " ".join(str(value or "").split())


def _source_code(country_name: str) -> str | None:
    code = FACTBOOK_COUNTRY_ALIASES.get(country_name)
    if code:
        return code
    try:
        return pycountry.countries.lookup(country_name).alpha_3
    except LookupError:
        return None


def _country_entries(source_text: str) -> list[tuple[str, str]]:
    headings = list(HEADING_RE.finditer(source_text))
    entries = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(source_text)
        entries.append((heading.group(1).strip(), source_text[heading.end() : end]))
    return entries


def _factbook_field_names(source_text: str) -> set[str]:
    lines = source_text.splitlines()
    description_index = next(
        (index for index, line in enumerate(lines) if line.strip() == "Field Description"),
        None,
    )
    if description_index is None:
        raise ValueError("Factbook source is missing its Field Listings")
    names: set[str] = set()
    started = False
    for line in lines[description_index + 1 :]:
        label = line.strip()
        if not label:
            if started:
                break
            continue
        started = True
        names.add(label)
    if SOURCE_FIELD not in names:
        raise ValueError(f"Factbook Field Listings do not include {SOURCE_FIELD!r}")
    return names


def _field_value(country_block: str, field_name: str, field_names: set[str]) -> str | None:
    field_re = re.compile(rf"^{re.escape(field_name)}:\s*", re.MULTILINE)
    match = field_re.search(country_block)
    if match is None:
        return None
    remainder = country_block[match.end() :]
    labels = "|".join(re.escape(name) for name in sorted(field_names, key=len, reverse=True))
    next_field = re.search(rf"^(?:{labels}):\s*", remainder, re.MULTILINE)
    value = remainder[: next_field.start()] if next_field else remainder
    return normalize_source_text(value)


def _split_entries(field_text: str) -> list[str]:
    """Split roster entries only at semicolons outside source brackets."""
    entries: list[str] = []
    square_depth = 0
    paren_depth = 0
    start = 0
    for index, char in enumerate(field_text):
        if char == "[":
            square_depth += 1
        elif char == "]":
            square_depth = max(0, square_depth - 1)
        elif char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth = max(0, paren_depth - 1)
        elif char == ";" and square_depth == 0 and paren_depth == 0:
            entry = field_text[start:index].strip()
            if entry:
                entries.append(entry)
            start = index + 1
    final_entry = field_text[start:].strip()
    if final_entry:
        entries.append(final_entry)
    return entries


def _party_identity(source_entry: str) -> tuple[str, str, str] | None:
    if NON_PARTY_RE.match(source_entry):
        return None

    leader_match = re.search(r"\[([^\]]*)\]", source_entry)
    display_name = source_entry[: leader_match.start()] if leader_match else source_entry
    display_name = display_name.strip().rstrip(" .")
    if not display_name:
        return None

    leaders_text = normalize_source_text(leader_match.group(1)) if leader_match else ""
    if not leaders_text:
        leader_status = "not_listed"
    elif leaders_text.casefold() in {"na", "n/a", "leader na"}:
        leaders_text = ""
        leader_status = "not_reported"
    else:
        leader_status = "reported"
    return display_name, leaders_text, leader_status


def _slug(value: str) -> str:
    normalized = value.casefold()
    normalized = normalized.replace("&", " and ")
    slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    if slug:
        return slug
    return f"entry_{hashlib.sha1(value.encode('utf-8')).hexdigest()[:12]}"


def _read_game_country_ids(path: Path = COUNTRIES_PATH) -> set[str]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return {
            row["id"].strip().upper()
            for row in csv.DictReader(stream, delimiter="\t")
            if row.get("id", "").strip()
        }


def build_roster(
    source_text: str,
    game_country_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Build named party rows, explicit country coverage, and extraction counts."""
    source_entries: dict[str, tuple[str, str | None]] = {}
    field_names = _factbook_field_names(source_text)
    source_country_blocks = dict(_country_entries(source_text))
    for country_name, country_block in _country_entries(source_text):
        country_id = _source_code(country_name)
        if country_id:
            source_entries[country_id] = (
                country_name,
                _field_value(country_block, SOURCE_FIELD, field_names),
            )

    roster_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    source_country_names = {name for name, _ in _country_entries(source_text)}
    country_field_count = 0

    for country_id in sorted(game_country_ids):
        source_country, party_field = source_entries.get(country_id, ("", None))
        records: list[dict[str, Any]] = []
        source_notes: list[str] = []
        if party_field is not None:
            country_field_count += 1
            for entry in _split_entries(party_field):
                identity = _party_identity(entry)
                if identity is None:
                    source_notes.append(entry)
                    continue
                display_name, leaders_text, leader_status = identity
                party_id = _slug(display_name)
                records.append(
                    {
                        "id": f"{country_id}:{party_id}",
                        "country_id": country_id,
                        "party_id": party_id,
                        "display_name": display_name,
                        "leaders_text": leaders_text,
                        "leader_status": leader_status,
                        "source_country": source_country,
                        "source_year": 2001,
                        "source_field": SOURCE_FIELD,
                        "source_entry": entry,
                        "source_notes": "",
                        "source_name": SOURCE_NAME,
                        "source_reference": f"{SOURCE_NAME}, {source_country}, {SOURCE_FIELD}",
                        "source_url": SOURCE_TEXT_URL,
                        "source_note": SOURCE_NOTE,
                    }
                )

        if source_notes and records:
            notes = " | ".join(source_notes)
            for row in records:
                row["source_notes"] = notes
        roster_rows.extend(records)
        source_record = source_entries.get(country_id)
        if source_record is None:
            status = "no_separate_country_entry"
            source_country = ""
        elif party_field is None:
            status = "party_field_not_reported"
        elif records:
            status = "reported"
        else:
            status = "field_without_named_party_record"
        coverage_rows.append(
            {
                "country_id": country_id,
                "source_country": source_country,
                "status": status,
                "party_record_count": len(records),
                "source_name": SOURCE_NAME,
                "source_reference": (
                    f"{SOURCE_NAME}, {source_country}, {SOURCE_FIELD}"
                    if source_country and party_field is not None
                    else f"{SOURCE_NAME}, {source_country}" if source_country else SOURCE_NAME
                ),
                "source_url": SOURCE_TEXT_URL,
                "source_note": (
                    f"{SOURCE_NOTE} {ANTARCTICA_ROSTER_SCOPE_NOTE}"
                    if country_id == "ATA"
                    else SOURCE_NOTE
                ),
            }
        )

    unmapped_source_countries = sorted(
        country_name
        for country_name, _ in _country_entries(source_text)
        if _source_code(country_name) is None
        and _field_value(source_country_blocks[country_name], SOURCE_FIELD, field_names) is not None
    )
    non_game_source_countries = sorted(
        source_country
        for country_id, (source_country, party_field) in source_entries.items()
        if country_id not in game_country_ids and party_field is not None
    )
    counts = {
        "source_country_entries": len(source_country_names),
        "source_party_fields": sum(
            _field_value(block, SOURCE_FIELD, field_names) is not None
            for _, block in _country_entries(source_text)
        ),
        "game_country_count": len(game_country_ids),
        "game_countries_with_party_field": country_field_count,
        "game_countries_with_party_records": sum(row["status"] == "reported" for row in coverage_rows),
        "party_record_count": len(roster_rows),
        "uncovered_game_country_ids": [
            row["country_id"] for row in coverage_rows if row["status"] != "reported"
        ],
        "uncovered_game_statuses": {
            status: [row["country_id"] for row in coverage_rows if row["status"] == status]
            for status in sorted({row["status"] for row in coverage_rows if row["status"] != "reported"})
        },
        "unmapped_source_countries_with_party_fields": unmapped_source_countries,
        "non_game_source_countries_with_party_fields": non_game_source_countries,
    }
    validate_roster(roster_rows, coverage_rows, game_country_ids)
    return roster_rows, coverage_rows, counts


def validate_roster(
    roster_rows: list[dict[str, Any]],
    coverage_rows: list[dict[str, Any]],
    game_country_ids: set[str],
) -> None:
    """Reject ambiguous, unsupported, or duplicate source-backed party records."""
    if {row["country_id"] for row in coverage_rows} != game_country_ids:
        raise ValueError("Country coverage must include every game country exactly once")
    if len(coverage_rows) != len(game_country_ids):
        raise ValueError("Duplicate game-country coverage record")

    keys: set[tuple[str, str]] = set()
    ids: set[str] = set()
    records_per_country = Counter(str(row.get("country_id") or "").strip().upper() for row in roster_rows)
    valid_coverage_statuses = {
        "reported",
        "no_separate_country_entry",
        "party_field_not_reported",
        "field_without_named_party_record",
    }
    for row in coverage_rows:
        country_id = str(row.get("country_id") or "").strip().upper()
        status = str(row.get("status") or "")
        record_count = int(row.get("party_record_count") or 0)
        if status not in valid_coverage_statuses:
            raise ValueError(f"Unknown party-roster coverage status: {status!r}")
        if record_count != records_per_country[country_id]:
            raise ValueError(f"Coverage count does not match party rows for {country_id}")
        if (status == "reported") != (record_count > 0):
            raise ValueError(f"Coverage status does not match party rows for {country_id}")

    for row in roster_rows:
        country_id = str(row.get("country_id") or "").strip().upper()
        party_id = str(row.get("party_id") or "").strip()
        display_name = str(row.get("display_name") or "").strip()
        if country_id not in game_country_ids or not party_id or not display_name:
            raise ValueError(f"Invalid party roster identity: {row!r}")
        key = (country_id, party_id)
        if key in keys or row["id"] in ids:
            raise ValueError(f"Duplicate party roster identity: {key}")
        keys.add(key)
        ids.add(row["id"])
        if row.get("source_year") != 2001 or row.get("source_field") != SOURCE_FIELD:
            raise ValueError(f"Missing Factbook 2001 field provenance for {key}")
        if row.get("source_url") != SOURCE_TEXT_URL or not row.get("source_reference"):
            raise ValueError(f"Missing source reference for {key}")
        if not str(row.get("source_entry") or "").startswith(display_name):
            raise ValueError(f"Source entry does not contain the imported name for {key}")
        if NON_PARTY_RE.match(str(row.get("source_entry") or "")):
            raise ValueError(f"Narrative source note was imported as a party: {key}")
        if row.get("leader_status") not in {"reported", "not_reported", "not_listed"}:
            raise ValueError(f"Invalid leader availability status for {key}")
        if row.get("leader_status") != "reported" and row.get("leaders_text"):
            raise ValueError(f"Unreported leader names were imported for {key}")
        if any(column in row for column in ("support_share", "vote_share", "votes", "is_ruling")):
            raise ValueError(f"Unsupported electoral or ruling-party data for {key}")


def _toml_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _write_tsv(path: Path, rows: list[dict[str, Any]], columns: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _write_world_toml(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for row in rows:
        lines.append("[[country_party_roster_2001]]")
        for key in EXTRACT_COLUMNS:
            value = row[key]
            if key == "source_year":
                lines.append(f"{key} = {int(value)}")
            else:
                lines.append(f"{key} = {_toml_string(value)}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_coverage_world_toml(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for row in rows:
        lines.append("[[country_party_roster_coverage_2001]]")
        for key in COVERAGE_COLUMNS:
            value = row[key]
            if key == "party_record_count":
                lines.append(f"{key} = {int(value)}")
            else:
                lines.append(f"{key} = {_toml_string(value)}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def generate() -> dict[str, Any]:
    if not FACTBOOK_PATH.is_file():
        raise FileNotFoundError(f"The bundled CIA Factbook source is missing: {FACTBOOK_PATH}")
    source_bytes = FACTBOOK_PATH.read_bytes()
    source_text = source_bytes.decode("utf-8-sig")
    country_ids = _read_game_country_ids()
    roster_rows, coverage_rows, counts = build_roster(source_text, country_ids)
    _write_tsv(EXTRACT_PATH, roster_rows, EXTRACT_COLUMNS)
    _write_tsv(COVERAGE_PATH, coverage_rows, COVERAGE_COLUMNS)
    _write_world_toml(WORLD_PATH, roster_rows)
    _write_coverage_world_toml(COVERAGE_WORLD_PATH, coverage_rows)

    manifest = {
        "source": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "source_text_url": SOURCE_TEXT_URL,
        "source_file": FACTBOOK_PATH.name,
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "data_year": 2001,
        "source_vintage_note": SOURCE_NOTE,
        "extracted_file": EXTRACT_PATH.name,
        "extracted_file_sha256": hashlib.sha256(EXTRACT_PATH.read_bytes()).hexdigest(),
        "coverage_file": COVERAGE_PATH.name,
        "coverage_file_sha256": hashlib.sha256(COVERAGE_PATH.read_bytes()).hexdigest(),
        "runtime_file": str(WORLD_PATH.relative_to(ROOT)).replace("\\", "/"),
        "runtime_file_sha256": hashlib.sha256(WORLD_PATH.read_bytes()).hexdigest(),
        "coverage_runtime_file": str(COVERAGE_WORLD_PATH.relative_to(ROOT)).replace("\\", "/"),
        "coverage_runtime_file_sha256": hashlib.sha256(COVERAGE_WORLD_PATH.read_bytes()).hexdigest(),
        "method": (
            "Extract each country entry's Political parties and leaders field, normalize line wraps, "
            "split only on semicolons outside parentheses and leader brackets, and retain named "
            "entries with exact source text and leader wording. Descriptive notes are retained as "
            "source notes, not emitted as generic parties."
        ),
        "counts": counts,
        "limitations": [
            "The Factbook provides no consistent vote shares, support shares, or ruling-party indicator in this field.",
            "The source states general information availability as of 1 January 2001; no field-specific estimate year is given.",
            "Country entries without the field and countries without a separate Factbook entry are explicitly unavailable; no parent-country list is assigned to successor or territory records.",
        ],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    result = generate()
    print(json.dumps(result["counts"], ensure_ascii=False, indent=2))
