"""Generate transparent gameplay proxies for unresolved 2001 macro fields."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "modules/base/data"
COUNTRIES_PATH = DATA_DIR / "countries/countries.tsv"
ECONOMICS_PATH = DATA_DIR / "countries/countries_economic_historical.tsv"
REGIONS_POP_PATH = DATA_DIR / "regions/regions_pop.tsv"
POPULATION_PROVENANCE_PATH = (
    DATA_DIR / "sources/2001/regional_population_provenance.tsv"
)
OUTPUT_PATH = DATA_DIR / "countries/countries_economic_gameplay_proxies_2001.tsv"
LEDGER_OUTPUT_PATH = DATA_DIR / "sources/2001/economic_gameplay_proxy_ledger_2001.tsv"

SCENARIO_YEAR = 2001
GDP_PER_CAPITA = "historical_gdp_per_capita_current_usd_2001"
CPI = "historical_inflation_cpi_pct_2001"
UNEMPLOYMENT = "historical_unemployment_modeled_ilo_pct_2001"
GDP = "historical_gdp_current_usd_2001"
GDP_INDICATOR = "NY.GDP.MKTP.CD"
GDP_PER_CAPITA_INDICATOR = "NY.GDP.PCAP.CD"
CPI_INDICATOR = "FP.CPI.TOTL.ZG"
UNEMPLOYMENT_INDICATOR = "SL.UEM.TOTL.ZS"

WDI_API = "https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
FACTBOOK_2001_URL = "https://www.gutenberg.org/ebooks/27638"
NAURU_FACTBOOK_URL = "https://www.thefactbook.org/nauru/2001"
MONACO_STATISTICS_URL = "https://www.imsee.mc/"

GDP_PER_CAPITA_PEERS = {"SSD": "SDN", "VAT": "ITA"}
GDP_POPULATION_TARGETS = {"SSD": "SDN", "VAT": "ITA"}

CPI_MODELS = {
    "MCO": {"kind": "single", "peers": ("FRA",)},
    "NRU": {"kind": "single", "peers": ("AUS",)},
    "PRK": {"kind": "median", "peers": ("CHN", "KOR", "MNG", "VNM")},
    "SOM": {"kind": "median", "peers": ("DJI", "ETH", "KEN", "SDN", "YEM")},
    "SSD": {"kind": "single", "peers": ("SDN",)},
    "VAT": {"kind": "single", "peers": ("ITA",)},
}

OUTPUT_COLUMNS = (
    "id",
    "target_field",
    "value",
    "available",
    "unit",
    "scenario_year",
    "observation_year",
    "source_year",
    "source_scope",
    "estimate_type",
    "method",
    "source_inputs_json",
    "confidence",
    "source_urls",
    "source_note",
)
PROXY_FIELDS = (GDP, GDP_PER_CAPITA, CPI, UNEMPLOYMENT)
PROXY_SUFFIXES = ("value", "available", "provenance_json")
RUNTIME_COLUMNS = (
    "id",
    *(
        f"{field}_gameplay_proxy_{suffix}"
        for field in PROXY_FIELDS
        for suffix in PROXY_SUFFIXES
    ),
)

FIELD_UNITS = {
    GDP: "current US$",
    GDP_PER_CAPITA: "current US$/person",
    CPI: "%/year",
    UNEMPLOYMENT: "% of labor force",
}


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def _number(value: str | int | float | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Expected finite number, got {value!r}")
    return number


def _format(value: float) -> str:
    return f"{value:.6f}"


def _source_url(country_id: str, indicator: str) -> str:
    return (
        WDI_API.format(country=country_id, indicator=indicator)
        + "?date=2001&format=json&per_page=1000"
    )


def _read_economics(path: Path) -> dict[str, dict[str, str]]:
    rows = _read_tsv(path)
    result = {row["id"].strip().upper(): row for row in rows}
    if len(result) != len(rows):
        raise ValueError(f"Duplicate country rows in {path}")
    return result


def _read_population(path: Path) -> dict[str, int]:
    totals: dict[str, int] = {}
    for row in _read_tsv(path):
        country_id = row["_owner"].strip().upper()
        population = sum(
            int(_number(row.get(column)) or 0)
            for column in ("pop_14", "pop_15_64", "pop_65")
        )
        totals[country_id] = totals.get(country_id, 0) + population
    return totals


def _read_population_provenance(path: Path) -> dict[str, dict]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in _read_tsv(path):
        grouped.setdefault(row["owner"].strip().upper(), []).append(row)
    result = {}
    for country_id, rows in grouped.items():
        result[country_id] = {
            "sources": sorted({row["source"] for row in rows if row["source"]}),
            "source_urls": sorted(
                {row["source_url"] for row in rows if row["source_url"]}
            ),
            "source_iso3": sorted(
                {row["source_iso3"] for row in rows if row["source_iso3"]}
            ),
            "years": sorted({row["year"] for row in rows if row["year"]}),
        }
    return result


def _historical_value(
    economics: dict[str, dict[str, str]],
    country_id: str,
    field: str,
    *,
    require_wdi: bool = True,
) -> tuple[float, dict]:
    row = economics[country_id]
    if row.get(f"{field}_available", "").lower() != "true":
        raise ValueError(f"Missing required source value {country_id}:{field}")
    value = _number(row.get(field))
    if value is None:
        raise ValueError(f"Available source value is blank: {country_id}:{field}")
    provenance = json.loads(row.get("historical_economic_provenance_json") or "{}")
    source = provenance.get(field) or {}
    if source.get("observation_year") != SCENARIO_YEAR:
        raise ValueError(f"Non-2001 observation used for {country_id}:{field}")
    if require_wdi and "World Bank" not in str(source.get("source") or ""):
        raise ValueError(f"Expected a WDI observation for {country_id}:{field}")
    return value, source


def _input_json(items: list[dict]) -> str:
    return json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _proxy_row(
    *,
    country_id: str,
    field: str,
    value: float,
    source_year: str,
    source_scope: str,
    method: str,
    inputs: list[dict],
    confidence: str,
    source_urls: list[str],
    note: str,
) -> dict[str, str]:
    return {
        "id": country_id,
        "target_field": field,
        "value": _format(value),
        "available": "true",
        "unit": FIELD_UNITS[field],
        "scenario_year": str(SCENARIO_YEAR),
        "observation_year": "",
        "source_year": source_year,
        "source_scope": source_scope,
        "estimate_type": "gameplay_proxy",
        "method": method,
        "source_inputs_json": _input_json(inputs),
        "confidence": confidence,
        "source_urls": " | ".join(sorted(set(source_urls))),
        "source_note": f"Gameplay proxy. {note}",
    }


def _not_applicable_row(country_id: str, field: str) -> dict[str, str]:
    return {
        "id": country_id,
        "target_field": field,
        "value": "",
        "available": "false",
        "unit": FIELD_UNITS[field],
        "scenario_year": str(SCENARIO_YEAR),
        "observation_year": "",
        "source_year": "",
        "source_scope": "No permanent resident national economy or labor market.",
        "estimate_type": "not_applicable",
        "method": "No numeric value is inferred; an unavailable field is not encoded as zero.",
        "source_inputs_json": "[]",
        "confidence": "not_applicable",
        "source_urls": "",
        "source_note": (
            "Antarctica has no permanent resident population, national consumer-price basket, "
            "or independent national accounts/labor-force series in 2001."
        ),
    }


def generate_rows(
    *,
    countries_path: Path = COUNTRIES_PATH,
    economics_path: Path = ECONOMICS_PATH,
    regions_pop_path: Path = REGIONS_POP_PATH,
    population_provenance_path: Path = POPULATION_PROVENANCE_PATH,
) -> list[dict[str, str]]:
    country_ids = [row["id"].strip().upper() for row in _read_tsv(countries_path)]
    if len(country_ids) != len(set(country_ids)):
        raise ValueError("Duplicate game-country IDs")
    economics = _read_economics(economics_path)
    if set(country_ids) != set(economics):
        raise ValueError("Economic table does not match the game-country roster")
    populations = _read_population(regions_pop_path)
    population_provenance = _read_population_provenance(population_provenance_path)

    rows: list[dict[str, str]] = []
    for field in (GDP, GDP_PER_CAPITA, CPI, UNEMPLOYMENT):
        rows.append(_not_applicable_row("ATA", field))

    # The GDP per-capita comparators are direct 2001 WDI values; regional
    # population provides the multiplier only for the total-GDP scenario proxy.
    gdp_pc_values = {}
    for target_id, peer_id in GDP_PER_CAPITA_PEERS.items():
        value, provenance = _historical_value(economics, peer_id, GDP_PER_CAPITA)
        gdp_pc_values[target_id] = (value, peer_id, provenance)
    for target_id, peer_id in GDP_POPULATION_TARGETS.items():
        if target_id not in populations or target_id not in population_provenance:
            raise ValueError(f"Missing regional population inputs for {target_id}")
        if population_provenance[target_id]["years"] != [str(SCENARIO_YEAR)]:
            raise ValueError(f"Non-2001 population provenance for {target_id}")
        population = populations[target_id]
        if population <= 0:
            raise ValueError(f"Non-positive population for GDP proxy {target_id}")
        per_capita, _, per_capita_provenance = gdp_pc_values[target_id]
        pop_sources = population_provenance[target_id]
        pop_urls = pop_sources["source_urls"]
        pop_inputs = {
            "country_id": target_id,
            "population_2001": population,
            "population_source": "; ".join(pop_sources["sources"]),
            "population_source_iso3": ",".join(pop_sources["source_iso3"]),
            "population_source_urls": pop_urls,
        }
        gdp_value = per_capita * population
        per_capita_note = (
            f"Uses {peer_id}'s observed 2001 WDI GDP per capita as a gameplay proxy; "
            "the target has no separate compatible national-accounts observation."
        )
        if target_id == "SSD":
            per_capita_note += (
                " South Sudan was part of Sudan in 2001; assigning Sudan's national average "
                "to the territory does not measure South Sudan's own output."
            )
        else:
            per_capita_note += (
                " Italy's GDP-per-capita level does not measure Vatican City State's "
                "institutional, visitor, or cross-border economic activity."
            )
        rows.append(
            _proxy_row(
                country_id=target_id,
                field=GDP_PER_CAPITA,
                value=per_capita,
                source_year="2001",
                source_scope=f"{peer_id} country-level GDP per capita applied as a {target_id} proxy.",
                method=f"Copy {peer_id} 2001 WDI GDP per capita as a territory/neighbour gameplay proxy.",
                inputs=[
                    {
                        "country_id": peer_id,
                        "field": GDP_PER_CAPITA,
                        "value": _format(per_capita),
                        "source": per_capita_provenance.get("source"),
                        "source_url": per_capita_provenance.get("source_url"),
                        "observation_year": SCENARIO_YEAR,
                    }
                ],
                confidence="very_low",
                source_urls=[per_capita_provenance.get("source_url", "")],
                note=per_capita_note,
            )
        )
        rows.append(
            _proxy_row(
                country_id=target_id,
                field=GDP,
                value=gdp_value,
                source_year="2001",
                source_scope=(
                    f"Proxy GDP per capita from {peer_id} multiplied by 2001 regional "
                    f"population estimate for {target_id}."
                ),
                method=f"{peer_id} 2001 WDI GDP per capita × {target_id} 2001 scenario population.",
                inputs=[
                    {
                        "country_id": peer_id,
                        "field": GDP_PER_CAPITA,
                        "value": _format(per_capita),
                        "source": per_capita_provenance.get("source"),
                        "source_url": per_capita_provenance.get("source_url"),
                        "observation_year": SCENARIO_YEAR,
                    },
                    pop_inputs,
                ],
                confidence="very_low",
                source_urls=[per_capita_provenance.get("source_url", ""), *pop_urls],
                note=(
                    per_capita_note
                    + f" Population is a 2001 WorldPop/regional baseline estimate ({population:,}); "
                    "the product is a gameplay scenario proxy, not a national-accounts observation."
                ),
            )
        )

    for target_id, model in CPI_MODELS.items():
        peer_values = []
        inputs = []
        peer_urls = []
        for peer_id in model["peers"]:
            value, provenance = _historical_value(economics, peer_id, CPI)
            peer_values.append(value)
            peer_urls.append(provenance.get("source_url", ""))
            inputs.append(
                {
                    "country_id": peer_id,
                    "field": CPI,
                    "value": _format(value),
                    "source": provenance.get("source"),
                    "source_url": provenance.get("source_url"),
                    "observation_year": SCENARIO_YEAR,
                }
            )
        proxy_value = (
            peer_values[0]
            if model["kind"] == "single"
            else statistics.median(peer_values)
        )
        peers = ", ".join(model["peers"])
        if target_id == "MCO":
            note = (
                "France's 2001 WDI CPI is used as a gameplay proxy. Monaco's later official "
                "statistical material references French CPI, but this does not establish a "
                "Monaco-wide 2001 observation."
            )
        elif target_id == "NRU":
            note = (
                "Australia's 2001 WDI CPI is used because the 2001 CIA Factbook lists the "
                "Australian dollar for Nauru. The Australian consumption basket is not a "
                "Nauru CPI and local import prices can differ."
            )
            peer_urls.append(NAURU_FACTBOOK_URL)
        elif target_id == "SSD":
            note = (
                "Sudan's 2001 WDI CPI is used as a territory proxy. South Sudan was part of "
                "Sudan in 2001, and the source does not report a separate South Sudan price basket."
            )
        elif target_id == "VAT":
            note = (
                "Italy's 2001 WDI CPI is used as a nearby-market gameplay proxy. It is not a "
                "measured Vatican City consumer-price index."
            )
        elif target_id == "PRK":
            note = (
                "The median of 2001 WDI CPI rates for nearby China, Republic of Korea, Mongolia, "
                "and Viet Nam is a scenario proxy. It cannot reconstruct a DPRK national CPI; "
                "available DPRK basket estimates are not comparable all-items series."
            )
        else:
            note = (
                "The median of 2001 WDI CPI rates for Djibouti, Ethiopia, Kenya, Sudan, and Yemen "
                "is a regional gameplay proxy. It is not a Somalia national all-items CPI."
            )
        rows.append(
            _proxy_row(
                country_id=target_id,
                field=CPI,
                value=proxy_value,
                source_year="2001",
                source_scope=f"{peers} 2001 CPI comparison; no separate compatible {target_id} series.",
                method=(
                    f"Use the 2001 WDI CPI rate from {peers}."
                    if model["kind"] == "single"
                    else f"Take the median 2001 WDI CPI rate across {peers}."
                ),
                inputs=inputs,
                confidence="low" if model["kind"] == "single" else "very_low",
                source_urls=[*peer_urls, MONACO_STATISTICS_URL]
                if target_id == "MCO"
                else peer_urls,
                note=note,
            )
        )

    # Andorra's 2001 Factbook edition gives a 0% rate but omits the reference
    # year and labor-force definition; retain it as a low-confidence prior only.
    rows.append(
        _proxy_row(
            country_id="AND",
            field=UNEMPLOYMENT,
            value=0.0,
            source_year="2001 Factbook edition",
            source_scope="Country entry; observation year and labor-force definition unspecified.",
            method="Carry the edition's published 0% rate as a scenario prior; do not treat it as a dated 2001 series.",
            inputs=[
                {
                    "country_id": "AND",
                    "field": "CIA Factbook unemployment rate",
                    "value": "0",
                    "source": "CIA World Factbook 2001",
                    "source_url": FACTBOOK_2001_URL,
                    "observation_year": None,
                }
            ],
            confidence="very_low",
            source_urls=[FACTBOOK_2001_URL],
            note=(
                "The Factbook 2001 country entry reports 0% but does not state the underlying "
                "observation year or labor-force definition. Kept as a scenario prior only; "
                "not an observed 2001 ILO unemployment rate."
            ),
        )
    )

    vat_unemployment, vat_provenance = _historical_value(economics, "ITA", UNEMPLOYMENT)
    rows.append(
        _proxy_row(
            country_id="VAT",
            field=UNEMPLOYMENT,
            value=vat_unemployment,
            source_year="2001",
            source_scope="Italy national modeled ILO labor-force rate used as a Vatican gameplay proxy.",
            method="Copy Italy's modeled 2001 ILO estimate as a neighboring labor-market proxy.",
            inputs=[
                {
                    "country_id": "ITA",
                    "field": UNEMPLOYMENT,
                    "value": _format(vat_unemployment),
                    "source": vat_provenance.get("source"),
                    "source_url": vat_provenance.get("source_url"),
                    "observation_year": SCENARIO_YEAR,
                }
            ],
            confidence="very_low",
            source_urls=[vat_provenance.get("source_url", "")],
            note=(
                "Italy's modeled ILO estimate is used only to provide a gameplay proxy. Vatican "
                "City has no comparable resident labor-force series; many workers commute across "
                "the border, so the value does not measure Vatican City unemployment."
            ),
        )
    )

    core_by_id = economics
    for row in rows:
        if row["available"] != "true":
            continue
        if (
            core_by_id[row["id"]].get(f"{row['target_field']}_available", "").lower()
            == "true"
        ):
            raise ValueError(
                f"Proxy would overlap an observed core value: {row['id']}:{row['target_field']}"
            )
    rows.sort(key=lambda row: (row["id"], row["target_field"]))
    return rows


def render_tsv(rows: list[dict[str, str]]) -> str:
    """Render one unique country row for the automatic country-table join."""
    by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        country_id = row["id"]
        target_field = row["target_field"]
        if target_field not in PROXY_FIELDS:
            raise ValueError(f"Unsupported macro proxy field: {target_field}")
        country_row = by_id.setdefault(country_id, _empty_runtime_row(country_id))
        prefix = f"{target_field}_gameplay_proxy"
        provenance_column = f"{prefix}_provenance_json"
        if country_row[provenance_column] != "{}":
            raise ValueError(f"Duplicate macro proxy row: {country_id}:{target_field}")

        source_urls = [
            url.strip() for url in row["source_urls"].split(" | ") if url.strip()
        ]
        provenance = {
            "scenario_year": row["scenario_year"],
            "observation_year": row["observation_year"],
            "source_year": row["source_year"],
            "source_scope": row["source_scope"],
            "estimate_type": row["estimate_type"],
            "method": row["method"],
            "confidence": row["confidence"],
            "unit": row["unit"],
            "source_inputs": json.loads(row["source_inputs_json"] or "[]"),
            "source_urls": source_urls,
            "source_note": row["source_note"],
        }
        country_row[f"{prefix}_value"] = row["value"]
        country_row[f"{prefix}_available"] = row["available"]
        country_row[provenance_column] = json.dumps(
            provenance, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    return render_rows(
        [by_id[country_id] for country_id in sorted(by_id)],
        RUNTIME_COLUMNS,
    )


def _empty_runtime_row(country_id: str) -> dict[str, str]:
    row = {"id": country_id}
    for field in PROXY_FIELDS:
        prefix = f"{field}_gameplay_proxy"
        row[f"{prefix}_value"] = ""
        row[f"{prefix}_available"] = "false"
        row[f"{prefix}_provenance_json"] = "{}"
    return row


def render_ledger_tsv(rows: list[dict[str, str]]) -> str:
    """Render the detailed long-form source ledger outside auto-merged country data."""
    return render_rows(rows, OUTPUT_COLUMNS)


def render_rows(rows: list[dict[str, str]], fieldnames: tuple[str, ...]) -> str:
    from io import StringIO

    buffer = StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=fieldnames,
        delimiter="\t",
        lineterminator="\n",
        extrasaction="raise",
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Verify output without rewriting it"
    )
    args = parser.parse_args()
    rows = generate_rows()
    rendered = render_tsv(rows)
    rendered_ledger = render_ledger_tsv(rows)
    if args.check:
        for path, expected in (
            (OUTPUT_PATH, rendered),
            (LEDGER_OUTPUT_PATH, rendered_ledger),
        ):
            current = path.read_text(encoding="utf-8")
            if current != expected:
                raise SystemExit(f"Generated proxy file is stale: {path}")
            print(f"Verified {path}")
        return 0
    OUTPUT_PATH.write_text(rendered, encoding="utf-8", newline="")
    LEDGER_OUTPUT_PATH.write_text(rendered_ledger, encoding="utf-8", newline="")
    runtime_rows = len({row["id"] for row in rows})
    print(f"Wrote {runtime_rows} country rows to {OUTPUT_PATH}")
    print(f"Wrote {len(rows)} proxy records to {LEDGER_OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
