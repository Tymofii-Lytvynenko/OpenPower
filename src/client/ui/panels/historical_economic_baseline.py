"""Format source-backed country baselines for read-only economic tooltips."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping

HISTORICAL_ECONOMIC_BASELINES = {
    "historical_gdp_current_usd_2001": {
        "label": "GDP (current US$)",
        "indicator": "NY.GDP.MKTP.CD",
    },
    "historical_gdp_per_capita_current_usd_2001": {
        "label": "GDP per capita (current US$)",
        "indicator": "NY.GDP.PCAP.CD",
    },
    "historical_inflation_cpi_pct_2001": {
        "label": "Inflation, consumer prices (annual %)",
        "indicator": "FP.CPI.TOTL.ZG",
    },
    "historical_unemployment_modeled_ilo_pct_2001": {
        "label": "Unemployment, modeled ILO estimate (% of labor force)",
        "indicator": "SL.UEM.TOTL.ZS",
    },
}

_COUNTRY_SCENARIO_KEYS = {
    "historical_gdp_current_usd_2001": "gdp",
    "historical_gdp_per_capita_current_usd_2001": "gdp_per_capita",
    "historical_inflation_cpi_pct_2001": "inflation",
    "historical_unemployment_modeled_ilo_pct_2001": "unemployment",
}

ALTERNATE_ECONOMIC_OBSERVATIONS = {
    "historical_gdp_current_usd_2001": (
        {
            "field": "historical_gdp_snaama_current_usd_2001",
            "label": "UNdata SNAAMA GDP estimate (separate series)",
            "provenance_column": "historical_economic_supplement_provenance_json",
            "currency": True,
        },
    ),
    "historical_gdp_per_capita_current_usd_2001": (
        {
            "field": "historical_gdp_per_capita_snaama_current_usd_2001",
            "label": "UNdata SNAAMA GDP per capita estimate (separate series)",
            "provenance_column": "historical_economic_supplement_provenance_json",
            "currency": True,
        },
    ),
    "historical_inflation_cpi_pct_2001": (
        {
            "field": "historical_cpi_inflation_source_supplement_pct_2001",
            "label": "Reported CPI inflation (separate source series)",
            "provenance_column": "historical_economic_supplement_provenance_json",
        },
        {
            "field": "historical_cpi_staff_estimate_pct_2001",
            "label": "IMF staff annual-average CPI estimate (separate series)",
            "provenance_column": "historical_economic_reported_observation_provenance_json",
        },
        {
            "field": "historical_cpi_kabul_yoy_pct_fy2001_02",
            "label": "IMF Kabul CPI estimate (FY2001/02, separate series)",
            "provenance_column": "historical_economic_reported_observation_provenance_json",
        },
    ),
    "historical_unemployment_modeled_ilo_pct_2001": (
        {
            "field": "historical_unemployment_imf_weo_pct_2001",
            "label": "IMF WEO unemployment rate (separate alternative series)",
            "provenance_column": "historical_economic_provenance_json",
        },
        {
            "field": "historical_unemployment_reported_supplement_pct_2001",
            "label": "Reported unemployment rate (separate source series)",
            "provenance_column": "historical_economic_supplement_provenance_json",
        },
        {
            "field": "historical_unemployment_reported_endyear_pct_2001",
            "label": "Reported end-of-year unemployment rate",
            "provenance_column": "historical_economic_reported_observation_provenance_json",
        },
        {
            "field": "historical_unemployment_census_pct_1999",
            "label": "Reported unemployment rate (1999 census)",
            "provenance_column": "historical_economic_reported_observation_provenance_json",
        },
        {
            "field": "historical_unemployment_census_pct_2000",
            "label": "Reported unemployment rate (2000 census)",
            "provenance_column": "historical_economic_reported_observation_provenance_json",
        },
        {
            "field": "historical_unemployment_census_pct_2002",
            "label": "Reported unemployment rate (2002 census)",
            "provenance_column": "historical_economic_reported_observation_provenance_json",
        },
    ),
}


def historical_economic_tooltip(
    country_row,
    field: str,
    current_value: str,
    current_description: str,
    *,
    value_formatter=None,
) -> str:
    """Keep a live value distinct from its exact-year, read-only source baseline."""
    definition = HISTORICAL_ECONOMIC_BASELINES[field]
    lines = [
        f"Current simulated {current_description}: {current_value}.",
        "This displayed value remains OpenPower simulation state.",
    ]
    available = _row_value(country_row, f"{field}_available")
    manual_value = _read_json_record(
        country_row, "countryinfo_economic_values_2001_json"
    ).get(_COUNTRY_SCENARIO_KEYS[field])
    if isinstance(manual_value, bool) or not isinstance(manual_value, (int, float)):
        manual_value = None
    elif not math.isfinite(manual_value):
        manual_value = None
    if not _as_bool(available):
        if manual_value is None:
            lines.append(
                f"2001 historical baseline: unavailable for {definition['indicator']} "
                "(no exact-year observation; no neighboring-year value was substituted)."
            )
        else:
            baseline = value_formatter(manual_value) if value_formatter else f"{manual_value:,.4g}"
            lines.append(f"2001 baseline ({definition['label']}): {baseline}.")
    else:
        raw_value = _row_value(country_row, field)
        try:
            numeric_value = float(raw_value)
        except (TypeError, ValueError, OverflowError):
            numeric_value = math.nan
        if not math.isfinite(numeric_value):
            lines.append(
                f"2001 historical baseline: unavailable for {definition['indicator']} "
                "because its stored value is invalid."
            )
        else:
            provenance = _read_provenance(country_row, field)
            if value_formatter is None:
                baseline = f"{numeric_value:,.4g}"
            else:
                baseline = value_formatter(numeric_value)
            observation_year = provenance.get("observation_year") or "unknown"
            scenario_year = provenance.get("scenario_year") or "2001"
            unit = provenance.get("unit") or ""
            unit_suffix = (
                f" ({unit})"
                if value_formatter and unit
                else (f" {unit}" if unit else "")
            )
            lines.append(
                f"2001 historical baseline ({definition['label']}): {baseline}{unit_suffix}. "
                f"Source observation year: {observation_year}; scenario year: {scenario_year}."
            )
            lines.append(
                f"Source: {provenance.get('source') or 'World Bank, World Development Indicators'}; "
                f"indicator {provenance.get('indicator') or definition['indicator']}."
            )
            source_note = str(provenance.get("source_note") or "").strip()
            source_url = str(provenance.get("source_url") or "").strip()
            if source_note:
                lines.append(f"Source note: {source_note}")
            if source_url:
                lines.append(f"Source URL: {source_url}")
            else:
                lines.append("Source URL: unavailable in the stored provenance record.")

    _append_alternate_economic_observations(lines, country_row, field, value_formatter)
    if _as_bool(available) or manual_value is None:
        _append_gameplay_proxy(lines, country_row, field, value_formatter, definition)
    return "\n".join(lines)


def _append_alternate_economic_observations(
    lines: list[str], country_row, field: str, value_formatter
) -> None:
    for definition in ALTERNATE_ECONOMIC_OBSERVATIONS.get(field, ()):
        source_field = definition["field"]
        if not _as_bool(_row_value(country_row, f"{source_field}_available")):
            continue
        try:
            value = float(_row_value(country_row, source_field))
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(value):
            continue

        provenance = _read_provenance(
            country_row,
            source_field,
            definition["provenance_column"],
        )
        if definition.get("currency") and value_formatter is not None:
            formatted_value = value_formatter(value)
            unit_suffix = ""
        else:
            formatted_value = f"{value:,.4g}"
            unit = str(provenance.get("unit") or "").strip()
            unit_suffix = f" {unit}" if unit else ""
        period = str(
            provenance.get("observation_period")
            or provenance.get("observation_year")
            or "unknown period"
        )
        observation_year = provenance.get("observation_year") or "unknown"
        scenario_year = provenance.get("scenario_year") or "2001"
        lines.append(
            f"Alternative historical observation ({definition['label']}): "
            f"{formatted_value}{unit_suffix}. Observation period: {period}; "
            f"source observation year: {observation_year}; scenario year: {scenario_year}."
        )
        source = str(provenance.get("source") or "Source unavailable").strip()
        series_id = str(provenance.get("series_id") or "").strip()
        source_release = str(provenance.get("source_release") or "").strip()
        source_description = source
        if series_id:
            source_description += f"; series: {series_id}"
        if source_release:
            source_description += f"; release: {source_release}"
        lines.append(f"Alternative source: {source_description}.")
        source_note = str(provenance.get("source_note") or "").strip()
        source_url = str(provenance.get("source_url") or "").strip()
        if source_note:
            lines.append(f"Alternative source scope and note: {source_note}")
        if source_url:
            lines.append(f"Alternative source URL: {source_url}")


def _append_gameplay_proxy(
    lines: list[str], country_row, field: str, value_formatter, definition: dict
) -> None:
    prefix = f"{field}_gameplay_proxy"
    provenance = _read_json_record(country_row, f"{prefix}_provenance_json")
    if not provenance:
        return

    if not _as_bool(_row_value(country_row, f"{prefix}_available")):
        if provenance.get("estimate_type") == "not_applicable":
            note = str(provenance.get("source_note") or "").strip()
            lines.append(
                f"2001 gameplay proxy ({definition['label']}): not applicable."
            )
            if note:
                lines.append(f"Proxy applicability note: {note}")
        return

    try:
        value = float(_row_value(country_row, f"{prefix}_value"))
    except (TypeError, ValueError, OverflowError):
        return
    if not math.isfinite(value):
        return

    if value_formatter is None:
        formatted_value = f"{value:,.4g}"
        unit = str(provenance.get("unit") or "").strip()
        unit_suffix = f" {unit}" if unit else ""
    else:
        formatted_value = value_formatter(value)
        unit_suffix = ""

    scenario_year = provenance.get("scenario_year") or "2001"
    source_year = provenance.get("source_year") or "unspecified"
    lines.append(
        f"Gameplay proxy (not a measured national series, {definition['label']}): "
        f"{formatted_value}{unit_suffix}. Target observation year: unavailable; "
        f"scenario year: {scenario_year}."
    )
    lines.append(
        f"Proxy metadata: estimate type {provenance.get('estimate_type') or 'unspecified'}; "
        f"quality {provenance.get('confidence') or 'unspecified'}; "
        f"source year {source_year}; method: {provenance.get('method') or 'unspecified'}; "
        f"source scope: {provenance.get('source_scope') or 'unspecified'}."
    )
    source_note = str(provenance.get("source_note") or "").strip()
    if source_note:
        lines.append(f"Proxy note: {source_note}")
    source_urls = provenance.get("source_urls") or []
    if isinstance(source_urls, str):
        source_urls = [source_urls]
    if source_urls:
        lines.append(f"Proxy source URLs: {'; '.join(str(url) for url in source_urls)}")
    else:
        lines.append("Proxy source URLs: unavailable in the stored provenance record.")


def _row_value(row, key: str):
    if row is None:
        return None
    if isinstance(row, Mapping):
        return row.get(key)
    columns = getattr(row, "columns", ())
    if key not in columns:
        return None
    try:
        return row[key][0]
    except (IndexError, TypeError, KeyError):
        return None


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def _read_provenance(
    row, field: str, column: str = "historical_economic_provenance_json"
) -> dict:
    raw = _row_value(row, column)
    if isinstance(raw, Mapping):
        value = raw.get(field)
        return dict(value) if isinstance(value, Mapping) else {}
    try:
        parsed = json.loads(str(raw or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    value = parsed.get(field) if isinstance(parsed, dict) else None
    return value if isinstance(value, dict) else {}


def _read_json_record(row, column: str) -> dict:
    raw = _row_value(row, column)
    if isinstance(raw, Mapping):
        return dict(raw)
    try:
        parsed = json.loads(str(raw or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
