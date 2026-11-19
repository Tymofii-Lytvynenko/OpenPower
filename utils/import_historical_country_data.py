"""Import dated WDI observations without substituting later-year measurements."""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import math
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

import pycountry

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "modules/base/data"
UNDP_URL = "https://hdr.undp.org/sites/default/files/2025_HDR/HDR25_Composite_indices_complete_time_series.csv"
HDI_BACKFILL_PATH = DATA / "sources/2001/hdi_backfills_2001.tsv"
DEFAULT_HUMAN_DEV = 0.5
UNSD_PROTECTED_AREAS_URL = "https://unstats.un.org/unsd/environment/TerrestrialProtectedAreas.htm"
UNSD_PROTECTED_AREAS_DATA = DATA / "sources/2001/unsd_terrestrial_protected_areas_2010.tsv"
UNSD_PROTECTED_AREAS_MANIFEST = DATA / "sources/2001/unsd_terrestrial_protected_areas_2010.json"
NATIONAL_PARK_EVIDENCE_DATA = DATA / "sources/2001/national_park_terrestrial_2001_evidence.tsv"
SUPPLEMENTAL_CLIMATE_CONTEXT_DATA = DATA / "sources/2001/climate_context_supplemental_2001.tsv"
FAOSTAT_LAND_USE_URL = "https://bulks-faostat.fao.org/production/Inputs_LandUse_E_All_Data_(Normalized).zip"
FAOSTAT_LAND_USE_DATA = DATA / "sources/2001/faostat_land_use_2026.zip"
FAOSTAT_LAND_USE_MANIFEST = DATA / "sources/2001/faostat_land_use_2026.json"
FAOSTAT_LAND_METRIC_SUPPLEMENT = DATA / "sources/2001/faostat_land_metric_supplement_2001.tsv"
FACTBOOK_LAND_METRIC_SUPPLEMENT = DATA / "sources/2001/factbook_land_metric_supplement_2001.tsv"
NATIONAL_LAND_METRIC_SUPPLEMENT = DATA / "sources/2001/national_land_metric_supplement_2001.tsv"
UNDP_METRICS = {
    "reference_human_dev": "hdi",
    "reference_life_expectancy": "le",
    "expected_years_schooling": "eys",
    "mean_years_schooling": "mys",
    "gross_national_income_per_capita_ppp": "gnipc",
}


def parse_undp_records(payload: bytes) -> dict[str, dict[str, float]]:
    """Select dated observations, never a neighbouring year's estimate."""
    records = {}
    for row in csv.DictReader(io.StringIO(payload.decode("cp1252"))):
        values = {}
        for field, prefix in UNDP_METRICS.items():
            try:
                value = float(row.get(f"{prefix}_2001", ""))
            except (ValueError, TypeError):
                continue
            if math.isfinite(value) and value >= 0 and (prefix != "hdi" or value <= 1):
                values[field] = value
        records[row["iso3"]] = values
    return records


