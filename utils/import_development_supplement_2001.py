"""Import separately labeled development indicators near the 2001 baseline."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "modules/base/data"
COUNTRIES_PATH = DATA / "countries/countries.tsv"
OUTPUT_PATH = DATA / "countries/countries_development_supplement_2001.tsv"
SOURCE_DIR = DATA / "sources/2001"

WDI_INDICATORS = {
    "school_life_expectancy": "SE.SCH.LIFE",
    "gni_per_capita_ppp_current": "NY.GNP.PCAP.PP.CD",
}
WDI_URLS = {
    code: f"https://api.worldbank.org/v2/country/all/indicator/{code}?date=2001&format=json&per_page=1000"
    for code in WDI_INDICATORS.values()
}
BARROLEE_URL = (
    "https://barrolee.github.io/BarroLeeDataSet/BLData/BL2013_MF1599_v2.2.csv"
)
BARROLEE_25PLUS_URL = (
    "https://barrolee.github.io/BarroLeeDataSet/BLData/BL2013_MF2599_v2.2.csv"
)

FIELD_SPECS = {
    "historical_school_life_expectancy_wdi_years_2001": {
        "label": "School life expectancy, primary to tertiary, both sexes (years)",
        "source": "World Bank WDI SE.SCH.LIFE",
        "url": WDI_URLS[WDI_INDICATORS["school_life_expectancy"]],
        "note": "WDI school life expectancy; retained separately from UNDP expected years of schooling.",
        "observation_year": 2001,
        "scope": "Primary through tertiary education; both sexes.",
    },
    "historical_gni_per_capita_wdi_ppp_current_intl_dollars_2001": {
        "label": "GNI per capita, PPP (current international dollars)",
        "source": "World Bank WDI NY.GNP.PCAP.PP.CD",
        "url": WDI_URLS[WDI_INDICATORS["gni_per_capita_ppp_current"]],
        "note": "Current international-dollar PPP series; retained separately from UNDP's 2021 PPP-dollar measure.",
        "observation_year": 2001,
        "scope": "National income per capita in current international dollars.",
    },
    "historical_mean_schooling_barrolee_years_population_15plus_2000": {
        "label": "Average years of schooling attained, population 15+",
        "source": "Barro-Lee 2013 educational attainment dataset, version 2.2",
        "url": BARROLEE_URL,
        "note": "Retrospective Barro-Lee estimate for 2000; adult population 15+ differs from UNDP mean years of schooling coverage.",
        "observation_year": 2000,
        "scope": "Total population aged 15 and over; both sexes.",
    },
    "historical_mean_schooling_barrolee_years_population_25plus_2000": {
        "label": "Average years of schooling attained, population 25+",
        "source": "Barro-Lee 2013 educational attainment dataset, version 2.2",
        "url": BARROLEE_25PLUS_URL,
        "note": (
            "Retrospective Barro-Lee estimate for 2000; the 25+ population "
            "threshold matches the UNDP mean-schooling age scope, but the source "
            "series and observation year remain distinct."
        ),
        "observation_year": 2000,
        "scope": "Total population aged 25 and over; both sexes.",
    },
}


def _fetch_or_read(path: Path, url: str) -> bytes:
    if path.exists():
        return path.read_bytes()
    request = Request(url, headers={"User-Agent": "OpenPower historical data importer"})
    with urlopen(request, timeout=90) as response:
        payload = response.read()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return payload


def _download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "OpenPower historical data importer"})
    with urlopen(request, timeout=90) as response:
        return response.read()


def _parse_wdi(payload: bytes, *, observation_year: int = 2001) -> dict[str, float]:
    document = json.loads(payload.decode("utf-8-sig"))
    if (
        not isinstance(document, list)
        or len(document) < 2
        or not isinstance(document[1], list)
    ):
        raise ValueError("Unexpected World Bank API response shape.")
    values: dict[str, float] = {}
    for row in document[1]:
        if str(row.get("date") or "") != str(observation_year):
            raise ValueError(
                f"World Bank response includes an unexpected date: {row.get('date')!r}"
            )
        country_id = str(row.get("countryiso3code") or "").strip().upper()
        raw_value = row.get("value")
        if not country_id or raw_value is None:
            continue
        value = float(raw_value)
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid WDI value for {country_id}: {raw_value!r}")
        if country_id in values:
            raise ValueError(f"Duplicate WDI country observation for {country_id}.")
        values[country_id] = value
    return values


def _parse_barrolee(
    payload: bytes, *, age_from: int = 15
) -> dict[str, float]:
    records: dict[str, float] = {}
    stream = io.StringIO(payload.decode("utf-8-sig"), newline="")
    for row in csv.DictReader(stream):
        if (
            row.get("year") != "2000"
            or row.get("sex") != "MF"
            or row.get("agefrom") != str(age_from)
            or row.get("ageto") != "999"
        ):
            continue
        country_id = str(row.get("WBcode") or "").strip().upper()
        try:
            value = float(row["yr_sch"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                f"Invalid Barro-Lee schooling value for {country_id}."
            ) from error
        if not country_id or not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid Barro-Lee record: {row}")
        if country_id in records:
            raise ValueError(
                f"Duplicate Barro-Lee country observation for {country_id}."
            )
        records[country_id] = value
    return records


def build_records(
    country_ids: set[str],
    historical_rows: dict[str, dict[str, str]],
    school_life: dict[str, float],
    gni_ppp_current: dict[str, float],
    barro_lee: dict[str, float],
    barro_lee_25plus: dict[str, float],
) -> list[dict[str, object]]:
    records = []
    sources = {
        "historical_school_life_expectancy_wdi_years_2001": school_life,
        "historical_gni_per_capita_wdi_ppp_current_intl_dollars_2001": gni_ppp_current,
        "historical_mean_schooling_barrolee_years_population_15plus_2000": barro_lee,
        "historical_mean_schooling_barrolee_years_population_25plus_2000": barro_lee_25plus,
    }
    primary_fields = {
        "historical_school_life_expectancy_wdi_years_2001": "expected_years_schooling",
        "historical_gni_per_capita_wdi_ppp_current_intl_dollars_2001": "gross_national_income_per_capita_ppp",
        "historical_mean_schooling_barrolee_years_population_15plus_2000": "mean_years_schooling",
        "historical_mean_schooling_barrolee_years_population_25plus_2000": "mean_years_schooling",
    }
    for country_id in sorted(country_ids):
        row: dict[str, object] = {"id": country_id}
        for field, source_values in sources.items():
            primary_field = primary_fields[field]
            missing_primary = historical_rows.get(country_id, {}).get(
                f"{primary_field}_available", "False"
            ).strip().lower() not in {"true", "1", "yes"}
            value = source_values.get(country_id) if missing_primary else None
            spec = FIELD_SPECS[field]
            row[field] = "" if value is None else value
            row[f"{field}_available"] = value is not None
            row[f"{field}_observation_year"] = (
                spec["observation_year"] if value is not None else ""
            )
            row[f"{field}_source"] = spec["source"] if value is not None else ""
            row[f"{field}_source_url"] = spec["url"] if value is not None else ""
            row[f"{field}_source_scope"] = spec["scope"] if value is not None else ""
            row[f"{field}_source_note"] = spec["note"] if value is not None else ""
        records.append(row)
    return records


def import_supplement() -> dict[str, int]:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    source_paths = {
        "SE.SCH.LIFE": SOURCE_DIR / "SE.SCH.LIFE_2001.json",
        "NY.GNP.PCAP.PP.CD": SOURCE_DIR / "NY.GNP.PCAP.PP.CD_2001.json",
    }
    payloads = {
        indicator: _fetch_or_read(source_paths[indicator], WDI_URLS[indicator])
        for indicator in ("SE.SCH.LIFE", "NY.GNP.PCAP.PP.CD")
    }
    payloads["barrolee"] = _download(BARROLEE_URL)
    payloads["barrolee_25plus"] = _download(BARROLEE_25PLUS_URL)
    country_rows = list(
        csv.DictReader(
            COUNTRIES_PATH.open(encoding="utf-8-sig", newline=""), delimiter="\t"
        )
    )
    country_ids = {
        row["id"].strip().upper() for row in country_rows if row.get("id", "").strip()
    }
    historical_path = DATA / "countries/countries_historical.tsv"
    historical_rows = {
        row["id"].strip().upper(): row
        for row in csv.DictReader(
            historical_path.open(encoding="utf-8-sig", newline=""), delimiter="\t"
        )
        if row.get("id", "").strip()
    }
    parsed = {
        "school_life": _parse_wdi(payloads["SE.SCH.LIFE"]),
        "gni_ppp_current": _parse_wdi(payloads["NY.GNP.PCAP.PP.CD"]),
        "barro_lee": _parse_barrolee(payloads["barrolee"]),
        "barro_lee_25plus": _parse_barrolee(
            payloads["barrolee_25plus"], age_from=25
        ),
    }
    records = build_records(country_ids, historical_rows, **parsed)
    columns = list(records[0]) if records else ["id"]
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output, fieldnames=columns, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(records)

    manifest = {
        "scenario_year": 2001,
        "retrieved_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "sources": {
            source: {
                "url": url,
                "sha256": hashlib.sha256(payloads[source]).hexdigest(),
            }
            for source, url in (
                ("SE.SCH.LIFE", WDI_URLS["SE.SCH.LIFE"]),
                ("NY.GNP.PCAP.PP.CD", WDI_URLS["NY.GNP.PCAP.PP.CD"]),
                ("barrolee", BARROLEE_URL),
                ("barrolee_25plus", BARROLEE_25PLUS_URL),
            )
        },
        "coverage": {
            field: sum(row[field + "_available"] for row in records)
            for field in FIELD_SPECS
        },
        "source_country_counts": {
            "SE.SCH.LIFE": len(parsed["school_life"]),
            "NY.GNP.PCAP.PP.CD": len(parsed["gni_ppp_current"]),
            "Barro-Lee 2000, population 15+": len(parsed["barro_lee"]),
            "Barro-Lee 2000, population 25+": len(parsed["barro_lee_25plus"]),
        },
        "note": "These adjacent or differently defined observations supplement the UNDP 2001 series; they never replace it.",
    }
    (SOURCE_DIR / "development_supplement_2001_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    digest_by_source = {
        source: manifest["sources"][source]["sha256"]
        for source in (
            "SE.SCH.LIFE",
            "NY.GNP.PCAP.PP.CD",
            "barrolee",
            "barrolee_25plus",
        )
    }
    ledger_path = SOURCE_DIR / "development_supplement_2001.tsv"
    ledger_columns = [
        "id",
        "field",
        "value",
        "observation_year",
        "source",
        "source_scope",
        "source_note",
        "source_url",
        "source_sha256",
    ]
    with ledger_path.open("w", encoding="utf-8", newline="") as ledger:
        writer = csv.DictWriter(
            ledger, fieldnames=ledger_columns, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        for record in records:
            for field, spec in FIELD_SPECS.items():
                if not record[f"{field}_available"]:
                    continue
                source_key = (
                    "SE.SCH.LIFE"
                    if field.startswith("historical_school_life")
                    else "NY.GNP.PCAP.PP.CD"
                    if field.startswith("historical_gni_per_capita")
                    else "barrolee_25plus"
                    if field.endswith("population_25plus_2000")
                    else "barrolee"
                )
                writer.writerow(
                    {
                        "id": record["id"],
                        "field": field,
                        "value": record[field],
                        "observation_year": spec["observation_year"],
                        "source": spec["source"],
                        "source_scope": spec["scope"],
                        "source_note": spec["note"],
                        "source_url": spec["url"],
                        "source_sha256": digest_by_source[source_key],
                    }
                )
    return manifest["coverage"]


if __name__ == "__main__":
    print(json.dumps(import_supplement(), indent=2))
