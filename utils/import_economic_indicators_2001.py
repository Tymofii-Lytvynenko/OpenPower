"""Import exact-year World Bank and IMF economic observations into a country extension."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "modules/base/data"
COUNTRY_IDS_PATH = DATA / "countries/countries.tsv"
COUNTRY_EXTENSION_PATH = DATA / "countries/countries_economic_historical.tsv"
SOURCE_DIR = DATA / "sources/2001"
LEDGER_PATH = SOURCE_DIR / "economic_indicators_2001.tsv"
REPORT_PATH = SOURCE_DIR / "economic_indicators_2001.md"
SCENARIO_YEAR = 2001

INDICATORS = {
    "historical_gdp_current_usd_2001": {
        "code": "NY.GDP.MKTP.CD",
        "unit": "current US$",
        "name": "GDP (current US$)",
        "note": (
            "GDP at purchasers' prices, expressed in current US dollars. This is a "
            "nominal historical observation and is not adjusted for inflation."
        ),
    },
    "historical_gdp_per_capita_current_usd_2001": {
        "code": "NY.GDP.PCAP.CD",
        "unit": "current US$/person",
        "name": "GDP per capita (current US$)",
        "note": (
            "GDP divided by midyear population, expressed in current US dollars per "
            "person. This is a nominal historical observation, not the live simulated "
            "GDP divided by currently controlled regional population."
        ),
    },
    "historical_inflation_cpi_pct_2001": {
        "code": "FP.CPI.TOTL.ZG",
        "unit": "%/year",
        "name": "Inflation, consumer prices (annual %)",
        "note": (
            "Annual percentage change in consumer prices. The WDI series can differ "
            "from OpenPower's live inflation mechanic and is presented only as a "
            "historical reference."
        ),
    },
    "historical_unemployment_modeled_ilo_pct_2001": {
        "code": "SL.UEM.TOTL.ZS",
        "unit": "% of labor force",
        "name": "Unemployment, total (% of total labor force), modeled ILO estimate",
        "note": (
            "Share of the labor force without work but available for and seeking "
            "employment. This is the modeled ILO estimate series (ILOEST), not a "
            "uniformly observed country survey count."
        ),
    },
}

WDI_API_URL = "https://api.worldbank.org/v2/country/all/indicator/{indicator}"
WDI_PAGE_URL = "https://data.worldbank.org/indicator/{indicator}"
IMF_WEO_API_URL = "https://www.imf.org/external/datamapper/api/v2/{indicator}?periods={year}"
IMF_WEO_RELEASE = "World Economic Outlook, October 2026"
IMF_WEO_COUNTRY_ALIASES = {"KOS": ("UVK",)}
IMF_WEO_FALLBACKS = {
    "historical_gdp_current_usd_2001": {
        "code": "NGDPD",
        "unit": "current US$",
        "scale": 1_000_000_000,
        "note": (
            "IMF WEO GDP at current prices, published in billions of U.S. dollars; "
            "the imported value is scaled to dollars. This fills a blank WDI entry only. "
            "WEO historical values are retrospective IMF staff data and can include staff estimates."
        ),
    },
    "historical_gdp_per_capita_current_usd_2001": {
        "code": "NGDPDPC",
        "unit": "current US$/person",
        "scale": 1.0,
        "note": (
            "IMF WEO GDP per capita at current prices in U.S. dollars per person. "
            "This fills a blank WDI entry only; retrospective WEO data can include IMF staff estimates."
        ),
    },
    "historical_inflation_cpi_pct_2001": {
        "code": "PCPIPCH",
        "unit": "%/year",
        "scale": 1.0,
        "note": (
            "IMF WEO inflation rate, average consumer prices, annual percent change. "
            "This fills a blank WDI entry only; it is not the live OpenPower rate. "
            "Retrospective WEO data can include IMF staff estimates."
        ),
    },
}
IMF_WEO_ALTERNATIVES = {
    "historical_unemployment_imf_weo_pct_2001": {
        "code": "LUR",
        "unit": "% of labor force",
        "label": "IMF WEO unemployment rate (alternative to modeled ILO series)",
        "note": (
            "IMF WEO unemployment rate, percent of the labor force. This is retained "
            "as a separate series and does not fill the World Bank modeled ILOEST field. "
            "Retrospective WEO data can include IMF staff estimates."
        ),
    },
}


def parse_wdi_payload(payload: bytes, indicator: str, allowed_country_ids: set[str]) -> dict[str, dict]:
    """Select only finite national observations dated exactly to the scenario year."""
    try:
        body = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid WDI response for {indicator}") from error
    if not isinstance(body, list) or len(body) != 2 or not isinstance(body[1], list):
        raise ValueError(f"Unexpected WDI response structure for {indicator}")

    values: dict[str, dict] = {}
    for row in body[1]:
        if not isinstance(row, dict) or str(row.get("date", "")) != str(SCENARIO_YEAR):
            continue
        country_id = str(row.get("countryiso3code") or "").strip().upper()
        if country_id not in allowed_country_ids:
            continue
        raw_value = row.get("value")
        if raw_value is None:
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(value):
            continue
        if country_id in values:
            raise ValueError(f"Duplicate {indicator} observation for {country_id}")
        values[country_id] = {
            "value": value,
            "observation_year": SCENARIO_YEAR,
            "country_name": str((row.get("country") or {}).get("value") or ""),
        }
    return values


def parse_imf_weo_payload(
    payload: bytes,
    indicator: str,
    allowed_country_ids: set[str],
    *,
    scale: float = 1.0,
) -> dict[str, dict]:
    """Read only 2001 IMF WEO points, mapping the documented Kosovo series code."""
    try:
        body = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid IMF WEO response for {indicator}") from error
    values = body.get("values", {}).get(indicator) if isinstance(body, dict) else None
    if not isinstance(values, dict):
        raise ValueError(f"Unexpected IMF WEO response structure for {indicator}")

    selected: dict[str, dict] = {}
    for country_id in sorted(allowed_country_ids):
        source_codes = (country_id, *IMF_WEO_COUNTRY_ALIASES.get(country_id, ()))
        for source_code in source_codes:
            series = values.get(source_code)
            if not isinstance(series, dict) or str(SCENARIO_YEAR) not in series:
                continue
            try:
                value = float(series[str(SCENARIO_YEAR)]) * scale
            except (TypeError, ValueError, OverflowError):
                continue
            if not math.isfinite(value):
                continue
            selected[country_id] = {
                "value": value,
                "observation_year": SCENARIO_YEAR,
                "source_country_code": source_code,
            }
            break
    return selected


def read_country_ids(path: Path = COUNTRY_IDS_PATH) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        ids = [str(row.get("id") or "").strip().upper() for row in csv.DictReader(stream, delimiter="\t")]
    if not ids or any(not country_id for country_id in ids) or len(set(ids)) != len(ids):
        raise ValueError(f"Country roster has empty or duplicate IDs: {path}")
    return ids


def _fetch_payload(indicator: str) -> tuple[bytes, str, dict]:
    cache_path = SOURCE_DIR / f"{indicator}.json"
    if not cache_path.exists():
        url = f"{WDI_API_URL.format(indicator=indicator)}?date={SCENARIO_YEAR}&format=json&per_page=1000"
        request = Request(url, headers={"User-Agent": "OpenPower historical data importer/1.0"})
        with urlopen(request, timeout=90) as response:
            payload = response.read()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(payload)
    payload = cache_path.read_bytes()
    try:
        response = json.loads(payload)
        metadata = response[0]
    except (UnicodeDecodeError, json.JSONDecodeError, IndexError, TypeError) as error:
        raise ValueError(f"Cached WDI response is invalid: {cache_path}") from error
    if not isinstance(metadata, dict) or metadata.get("message"):
        raise ValueError(f"WDI returned an error for {indicator}: {metadata}")
    manifest = {
        "indicator": indicator,
        "scenario_year": SCENARIO_YEAR,
        "observation_year_filter": str(SCENARIO_YEAR),
        "url": f"{WDI_API_URL.format(indicator=indicator)}?date={SCENARIO_YEAR}&format=json&per_page=1000",
        "data_url": WDI_PAGE_URL.format(indicator=indicator),
        "source_release_last_updated": str(metadata.get("lastupdated") or ""),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    cache_path.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return payload, manifest["source_release_last_updated"], manifest


def _fetch_imf_weo_payload(indicator: str) -> tuple[bytes, dict]:
    cache_path = SOURCE_DIR / f"imf_weo_2026_{indicator}.json"
    url = IMF_WEO_API_URL.format(indicator=indicator, year=SCENARIO_YEAR)
    if not cache_path.exists():
        with urlopen(url, timeout=90) as response:
            payload = response.read()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(payload)
    payload = cache_path.read_bytes()
    try:
        body = json.loads(payload)
        metadata = body["indicators"][indicator]
        if indicator not in body.get("values", {}):
            raise ValueError(f"IMF WEO response has no values for {indicator}")
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError(f"Cached IMF WEO response is invalid: {cache_path}") from error
    manifest = {
        "indicator": indicator,
        "release": IMF_WEO_RELEASE,
        "scenario_year_filter": SCENARIO_YEAR,
        "url": url,
        "country_catalog_url": "https://www.imf.org/external/datamapper/api/v2/countries",
        "label": str(metadata.get("label") or ""),
        "unit": str(metadata.get("unit") or ""),
        "source_last_modified": str(metadata.get("last-modified") or ""),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    cache_path.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return payload, manifest


def load_source_records(country_ids: list[str], *, fetch: bool = True) -> tuple[dict[str, dict[str, dict]], dict[str, dict]]:
    records: dict[str, dict[str, dict]] = {country_id: {} for country_id in country_ids}
    manifests: dict[str, dict] = {}
    allowed = set(country_ids)
    for field, definition in INDICATORS.items():
        indicator = definition["code"]
        cache_path = SOURCE_DIR / f"{indicator}.json"
        if fetch:
            payload, _release, manifest = _fetch_payload(indicator)
        else:
            payload = cache_path.read_bytes()
            manifest_path = cache_path.with_suffix(".manifest.json")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        parsed = parse_wdi_payload(payload, indicator, allowed)
        manifests[field] = manifest
        for country_id, observation in parsed.items():
            observation["provenance"] = _wdi_provenance(field, manifest)
            records[country_id][field] = observation

    for field, definition in IMF_WEO_FALLBACKS.items():
        indicator = definition["code"]
        cache_path = SOURCE_DIR / f"imf_weo_2026_{indicator}.json"
        if fetch:
            payload, manifest = _fetch_imf_weo_payload(indicator)
        else:
            payload = cache_path.read_bytes()
            manifest_path = cache_path.with_suffix(".manifest.json")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        parsed = parse_imf_weo_payload(
            payload, indicator, allowed, scale=definition["scale"]
        )
        manifests[f"imf_{indicator}"] = manifest
        for country_id, observation in parsed.items():
            if field in records[country_id]:
                continue
            observation["provenance"] = _imf_weo_provenance(
                field, definition, manifest, observation["source_country_code"]
            )
            records[country_id][field] = observation

    for field, definition in IMF_WEO_ALTERNATIVES.items():
        indicator = definition["code"]
        cache_path = SOURCE_DIR / f"imf_weo_2026_{indicator}.json"
        if fetch:
            payload, manifest = _fetch_imf_weo_payload(indicator)
        else:
            payload = cache_path.read_bytes()
            manifest_path = cache_path.with_suffix(".manifest.json")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        parsed = parse_imf_weo_payload(payload, indicator, allowed)
        manifests[f"imf_{indicator}"] = manifest
        for country_id, observation in parsed.items():
            if "historical_unemployment_modeled_ilo_pct_2001" in records[country_id]:
                continue
            observation["provenance"] = _imf_weo_provenance(
                field, definition, manifest, observation["source_country_code"]
            )
            records[country_id][field] = observation
    return records, manifests


def _wdi_provenance(field: str, manifest: dict) -> dict:
    definition = INDICATORS[field]
    indicator = definition["code"]
    return {
        "scenario_year": SCENARIO_YEAR,
        "observation_year": SCENARIO_YEAR,
        "source": "World Bank, World Development Indicators",
        "indicator": indicator,
        "source_url": WDI_PAGE_URL.format(indicator=indicator),
        "source_note": definition["note"],
        "unit": definition["unit"],
        "source_release": manifest.get("source_release_last_updated", ""),
    }


def _imf_weo_provenance(
    field: str, definition: dict, manifest: dict, source_country_code: str
) -> dict:
    indicator = definition["code"]
    provenance = {
        "scenario_year": SCENARIO_YEAR,
        "observation_year": SCENARIO_YEAR,
        "source": IMF_WEO_RELEASE,
        "indicator": indicator,
        "source_url": manifest["url"],
        "source_note": definition["note"],
        "unit": definition["unit"],
        "source_release": manifest.get("source_last_modified", ""),
    }
    if source_country_code == "UVK":
        provenance["source_country_code_mapping"] = (
            "Game country KOS uses IMF WEO code UVK; the IMF country catalog labels UVK Kosovo."
        )
    return provenance


ALL_INDICATORS = {**INDICATORS, **IMF_WEO_ALTERNATIVES}


def write_outputs(country_ids: list[str], records: dict[str, dict[str, dict]]) -> None:
    extension_columns = ["id"]
    for field in ALL_INDICATORS:
        extension_columns.extend((field, f"{field}_available"))
    extension_columns.append("historical_economic_provenance_json")
    with COUNTRY_EXTENSION_PATH.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=extension_columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for country_id in country_ids:
            country_records = records.get(country_id, {})
            row = {"id": country_id}
            provenance = {}
            for field in ALL_INDICATORS:
                observation = country_records.get(field)
                row[field] = format(observation["value"], ".15g") if observation is not None else ""
                row[f"{field}_available"] = "true" if observation is not None else "false"
                if observation is not None:
                    provenance[field] = observation["provenance"]
            row["historical_economic_provenance_json"] = json.dumps(
                provenance, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )
            writer.writerow(row)

    ledger_columns = [
        "country_id", "field", "scenario_year", "observation_year", "value", "unit",
        "indicator_code", "source_name", "source_release", "source_url", "source_note",
    ]
    with LEDGER_PATH.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=ledger_columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for country_id in country_ids:
            for field, observation in sorted(records.get(country_id, {}).items()):
                provenance = observation["provenance"]
                writer.writerow({
                    "country_id": country_id,
                    "field": field,
                    "scenario_year": SCENARIO_YEAR,
                    "observation_year": observation["observation_year"],
                    "value": format(observation["value"], ".15g"),
                    "unit": provenance["unit"],
                    "indicator_code": provenance["indicator"],
                    "source_name": provenance["source"],
                    "source_release": provenance.get("source_release", ""),
                    "source_url": provenance["source_url"],
                    "source_note": provenance["source_note"],
                })
    _write_report(country_ids, records)


def _write_report(country_ids: list[str], records: dict[str, dict[str, dict]]) -> None:
    total = len(country_ids)
    lines = [
        "# 2001 economic baselines",
        "",
        "Generated by `utils/import_economic_indicators_2001.py` from archived World Bank and IMF API responses.",
        "Only observations dated exactly 2001 are included. Missing observations remain blank and have an explicit `false` availability flag; no adjacent-year values are substituted.",
        "These are read-only historical baselines. They do not overwrite the live `gdp`, `inflation_rate`, or other OpenPower simulation state.",
        "GDP values are current US dollars and therefore nominal rather than inflation-adjusted. Both sources are retrospective revisions, not a reconstruction of what was known on 1 January 2001.",
        "",
        "| Field | WDI observations | IMF WEO supplements | Total available | Roster coverage |",
        "|---|---:|---:|---:|---:|",
    ]
    for field, _definition in INDICATORS.items():
        observations = [records.get(country_id, {}).get(field) for country_id in country_ids]
        wdi_count = sum(bool(item and item["provenance"]["source"].startswith("World Bank")) for item in observations)
        imf_count = sum(bool(item and item["provenance"]["source"].startswith("World Economic Outlook")) for item in observations)
        count = wdi_count + imf_count
        lines.append(f"| `{field}` | {wdi_count} | {imf_count} | {count} | {count}/{total} ({count / total:.1%}) |")
    alternate_count = sum(
        "historical_unemployment_imf_weo_pct_2001" in records.get(country_id, {})
        for country_id in country_ids
    )
    lines.append(
        f"| `historical_unemployment_imf_weo_pct_2001` (separate alternate series) | 0 | {alternate_count} | {alternate_count} | {alternate_count}/{total} ({alternate_count / total:.1%}) |"
    )
    lines.extend((
        "",
        "## Definitions and caveats",
        "",
        "- World Bank WDI is the primary source for GDP, GDP per capita, and consumer-price inflation; IMF WEO fills only missing WDI cells with its corresponding exact-2001 current-price or annual consumer-price series.",
        "- GDP per capita is each source's published per-person series; it is not recalculated from the game's live GDP or territory population.",
        "- Inflation is an annual consumer-price series, not the game's current policy or simulated rate.",
        "- World Bank unemployment is the modeled ILO estimate (ILOEST), expressed as a percentage of the labor force; it is not a uniform survey observation.",
        "- IMF WEO unemployment is a separate alternative series, never substituted into the modeled ILO field. Its historical data may include IMF staff estimates.",
        "- IMF WEO fallbacks fill only blank WDI fields. The WEO API reports current-price GDP in billions of U.S. dollars; the importer scales that value to dollars. Kosovo maps to the WEO country code `UVK` only when the direct game-matching code has no 2001 value.",
        "- The IMF WEO October 2026 dataset and API documentation are available at https://data.imf.org/en/datasets/IMF.RES%3AWEO and https://www.imf.org/external/datamapper/api/help. Its documentation cautions that historical series are revised and may use IMF staff estimates.",
        "- The country extension carries a per-field provenance JSON record with scenario year, observation year, URL, note, indicator, and unit. The source ledger records the same details row by row.",
        "",
        "## Filled IDs and remaining gaps",
    ))
    for field in (
        "historical_gdp_current_usd_2001",
        "historical_gdp_per_capita_current_usd_2001",
        "historical_inflation_cpi_pct_2001",
    ):
        imf_ids = sorted(
            country_id
            for country_id in country_ids
            if field in records.get(country_id, {})
            and records[country_id][field]["provenance"]["source"].startswith("World Economic Outlook")
        )
        remaining_ids = sorted(
            country_id for country_id in country_ids if field not in records.get(country_id, {})
        )
        lines.append(
            f"- `{field}`: IMF WEO filled {len(imf_ids)} WDI gaps (`{', '.join(imf_ids) or 'none'}`); "
            f"still unavailable: `{', '.join(remaining_ids) or 'none'}`."
        )
    ilo_missing = sorted(
        country_id
        for country_id in country_ids
        if "historical_unemployment_modeled_ilo_pct_2001" not in records.get(country_id, {})
    )
    imf_unemployment = sorted(
        country_id
        for country_id in country_ids
        if "historical_unemployment_imf_weo_pct_2001" in records.get(country_id, {})
    )
    lines.append(
        f"- Modeled ILO unemployment remains unavailable for `{', '.join(ilo_missing)}`. "
        f"The distinct IMF WEO unemployment series is available for `{', '.join(imf_unemployment)}`; it does not close the ILO series gaps."
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    country_ids = read_country_ids()
    records, _manifests = load_source_records(country_ids)
    write_outputs(country_ids, records)
    print(f"Wrote {COUNTRY_EXTENSION_PATH.relative_to(ROOT)} and {LEDGER_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