def human_development_records() -> dict[str, dict[str, float]]:
    cache = DATA / "sources/2001/undp_hdr2025.csv"
    if not cache.exists():
        request = Request(UNDP_URL + "?download=1", headers={
            "User-Agent": "Mozilla/5.0", "Referer": "https://hdr.undp.org/",
        })
        with urlopen(request, timeout=120) as response:
            payload = response.read()
        parse_undp_records(payload)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(payload)
    payload = cache.read_bytes()
    records = parse_undp_records(payload)
    world = records.get("ZZK.WORLD", {})
    if "reference_human_dev" not in world:
        raise ValueError("UNDP source lacks the dated world HDI aggregate")
    manifest = {"url": UNDP_URL, "release": 2025, "observation_year": 2001,
                "encoding": "cp1252", "sha256": hashlib.sha256(payload).hexdigest()}
    cache.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    lines = ['[[historical_world_indicators]]', 'id = "WLD"', 'year = 2001',
             'source = "UNDP HDR 2025: 2001 observations"', f'source_url = "{UNDP_URL}"']
    lines.extend(f"{field} = {value}" for field, value in world.items())
    (DATA / "world/historical_world_indicators.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return records


def human_development_backfills() -> dict[str, dict]:
    """Read sourced legacy values, transparent estimates, and non-applicable cases."""
    records = {}
    with HDI_BACKFILL_PATH.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            code = row["id"].strip()
            if not code or code in records:
                raise ValueError(f"Invalid or duplicate HDI backfill code: {code!r}")
            value_text = row["value"].strip()
            value = float(value_text) if value_text else None
            simulation_value = float(row["simulation_value"])
            if (value is not None and (not math.isfinite(value) or not 0 <= value <= 1)
                    or not math.isfinite(simulation_value) or not 0 <= simulation_value <= 1):
                raise ValueError(f"Invalid HDI backfill value for {code}")
            if value is None and row["status"] not in {"not_applicable", "not_reported"}:
                raise ValueError(f"HDI backfill {code} needs a score or an explicit unavailable status")
            records[code] = {
                "value": value,
                "simulation_value": simulation_value,
                "status": row["status"].strip(),
                "method": row["method"].strip(),
                "source": row["source"].strip(),
                "source_url": row["source_url"].strip(),
                "source_location": row["source_location"].strip(),
                "notes": row["notes"].strip(),
            }
    return records
INDICATORS = {
    "fertility_rate": "SP.DYN.TFRT.IN",
    "life_expectancy": "SP.DYN.LE00.IN",
    "birth_rate": "SP.DYN.CBRT.IN",
    "death_rate": "SP.DYN.CDRT.IN",
    "arable_land_pct": "AG.LND.ARBL.ZS",
    "forest_area_pct": "AG.LND.FRST.ZS",
    "reference_land_area_km2": "AG.LND.TOTL.K2",
    "reference_total_area_km2": "AG.SRF.TOTL.K2",
}
WDI_COUNTRY_ALIASES = {"XKX": "KOS"}

FACTBOOK_NAMES = {
    "Bahamas, The": "BHS", "Gambia, The": "GMB", "Burma": "MMR",
    "Congo, Democratic Republic of the": "COD", "Congo, Republic of the": "COG",
    "Korea, North": "PRK", "Korea, South": "KOR", "Laos": "LAO",
    "Macedonia, The Former Yugoslav Republic of": "MKD", "Taiwan": "TWN",
    "Yugoslavia": "YUG", "West Bank": "PSE", "Gaza Strip": "PSX",
    "East Timor": "TLS", "Vietnam": "VNM", "Holy See (Vatican City)": "VAT",
    "Cote d'Ivoire": "CIV",
    "Russia": "RUS", "Turkey": "TUR", "Brunei": "BRN",
    "Cape Verde": "CPV", "Swaziland": "SWZ",
}


def apply_wdi_observations(
    countries: dict[str, dict], field: str, indicator: str, source_records: list[dict]
) -> list[dict]:
    """Apply exact-year WDI records after mapping source ISO3 codes to game IDs."""
    provenance = []
    for record in source_records:
        source_code = record["countryiso3code"]
        code = WDI_COUNTRY_ALIASES.get(source_code, source_code)
        if code not in countries or record["value"] is None:
            continue
        if record["date"] != "2001":
            raise ValueError(f"Wrong observation year: {record}")
        countries[code][field] = record["value"]
        source_note = "World Bank observation dated 2001"
        if source_code != code:
            source_note += f"; WDI ISO3 {source_code} mapped to game country ID {code}"
        provenance.append(dict(
            id=code,
            field=field,
            year=2001,
            observation_year=2001,
            source=indicator,
            source_scope=record.get("country", {}).get("value"),
            source_note=source_note,
            url=f"https://data.worldbank.org/indicator/{indicator}",
        ))
    return provenance

UNSD_PROTECTED_AREA_NAME_ALIASES = {
    "Bahamas": "BHS",
    "Bolivia": "BOL",
    "Cape Verde": "CPV",
    "China, Hong Kong SAR": "HKG",
    "Congo": "COG",
    "Cote d'Ivoire": "CIV",
    "Dem. Rep. of the Congo": "COD",
    "Falkland Islands (Malvinas)": "FLK",
    "Iran (Islamic Republic of)": "IRN",
    "Korea, Dem. People's Rep.": "PRK",
    "Korea, Republic of": "KOR",
    "Lao People's Dem. Rep.": "LAO",
    "Libyan Arab Jamahiriya": "LBY",
    "Macedonia, The Former Yugoslav Republic of": "MKD",
    "Micronesia, Federated States of": "FSM",
    "Republic of Moldova": "MDA",
    "Russian Federation": "RUS",
    "Saint Kitts and Nevis": "KNA",
    "Saint Lucia": "LCA",
    "Saint Pierre and Miquelon": "SPM",
    "St. Vincent and the Grenadines": "VCT",
    "Swaziland": "SWZ",
    "Syrian Arab Republic": "SYR",
    "The Former Yugoslav Rep. of Macedonia": "MKD",
    "Timor-Leste": "TLS",
    "Turkey": "TUR",
    "United Rep. of Tanzania": "TZA",
    "United States Virgin Islands": "VIR",
    "Venezuela (Bolivarian Republic of)": "VEN",
    "Viet Nam": "VNM",
}

FAOSTAT_M49_ISO3_ALIASES = {"159": "CHN", "736": "SDN"}


def _estimate_year(detail: str) -> int | None:
    match = re.search(r"\b((?:19|20)\d{2})\b", detail)
    return int(match.group(1)) if match else None


def factbook_records() -> dict[str, dict]:
    path = DATA / "sources/2001/factbook.txt"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with urlopen("https://www.gutenberg.org/cache/epub/27638/pg27638.txt", timeout=120) as response:
            path.write_bytes(response.read())
    text = path.read_text(encoding="utf-8-sig")
    headings = list(re.finditer(r"^(.+?)    Geography\s*$", text, re.M))
    records = {}
    for index, heading in enumerate(headings):
        name = heading[1]
        try:
            code = FACTBOOK_NAMES.get(name) or pycountry.countries.lookup(name).alpha_3
        except LookupError:
            continue
        block = text[heading.end():headings[index + 1].start() if index + 1 < len(headings) else len(text)]
        values = {}
        climate = re.search(r"^Climate: (.*?)(?=\n\s*\n)", block, re.M | re.S)
        if climate:
            values["climate_description"] = " ".join(climate[1].split())
        for field, pattern in {
            "reference_water_area_km2": r"^water:\s*([\d,.]+) sq km",
            "reference_total_area_km2": r"^Area: total:\s*([\d,.]+) sq km",
            "birth_rate": r"^Birth rate:\s*([\d.]+) births/",
            "death_rate": r"^Death rate:\s*([\d.]+) deaths/",
            "fertility_rate": r"^Total fertility rate:\s*([\d.]+) children",
            "life_expectancy": r"^Life expectancy at birth: total population:\s*([\d.]+) years",
        }.items():
            match = re.search(pattern, block, re.M)
            if match:
                values[field] = float(match[1].replace(",", ""))
                source_line = block[match.start():].splitlines()[0]
                years = values.setdefault("_observation_years", {})
                years[field] = _estimate_year(source_line[match.end() - match.start():])
        poverty = re.search(r"^Population below poverty line:\s*([\d.]+)%([^\n]*)", block, re.M)
        if poverty:
            values["historical_poverty_rate_pct"] = float(poverty[1])
            poverty_detail = poverty[2].strip()
            poverty_year = _estimate_year(poverty_detail)
            values["historical_poverty_rate_year"] = poverty_year or 0
            values.setdefault("_observation_years", {})["historical_poverty_rate_pct"] = poverty_year
            values.setdefault("_source_notes", {})["historical_poverty_rate_pct"] = (
                poverty_detail or "CIA Factbook 2001 edition; estimate year not stated"
            )
        if "_observation_years" in values:
            values.setdefault("_source_notes", {}).update({
                field: (f"CIA Factbook estimate year {year}" if year else
                        "CIA Factbook 2001 edition; estimate year not stated")
                for field, year in values["_observation_years"].items()
            })
        values["_source_scope"] = name
        records[code] = values
    return records


def supplemental_climate_context_records(country_ids: set[str]) -> dict[str, dict]:
    """Read explicitly scoped historical climate context for absent Factbook entries."""
    records = {}
    with SUPPLEMENTAL_CLIMATE_CONTEXT_DATA.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            code = row["id"].strip().upper()
            if code not in country_ids or code in records:
                raise ValueError(f"Invalid or duplicate supplemental climate code: {code!r}")
            try:
                source_year = int(row["source_year"])
                observation_year = int(row["observation_year"]) if row["observation_year"].strip() else None
            except ValueError as error:
                raise ValueError(f"Invalid climate source year for {code}") from error
            description = row["climate_description"].strip()
            source = row["source"].strip()
            scope = row["source_scope"].strip()
            source_note = row["source_note"].strip()
            source_url = row["url"].strip()
            if not all((description, source, scope, source_note, source_url)):
                raise ValueError(f"Incomplete supplemental climate context for {code}")
            records[code] = {
                "climate_description": description,
                "source": source,
                "source_year": source_year,
                "observation_year": observation_year,
                "source_scope": scope,
                "source_note": source_note,
                "url": source_url,
            }
    return records


def observations(indicator: str) -> list[dict]:
    """Cache exact source responses so regeneration also works offline."""
    cache = DATA / "sources/2001" / f"{indicator}.json"
    if not cache.exists():
        url = (f"https://api.worldbank.org/v2/country/all/indicator/{indicator}"
               "?date=2001&format=json&per_page=1000")
        with urlopen(url, timeout=120) as response:
            payload = json.load(response)
        if not isinstance(payload, list) or len(payload) != 2 or not payload[1]:
            raise ValueError(f"No WDI observations returned for {indicator}")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return json.loads(cache.read_text(encoding="utf-8"))[1]


def write_table(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def parse_unsd_protected_area_records(payload: bytes) -> dict[str, float]:
    """Read the source table's 2000 column without substituting its 1990 or 2009 values."""
    source = payload.decode("utf-8-sig", errors="replace")
    records = {}
    for row_html in re.findall(r"(?is)<tr\b[^>]*>(.*?)</tr>", source):
        cells = re.findall(r"(?is)<td\b[^>]*>(.*?)</td>", row_html)
        if len(cells) < 4:
            continue
        country = html.unescape(re.sub(r"<[^>]+>", " ", cells[1])).strip()
        value_text = html.unescape(re.sub(r"<[^>]+>", " ", cells[3])).strip()
        value_text = " ".join(value_text.split()).replace(",", "")
        try:
            value = float(value_text)
        except ValueError:
            continue
        if country and math.isfinite(value) and 0 <= value <= 100:
            records[country] = value
    return records


def map_unsd_protected_area_records(
    source_records: dict[str, float],
    country_ids: set[str],
) -> dict[str, tuple[str, float]]:
    """Map official source labels to the game's ISO3 country keys."""
    mapped = {}
    for source_name, value in source_records.items():
        code = UNSD_PROTECTED_AREA_NAME_ALIASES.get(source_name)
        if code is None:
            try:
                code = pycountry.countries.lookup(source_name).alpha_3
            except LookupError:
                continue
        if code in country_ids:
            mapped[code] = (source_name, value)
    return mapped


def historical_protected_area_records(country_ids: set[str]) -> dict[str, tuple[str, float]]:
    """Load the attributed 2000 UNSD snapshot, downloading it only for regeneration."""
    if not UNSD_PROTECTED_AREAS_DATA.exists():
        request = Request(UNSD_PROTECTED_AREAS_URL, headers={"User-Agent": "OpenPower historical data importer"})
        with urlopen(request, timeout=120) as response:
            payload = response.read()
        source_records = parse_unsd_protected_area_records(payload)
        mapped = map_unsd_protected_area_records(source_records, country_ids)
        if len(mapped) < 180:
            raise ValueError(f"UNSD protected-area source matched only {len(mapped)} game countries")
        rows = [
            {"id": code, "source_country_name": name, "terrestrial_protected_area_pct_2000": value}
            for code, (name, value) in sorted(mapped.items())
        ]
        write_table(
            UNSD_PROTECTED_AREAS_DATA,
            rows,
            ["id", "source_country_name", "terrestrial_protected_area_pct_2000"],
        )
        manifest = {
            "url": UNSD_PROTECTED_AREAS_URL,
            "page_last_updated": 2010,
            "observation_year": 2000,
            "source_payload_sha256": hashlib.sha256(payload).hexdigest(),
            "mapped_game_country_count": len(mapped),
        }
        UNSD_PROTECTED_AREAS_MANIFEST.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

    with UNSD_PROTECTED_AREAS_DATA.open(encoding="utf-8-sig", newline="") as stream:
        records = {}
        for row in csv.DictReader(stream, delimiter="\t"):
            code = row["id"]
            value = float(row["terrestrial_protected_area_pct_2000"])
            if code not in country_ids or code in records or not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError(f"Invalid UNSD protected-area row: {row}")
            records[code] = (row["source_country_name"], value)
    return records


def national_park_evidence_records(country_ids: set[str]) -> dict[str, dict]:
    """Load country-specific park evidence without conflating it with broad protected areas."""
    records = {}
    with NATIONAL_PARK_EVIDENCE_DATA.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            code = row["id"].strip().upper()
            if code not in country_ids or code in records:
                raise ValueError(f"Invalid or duplicate national-park evidence code: {code!r}")
            parsed = dict(row)
            for field in (
                "national_park_land_area_km2",
                "national_park_land_coverage_pct",
                "terrestrial_protected_area_pct_2000_override",
            ):
                raw = row[field].strip()
                parsed[field] = float(raw) if raw else None
                if parsed[field] is not None and (
                    not math.isfinite(parsed[field]) or parsed[field] < 0
                    or field.endswith("coverage_pct") and parsed[field] > 100
                    or field.endswith("override") and parsed[field] > 100
                ):
                    raise ValueError(f"Invalid national-park evidence value for {code}: {field}")
            records[code] = parsed
    return records


def faostat_land_use_records(
    country_ids: set[str], *, write_manifest: bool = False
) -> dict[str, dict[str, object]]:
    """Read 2001 Other land and Land area from the FAOSTAT normalized snapshot."""
    source_last_modified = ""
    if not FAOSTAT_LAND_USE_DATA.exists():
        request = Request(FAOSTAT_LAND_USE_URL, headers={"User-Agent": "OpenPower historical-data importer"})
        with urlopen(request, timeout=120) as response:
            payload = response.read()
            source_last_modified = response.headers.get("Last-Modified", "")
        FAOSTAT_LAND_USE_DATA.parent.mkdir(parents=True, exist_ok=True)
        FAOSTAT_LAND_USE_DATA.write_bytes(payload)
    else:
        source_last_modified = "2026-10-02 (verified FAOSTAT bulk archive Last-Modified)"

    payload = FAOSTAT_LAND_USE_DATA.read_bytes()
    source_sha256 = hashlib.sha256(payload).hexdigest()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        data_name = next(
            name for name in archive.namelist()
            if name.endswith("_All_Data_(Normalized).csv")
        )
        flags_name = next(name for name in archive.namelist() if name.endswith("_Flags.csv"))
        flag_rows = csv.DictReader(io.StringIO(archive.read(flags_name).decode("utf-8-sig")))
        flag_descriptions = {row["Flag"]: row[" Description"].strip() for row in flag_rows}
        data_rows = csv.DictReader(io.StringIO(archive.read(data_name).decode("utf-8-sig")))
        by_m49: dict[str, dict[str, object]] = {}
        for row in data_rows:
            if row.get("Year") != "2001" or row.get("Element Code") != "5110":
                continue
            item_code = row.get("Item Code")
            if item_code not in {"6601", "6670"}:
                continue
            if row.get("Unit") != "1000 ha":
                raise ValueError(f"Unexpected FAOSTAT area unit: {row}")
            m49 = row.get("Area Code (M49)", "").strip().lstrip("'").zfill(3)
            try:
                value = float(row["Value"])
            except (KeyError, ValueError) as error:
                raise ValueError(f"Invalid FAOSTAT area value: {row}") from error
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid FAOSTAT area value: {row}")
            entry = by_m49.setdefault(m49, {"source_country_name": row["Area"]})
            if item_code in entry:
                raise ValueError(f"Duplicate FAOSTAT 2001 area category for M49 {m49}")
            entry[item_code] = value
            entry[f"{item_code}_flag"] = row.get("Flag", "")

    records: dict[str, dict[str, object]] = {}
    for m49, source in by_m49.items():
        if "6601" not in source or "6670" not in source:
            continue
        country_id = FAOSTAT_M49_ISO3_ALIASES.get(m49)
        if country_id is None:
            country = pycountry.countries.get(numeric=m49)
            country_id = country.alpha_3 if country is not None else None
        if country_id not in country_ids:
            continue
        land_area = float(source["6601"])
        other_land = float(source["6670"])
        if land_area <= 0:
            raise ValueError(f"Nonpositive FAOSTAT land area for {country_id}")
        other_land_pct = other_land / land_area * 100.0
        if not math.isfinite(other_land_pct) or not 0 <= other_land_pct <= 100:
            raise ValueError(f"Invalid FAOSTAT other-land percentage for {country_id}: {other_land_pct}")
        other_flag = str(source["6670_flag"])
        land_flag = str(source["6601_flag"])
        records[country_id] = {
            "other_land_pct": other_land_pct,
            "source_country_name": source["source_country_name"],
            "other_land_flag": other_flag,
            "land_area_flag": land_flag,
            "other_land_flag_description": flag_descriptions.get(other_flag, "Unknown FAOSTAT flag"),
            "land_area_flag_description": flag_descriptions.get(land_flag, "Unknown FAOSTAT flag"),
        }

    flag_counts: dict[str, int] = {}
    for record in records.values():
        flag = str(record["other_land_flag"])
        flag_counts[flag] = flag_counts.get(flag, 0) + 1
    manifest = {
        "dataset": "FAOSTAT Land Use (RL), Inputs_LandUse_E_All_Data_(Normalized).zip",
        "url": FAOSTAT_LAND_USE_URL,
        "source_last_modified": source_last_modified,
        "observation_year": 2001,
        "item": "Other land (6670)",
        "denominator": "Land area (6601)",
        "unit_in_source": "1000 ha",
        "derived_measure": "Other land area / Land area * 100",
        "mapped_game_country_count": len(records),
        "other_land_flag_counts": flag_counts,
        "source_sha256": source_sha256,
        "flags": flag_descriptions,
    }
    if write_manifest:
        FAOSTAT_LAND_USE_MANIFEST.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return records


def apply_land_metric_supplements(
    countries: dict[str, dict], source_rows: list[dict[str, str]]
) -> list[dict]:
    """Fill absent historical land cells while retaining each source observation year."""
    allowed_fields = {
        "arable_land_pct",
        "forest_area_pct",
        "reference_land_area_km2",
        "reference_water_area_km2",
    }
    provenance = []
    seen: set[tuple[str, str]] = set()
    for source_row in source_rows:
        country_id = source_row.get("country_id", "").strip().upper()
        field = source_row.get("field", "").strip()
        key = (country_id, field)
        if key in seen:
            raise ValueError(f"Duplicate historical land metric supplement for {country_id}/{field}.")
        seen.add(key)
        if country_id not in countries:
            raise ValueError(f"Historical land metric supplement country {country_id} is not in countries.tsv.")
        if field not in allowed_fields or source_row.get("scenario_year") != "2001":
            raise ValueError(f"Unsupported historical land metric supplement contract for {country_id}/{field}.")
        status = source_row.get("status", "")
        accepted_statuses = {
            "approved_for_import",
            "approved_for_import_adjacent_year",
            "approved_for_import_observation_year_unstated",
        }
        if status not in accepted_statuses:
            raise ValueError(f"Unreviewed historical land metric row for {country_id}/{field}.")
        required = ("value", "source_dataset", "source_scope", "source_note", "source_url")
        if not all(source_row.get(column, "").strip() for column in required):
            raise ValueError(f"Historical land metric supplement for {country_id}/{field} is missing provenance.")
        try:
            value = float(source_row["value"])
            source_year = int(source_row["source_year"])
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid value or date in historical land metric supplement for {country_id}/{field}.") from error
        observation_year_text = source_row.get("observation_year", "").strip()
        if status == "approved_for_import_observation_year_unstated":
            if (
                observation_year_text
                or source_year != 2001
                or source_row["source_dataset"] != "CIA World Factbook 2001"
            ):
                raise ValueError(
                    f"Unstated observation year must use the 2001 CIA Factbook for {country_id}/{field}."
                )
            observation_year = None
        else:
            try:
                observation_year = int(observation_year_text)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Missing observation year for historical land metric {country_id}/{field}."
                ) from error
        if not math.isfinite(value) or value < 0 or (
            observation_year is not None and not 2000 <= observation_year <= 2001
        ):
            raise ValueError(f"Invalid historical land metric value or observation year for {country_id}/{field}.")
        if status == "approved_for_import" and observation_year != 2001:
            raise ValueError(f"Historical land metric status does not match its observation year for {country_id}/{field}.")
        if status == "approved_for_import_adjacent_year" and observation_year != 2000:
            raise ValueError(f"Historical land metric status does not match its observation year for {country_id}/{field}.")
        if status == "approved_for_import_observation_year_unstated" and observation_year is not None:
            raise ValueError(f"Historical land metric status does not match its observation year for {country_id}/{field}.")
        if field.endswith("_pct") and value > 100:
            raise ValueError(f"Historical land metric percentage exceeds 100 for {country_id}/{field}.")
        if not source_row["source_url"].startswith("https://"):
            raise ValueError(f"Historical land metric supplement URL must use HTTPS for {country_id}/{field}.")

        # Exact-year WDI values loaded earlier take precedence over supplemental estimates.
        if field in countries[country_id]:
            continue
        countries[country_id][field] = value
        provenance.append({
            "id": country_id,
            "field": field,
            "year": 2001,
            "observation_year": observation_year,
            "source": source_row["source_dataset"],
            "source_year": source_year,
            "source_scope": source_row["source_scope"],
            "source_note": source_row["source_note"],
            "url": source_row["source_url"],
        })
    return provenance


def historical_land_metric_supplement_records(country_ids: set[str]) -> list[dict[str, str]]:
    """Read the reviewed land-metric rows without treating review-only candidates as data."""
    return read_historical_land_metric_records(FAOSTAT_LAND_METRIC_SUPPLEMENT, country_ids)


def factbook_land_metric_supplement_records(country_ids: set[str]) -> list[dict[str, str]]:
    """Read the reviewed CIA Factbook land-metric rows without treating candidates as data."""
    return read_historical_land_metric_records(FACTBOOK_LAND_METRIC_SUPPLEMENT, country_ids)


def national_land_metric_supplement_records(country_ids: set[str]) -> list[dict[str, str]]:
    """Read individually sourced national land-metric observations."""
    return read_historical_land_metric_records(NATIONAL_LAND_METRIC_SUPPLEMENT, country_ids)


def read_historical_land_metric_records(path: Path, country_ids: set[str]) -> list[dict[str, str]]:
    """Read a land-metric source ledger and reject country codes outside the game roster."""
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    unknown_ids = {
        row.get("country_id", "").strip().upper()
        for row in rows
        if row.get("country_id", "").strip().upper() not in country_ids
    }
    if unknown_ids:
        raise ValueError(f"Historical land metric source uses unknown countries: {sorted(unknown_ids)}")
    return rows


def main() -> None:
    country_dir = DATA / "countries"
    with (country_dir / "countries.tsv").open(encoding="utf-8-sig") as stream:
        countries = {row["id"]: {"id": row["id"]} for row in csv.DictReader(stream, delimiter="\t")}
    provenance = []
    protected_areas = historical_protected_area_records(set(countries))
    for code, (source_name, value) in protected_areas.items():
        countries[code]["terrestrial_protected_area_pct_2000"] = value
        countries[code]["terrestrial_protected_area_source"] = "UNSD Environmental Indicators (2010 table)"
        countries[code]["terrestrial_protected_area_method"] = (
            f"UNSD source country: {source_name}; 2000 nationally designated terrestrial protected-area "
            "proportion of total country surface including inland waters; multiple protection categories."
        )
        countries[code]["terrestrial_protected_area_source_url"] = UNSD_PROTECTED_AREAS_URL
        provenance.append(dict(
            id=code,
            field="terrestrial_protected_area_pct_2000",
            year=2001,
            observation_year=2000,
            source="UNSD Environmental Indicators (2010 table)",
            source_note=(
                f"UNSD source country: {source_name}; 2000 nationally designated terrestrial protected-area "
                "proportion as a percent of total country surface area, including inland waters; multiple "
                "protection categories, not national-parks-only"
            ),
            url=UNSD_PROTECTED_AREAS_URL,
        ))
    for code, record in national_park_evidence_records(set(countries)).items():
        countries[code].update(
            national_park_status=record["value_status"],
            national_park_source_url=record["source_url"],
            national_park_denominator_source_url=record["denominator_source_url"],
            national_park_notes=record["notes"],
        )
        for source_field, country_field in (
            ("national_park_land_area_km2", "national_park_land_area_km2_2001"),
            ("national_park_land_coverage_pct", "national_park_land_coverage_pct_2001"),
        ):
            value = record[source_field]
            if value is None:
                continue
            countries[code][country_field] = value
            provenance.append(dict(
                id=code,
                field=country_field,
                year=2001,
                observation_year=2001,
                source="National park 2001 evidence ledger",
                source_note=f"{record['value_status']}: {record['notes']}",
                url=record["source_url"],
            ))
        override = record["terrestrial_protected_area_pct_2000_override"]
        if override is not None:
            if code in protected_areas:
                raise ValueError(f"Protected-area override conflicts with direct UNSD row for {code}")
            override_source = record.get("terrestrial_protected_area_source_name") or (
                "Country-specific protected-area evidence ledger"
            )
            countries[code]["terrestrial_protected_area_pct_2000"] = override
            countries[code]["terrestrial_protected_area_source"] = override_source
            countries[code]["terrestrial_protected_area_method"] = (
                record.get("terrestrial_protected_area_method") or record["notes"]
            )
            countries[code]["terrestrial_protected_area_source_url"] = record["source_url"]
            provenance.append(dict(
                id=code,
                field="terrestrial_protected_area_pct_2000",
                year=2001,
                observation_year=2000,
                source=override_source,
                source_note=(
                    record.get("terrestrial_protected_area_method")
                    or f"{record['value_status']}: {record['notes']}"
                ),
                url=record["source_url"],
            ))
    other_land = faostat_land_use_records(set(countries), write_manifest=True)
    for code, record in other_land.items():
        countries[code]["other_land_pct"] = record["other_land_pct"]
        countries[code]["other_land_source_flag"] = record["other_land_flag"]
        countries[code]["other_land_source_flag_description"] = record["other_land_flag_description"]
        provenance.append(dict(
            id=code,
            field="other_land_pct",
            year=2001,
            observation_year=2001,
            source="FAOSTAT Land Use (RL)",
            source_note=(
                f"FAOSTAT source area: {record['source_country_name']}; Other land / Land area; "
                f"Other land flag {record['other_land_flag']}: {record['other_land_flag_description']}; "
                f"Land area flag {record['land_area_flag']}: {record['land_area_flag_description']}"
            ),
            url="https://www.fao.org/faostat/en/#data/RL",
        ))
    factbook = factbook_records()
    for code, source_values in factbook.items():
        values = {key: value for key, value in source_values.items()
                  if not key.startswith("_")}
        if code in countries:
            countries[code].update(values)
            for field in values:
                climate_field = field == "climate_description"
                provenance.append(dict(
                    id=code,
                    field=field,
                    year=2001,
                    observation_year=source_values.get("_observation_years", {}).get(field),
                    source="CIA Factbook 2001",
                    source_year=2001 if climate_field else None,
                    source_scope=source_values.get("_source_scope") if climate_field else None,
                    source_note=(
                        f"CIA Factbook 2001 country entry for {source_values.get('_source_scope')}; "
                        "climatological context, not a 2001 weather observation."
                        if climate_field else source_values.get("_source_notes", {}).get(
                            field, "CIA Factbook 2001 edition; estimate year not stated"
                        )
                    ),
                    url="https://www.gutenberg.org/ebooks/27638",
                ))
    for code, record in supplemental_climate_context_records(set(countries)).items():
        if countries[code].get("climate_description"):
            continue
        countries[code]["climate_description"] = record["climate_description"]
        provenance.append(dict(
            id=code,
            field="climate_description",
            year=2001,
            observation_year=record["observation_year"],
            source=record["source"],
            source_year=record["source_year"],
            source_scope=record["source_scope"],
            source_note=record["source_note"],
            url=record["url"],
        ))
    for record in observations("SI.POV.NAHC"):
        code = record["countryiso3code"]
        if (code not in countries or record["value"] is None or record["date"] != "2001"
                or "historical_poverty_rate_pct" in countries[code]):
            continue
        countries[code]["historical_poverty_rate_pct"] = float(record["value"])
        countries[code]["historical_poverty_rate_year"] = 2001
        provenance.append(dict(
            id=code,
            field="historical_poverty_rate_pct",
            year=2001,
            observation_year=2001,
            source="SI.POV.NAHC",
            source_scope=record["country"]["value"],
            source_note=(
                "Exact 2001 national poverty headcount ratio; national household-survey estimate "
                "using the country-specific poverty line. National-line estimates are not comparable "
                "across countries. Definition: "
                "https://databank.worldbank.org/metadataglossary/world-development-indicators/series/SI.POV.NAHC"
            ),
            url=("https://api.worldbank.org/v2/country/all/indicator/"
                 "SI.POV.NAHC?date=2001&format=json&per_page=1000"),
        ))
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = executor.map(observations, INDICATORS.values())
        for (field, indicator), records in zip(INDICATORS.items(), results, strict=True):
            provenance.extend(apply_wdi_observations(countries, field, indicator, records))
    country_ids = set(countries)
    land_metric_rows = historical_land_metric_supplement_records(country_ids)
    land_metric_rows.extend(factbook_land_metric_supplement_records(country_ids))
    land_metric_rows.extend(national_land_metric_supplement_records(country_ids))
    provenance.extend(apply_land_metric_supplements(countries, land_metric_rows))
    for code, values in human_development_records().items():
        if code not in countries:
            continue
        countries[code].update(values)
        if "reference_human_dev" in values:
            countries[code]["human_dev"] = values["reference_human_dev"]
            countries[code].update(
                reference_human_dev_status="official_undp_hdr2025",
                reference_human_dev_method="UNDP HDR 2025 retrospective series; observation year 2001.",
                reference_human_dev_source="UNDP Human Development Report 2025",
                reference_human_dev_source_url=UNDP_URL,
            )
        provenance.extend(dict(
            id=code, field=field, year=2001, observation_year=2001,
            source="UNDP HDR 2025", source_note="UNDP HDR 2025 retrospective series; observation year 2001.",
            url=UNDP_URL,
        ) for field in values)
    for code, record in human_development_backfills().items():
        if code not in countries:
            raise ValueError(f"HDI backfill code {code} is not in countries.tsv")
        if "reference_human_dev" in countries[code]:
            raise ValueError(f"HDI backfill {code} conflicts with an UNDP HDR 2025 observation")
        countries[code].update(
            reference_human_dev_status=record["status"],
            reference_human_dev_method=record["method"],
            reference_human_dev_source=record["source"],
            reference_human_dev_source_url=record["source_url"],
        )
        if record["value"] is not None:
            countries[code]["reference_human_dev"] = record["value"]
            countries[code]["human_dev"] = record["simulation_value"]
            provenance.append(dict(
                id=code,
                field="reference_human_dev",
                year=2001,
                observation_year=2001 if record["status"] not in {"regional_estimate_proxy"} else None,
                source=record["source"],
                source_note=f"{record['method']} {record['notes']} Source location: {record['source_location']}.",
                url=record["source_url"],
            ))
        else:
            countries[code]["human_dev"] = record["simulation_value"]
            provenance.append(dict(
                id=code,
                field="human_dev",
                year=2001,
                observation_year=None,
                source=record["source"],
                source_note=(
                    f"{record['method']} {record['notes']} This neutral simulation fallback is not a historical HDI."
                ),
                url=record["source_url"],
            ))
    rows = list(countries.values())
    for row in rows:
        land, total = row.get("reference_land_area_km2"), row.get("reference_total_area_km2")
        if (
            land is not None
            and total is not None
            and total >= land
            and "reference_water_area_km2" not in row
        ):
            row["reference_water_area_km2"] = round(total - land, 6)
            provenance.append(dict(id=row["id"], field="reference_water_area_km2", year=2001,
                                   observation_year=2001,
                                   source="WDI surface area minus land area",
                                   source_note="Derived from 2001 WDI total and land area",
                                   url="https://data.worldbank.org/indicator/AG.SRF.TOTL.K2"))
        row["reference_year"] = 2001
    # Availability survives the loader's numeric-null normalization; an unknown rate is not zero.
    metrics = [field for field in INDICATORS if field not in {"fertility_rate", "life_expectancy"}]
    metrics.extend([
        "reference_water_area_km2", "climate_description", "fertility_rate",
        "life_expectancy", "historical_poverty_rate_pct", "historical_poverty_rate_year",
        "terrestrial_protected_area_pct_2000", "national_park_land_area_km2_2001",
        "national_park_land_coverage_pct_2001", "other_land_pct",
    ])
    metrics.extend(UNDP_METRICS)
    selected_sources = {(row["id"], row["field"]): row for row in provenance}
    metadata_fields = [
        "other_land_source_flag", "other_land_source_flag_description",
        "terrestrial_protected_area_source", "terrestrial_protected_area_method",
        "terrestrial_protected_area_source_url", "national_park_status",
        "national_park_source_url", "national_park_denominator_source_url", "national_park_notes",
        "reference_human_dev_status", "reference_human_dev_method",
        "reference_human_dev_source", "reference_human_dev_source_url",
        "historical_metric_provenance_json",
    ]
    for row in rows:
        for field in metrics:
            row[f"{field}_available"] = field in row
        historical_provenance = {}
        for field in (
            "birth_rate", "death_rate", "fertility_rate", "life_expectancy", "arable_land_pct",
            "forest_area_pct", "reference_land_area_km2", "reference_total_area_km2",
            "reference_water_area_km2", "national_park_land_area_km2_2001",
            "national_park_land_coverage_pct_2001", "other_land_pct", "reference_human_dev",
            "reference_life_expectancy", "expected_years_schooling", "mean_years_schooling",
            "gross_national_income_per_capita_ppp", "terrestrial_protected_area_pct_2000",
            "historical_poverty_rate_pct", "climate_description",
        ):
            source = selected_sources.get((row["id"], field))
            if source is None:
                continue
            record = {
                key: source.get(key)
                for key in (
                    "year", "observation_year", "source", "source_year", "source_scope",
                    "source_note", "url",
                )
            }
            metadata_by_field = {
                "other_land_pct": ("other_land_source_flag", "other_land_source_flag_description"),
                "terrestrial_protected_area_pct_2000": (
                    "terrestrial_protected_area_source", "terrestrial_protected_area_method",
                ),
                "national_park_land_area_km2_2001": ("national_park_status", "national_park_notes"),
                "national_park_land_coverage_pct_2001": ("national_park_status", "national_park_notes"),
                "reference_human_dev": (
                    "reference_human_dev_status", "reference_human_dev_method", "reference_human_dev_source",
                ),
            }
            for metadata_field in metadata_by_field.get(field, ()):
                value = row.get(metadata_field)
                if value not in (None, ""):
                    record[metadata_field] = value
            historical_provenance[field] = record
        row["historical_metric_provenance_json"] = json.dumps(
            historical_provenance, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    fields = ["id", "reference_year", *metrics, *metadata_fields, *(f"{field}_available" for field in metrics)]
    historical_rows = [{key: row[key] for key in fields if key in row} for row in rows]
    write_table(country_dir / "countries_historical.tsv", historical_rows, fields)
    # WDI overrides Factbook estimates for matching metrics, so retain the selected source only.
    write_table(DATA / "sources/2001/provenance.tsv", list(selected_sources.values()),
                ["id", "field", "year", "observation_year", "source", "source_year",
                 "source_scope", "source_note", "url"])
    # Demographic parameters drive population growth; fix the original source rather than only the UI.
    path = country_dir / "countries_dem.tsv"
    with path.open(encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        dem_fields = list(reader.fieldnames or ())
        demographics = list(reader)
    for row in demographics:
        for field in ("fertility_rate", "life_expectancy", "human_dev"):
            # Numeric schema defaults stay finite; countries_historical records availability separately.
            row[field] = countries[row["id"]].get(field, DEFAULT_HUMAN_DEV if field == "human_dev" else 0.0)
        if "historical_poverty_rate_pct" in countries[row["id"]]:
            row["poverty_rate"] = countries[row["id"]]["historical_poverty_rate_pct"] / 100.0
    write_table(path, demographics, dem_fields)
    print(f"Imported {len(provenance)} sourced country fields for {len(rows)} game countries.")


if __name__ == "__main__":
    main()
