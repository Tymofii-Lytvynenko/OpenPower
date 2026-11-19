"""Build the 150-entry interface data inventory from the source audit registers."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "docs" / "ui" / "reference"
INVENTORY_PATH = AUDIT_DIR / "interface_data_inventory_150.csv"
REPORT_PATH = AUDIT_DIR / "2001-interface-data-completion-report.md"
REGIONAL_POPULATION_PROVENANCE = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "regional_population_provenance.tsv"
RASTER_SOURCE_PROVENANCE = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "worldpop_regional_raster_sources.tsv"
PROTECTED_AREA_DATA = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "unsd_terrestrial_protected_areas_2010.tsv"
NATIONAL_PARK_EVIDENCE_DATA = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "national_park_terrestrial_2001_evidence.tsv"
PALESTINIAN_NATURAL_RESERVES_DATA = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "palestinian_natural_reserves_2001_candidate.tsv"
PALESTINIAN_NATURAL_RESERVES_RUNTIME_DATA = ROOT / "modules" / "base" / "data" / "countries" / "countries_palestinian_reserves_context_2001.tsv"
REGIONAL_BIOME_DATA = ROOT / "modules" / "base" / "data" / "regions" / "regions_biomes.tsv"
REGIONAL_BIOME_MANIFEST = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "resolve_ecoregions_2017_manifest.json"
FAOSTAT_LAND_USE_MANIFEST = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "faostat_land_use_2026.json"
OTHER_LAND_SUPPLEMENT_DATA = ROOT / "modules" / "base" / "data" / "countries" / "countries_other_land_supplement_2001.tsv"
COUNTRY_HISTORICAL_DATA = ROOT / "modules" / "base" / "data" / "countries" / "countries_historical.tsv"
UNIT_RESEARCH_BASELINE_DATA = ROOT / "modules" / "base" / "data" / "countries" / "countries_unit_research_2001.tsv"
LANGUAGE_FACTBOOK_DATA = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "country_languages_factbook_2001.tsv"
LANGUAGE_SUPPLEMENTAL_CONTEXT_DATA = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "country_languages_supplemental_context_2001.tsv"
PARTY_ROSTER_FACTBOOK_DATA = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "country_party_roster_factbook_2001.tsv"
PARTY_ROSTER_COVERAGE_DATA = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "country_party_roster_coverage_2001.tsv"
PARTY_ROSTER_SUPPLEMENTAL_DATA = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "country_party_roster_supplemental_2001.tsv"
MILITARY_PERSONNEL_WDI_DATA = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "military_personnel_wdi_2001.tsv"
MILITARY_PERSONNEL_SUPPLEMENTAL_DATA = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "military_personnel_supplemental_2001.tsv"
MILITARY_PERSONNEL_GAMEPLAY_ESTIMATES_DATA = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "military_personnel_gameplay_estimates_2001.tsv"
MILITARY_EQUIPMENT_SUPPLEMENT_DATA = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "military_equipment_inventory_supplement_2001.tsv"
COUNTRY_ECONOMIC_HISTORICAL_DATA = ROOT / "modules" / "base" / "data" / "countries" / "countries_economic_historical.tsv"
DEVELOPMENT_SUPPLEMENT_DATA = ROOT / "modules" / "base" / "data" / "countries" / "countries_development_supplement_2001.tsv"
INTERNATIONAL_POVERTY_DATA = ROOT / "modules" / "base" / "data" / "countries" / "countries_poverty_international_2001.tsv"
INTERNATIONAL_POVERTY_SOURCE = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "pip_2021_ppp_3usd_2001.tsv"
POVERTY_SCENARIO_ESTIMATES_DATA = ROOT / "modules" / "base" / "data" / "countries" / "countries_poverty_scenario_estimates_2001.tsv"
NATIONAL_POVERTY_SUPPLEMENT_DATA = ROOT / "modules" / "base" / "data" / "countries" / "countries_poverty_national_supplement_2001.tsv"
ELECTION_RESULTS_DATA = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "country_election_results_2001.tsv"
ECONOMIC_SUPPLEMENT_SOURCE = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "economic_supplement_2001.tsv"
ECONOMIC_REPORTED_SOURCE = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "economic_reported_observations_2001.tsv"
JOURNEY_SUITE = ROOT / "artifacts" / "ui" / "reference" / "goal-2001-journeys-final-20261115" / "suite.json"
SURFACE_MATRIX_SUITE = ROOT / "artifacts" / "ui" / "reference" / "goal-2001-surface-matrix-final-20261115" / "suite.json"
ECONOMIC_INDICATORS_SOURCE = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "economic_indicators_2001.tsv"
ECONOMIC_GAMEPLAY_PROXY_LEDGER = (
    ROOT
    / "modules"
    / "base"
    / "data"
    / "sources"
    / "2001"
    / "economic_gameplay_proxy_ledger_2001.tsv"
)
ECONOMIC_GAMEPLAY_PROXY_RUNTIME = (
    ROOT
    / "modules"
    / "base"
    / "data"
    / "countries"
    / "countries_economic_gameplay_proxies_2001.tsv"
)
WORLD_CONFLICTS_TREATIES_SOURCE = ROOT / "modules" / "base" / "data" / "sources" / "2001" / "world_conflicts_treaties_2001.tsv"
COUNTRIES_TREATY_DATA = ROOT / "modules" / "base" / "data" / "world" / "countries_treaties.toml"
COUNTRIES_WAR_DATA = ROOT / "modules" / "base" / "data" / "world" / "countries_wars.toml"

DISPLAY_STATUS_ORDER = (
    "verified_openpower",
    "partial",
    "verified_unavailable",
    "assumption/unknown",
    "verified_cpp",
)
INTERACTION_STATUS_ORDER = (
    "verified_openpower",
    "partial",
    "verified_unavailable",
    "verified_cpp",
)


def read_csv(path: Path, delimiter: str = ",") -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        return list(reader.fieldnames or ()), list(reader)


def read_suite_evidence(path: Path, result_key: str) -> dict[str, object]:
    if not path.exists():
        return {"total": 0, "passed": 0, "failed": 0, "surfaces": 0, "viewports": 0}
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data.get(result_key, [])
    surface_ids = {row.get("surface", "") for row in results} - {""}
    viewport_sizes = {
        (row.get("width"), row.get("height"))
        for row in results
        if row.get("width") is not None and row.get("height") is not None
    }
    configured_viewport = data.get("viewport", {})
    if not viewport_sizes and configured_viewport.get("width") and configured_viewport.get("height"):
        viewport_sizes.add((configured_viewport["width"], configured_viewport["height"]))
    return {
        "total": len(results),
        "passed": sum(bool(row.get("passed")) for row in results),
        "failed": sum(not bool(row.get("passed")) for row in results),
        "surfaces": len(surface_ids),
        "viewports": len(viewport_sizes),
    }


def count_toml_entries(path: Path, table_name: str) -> int:
    marker = f"[[{table_name}]]"
    return sum(line.strip() == marker for line in path.read_text(encoding="utf-8").splitlines())


def historical_metric_source_counts(
    rows: list[dict[str, str]], field: str
) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        provenance = json.loads(row.get("historical_metric_provenance_json", "{}") or "{}")
        source = provenance.get(field, {}).get("source")
        if source:
            counts[source] += 1
    return counts


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def status_counts(rows: list[dict[str, str]], status_field: str) -> str:
    counts = Counter(row.get(status_field, "") for row in rows)
    return "; ".join(
        f"{status}={counts[status]}"
        for status in dict.fromkeys(DISPLAY_STATUS_ORDER + INTERACTION_STATUS_ORDER)
        if counts.get(status)
    ) or "no direct contract"


def summarize_unavailable_fields(rows: list[dict[str, str]]) -> str:
    details: list[str] = []
    for row in rows:
        status = row.get("openpower_binding_status", "")
        path = row.get("component_path", "")
        if status == "verified_unavailable":
            detail = row.get("openpower_state_binding", "") or row.get("fallback", "")
            details.append(f"{path}: {detail}")
    return "; ".join(dict.fromkeys(details)) or "none identified in the display-data contract"


def summarize_unresolved_fields(rows: list[dict[str, str]]) -> str:
    details: list[str] = []
    for row in rows:
        if row.get("openpower_binding_status") != "assumption/unknown":
            continue
        path = row.get("component_path", "")
        displayed = row.get("what_is_displayed", "")
        binding = row.get("openpower_state_binding", "")
        details.append(f"{path}: {displayed} OpenPower binding: {binding}.")
    return "; ".join(dict.fromkeys(details)) or "none identified in the display-data contract"


def summarize_unavailable_interactions(rows: list[dict[str, str]]) -> str:
    details: list[str] = []
    for row in rows:
        if row.get("status") != "verified_unavailable":
            continue
        path = row.get("component_path", "")
        effect = row.get("openpower_effect", "") or row.get("action_required", "")
        details.append(f"{path}: {effect}")
    return "; ".join(dict.fromkeys(details)) or "none identified in the interaction contract"


def group_by(rows: list[dict[str, str]], key: str) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row.get(key, "")].append(row)
    return grouped


def enrich_inventory() -> tuple[list[dict[str, str]], Counter[str], Counter[str]]:
    inventory_fields, inventory = read_csv(INVENTORY_PATH)
    _, display_contracts = read_csv(AUDIT_DIR / "data_contracts.csv")
    _, interactions = read_csv(AUDIT_DIR / "interaction_contracts.csv")
    display_by_window = group_by(display_contracts, "window_id")
    interaction_by_window = group_by(interactions, "window_id")
    inventory_kinds = Counter(entry.get("inventory_kind", "") for entry in inventory)
    expected_kinds = Counter({
        "REFERENCE GML window": 92,
        "Native OpenPower panel": 10,
        "UI component or dialog": 39,
        "Top-level client view": 9,
    })
    if len(inventory) != 150 or inventory_kinds != expected_kinds:
        raise ValueError(f"Expected the reviewed 150-entry inventory, found {len(inventory)}: {inventory_kinds}")

    extra_fields = [
        "display_contract_status_counts",
        "verified_unavailable_data_fields",
        "unresolved_data_or_semantics",
        "partial_display_contract_count",
        "interaction_contract_count",
        "interaction_contract_status_counts",
        "unavailable_or_source_hidden_interactions",
    ]
    fields = inventory_fields + [field for field in extra_fields if field not in inventory_fields]

    for entry in inventory:
        is_source_window = entry.get("inventory_kind") == "REFERENCE GML window"
        window_id = entry.get("interface_or_component", "") if is_source_window else ""
        displays = display_by_window.get(window_id, [])
        inputs = interaction_by_window.get(window_id, [])
        if is_source_window:
            display_status = status_counts(displays, "status")
            interaction_status = status_counts(inputs, "status")
            unavailable = summarize_unavailable_fields(displays)
            unresolved = summarize_unresolved_fields(displays)
            partial_count = str(sum(row.get("status") == "partial" for row in displays))
            unavailable_inputs = summarize_unavailable_interactions(inputs)
            entry["specific_missing_data_or_limit"] = (
                f"Unavailable fields: {unavailable}. Unresolved fields/meaning: {unresolved}. "
                f"Partial display contracts: {partial_count}; see data_contracts.csv filtered by window_id."
            )
        else:
            display_status = "parent-owned or no one-to-one source contract"
            interaction_status = "parent-owned or no one-to-one source contract"
            unavailable = "no direct source-window field contract"
            unresolved = entry.get("specific_missing_data_or_limit", "")
            partial_count = "0"
            unavailable_inputs = (
                entry.get("evidence_or_notes", "")
                if any(term in entry.get("evidence_or_notes", "").lower() for term in ("unavailable", "incomplete", "no authoritative"))
                else "no direct source-window interaction contract"
            )

        entry.update({
            "display_contract_status_counts": display_status,
            "verified_unavailable_data_fields": unavailable,
            "unresolved_data_or_semantics": unresolved,
            "partial_display_contract_count": partial_count,
            "interaction_contract_count": str(len(inputs)) if is_source_window else "0 direct; parent-owned",
            "interaction_contract_status_counts": interaction_status,
            "unavailable_or_source_hidden_interactions": unavailable_inputs,
        })

    write_csv(INVENTORY_PATH, fields, inventory)
    return inventory, Counter(row["status"] for row in display_contracts), Counter(row["status"] for row in interactions)


def write_report(
    inventory: list[dict[str, str]],
    display_statuses: Counter[str],
    interaction_statuses: Counter[str],
) -> None:
    counts = Counter(row["inventory_kind"] for row in inventory)
    _, component_rows = read_csv(AUDIT_DIR / "component_tree.csv")
    _, display_rows = read_csv(AUDIT_DIR / "data_contracts.csv")
    _, interaction_rows = read_csv(AUDIT_DIR / "interaction_contracts.csv")
    _, gap_rows = read_csv(AUDIT_DIR / "gap_table.csv")
    _, regional_population = read_csv(REGIONAL_POPULATION_PROVENANCE, delimiter="\t")
    _, raster_sources = read_csv(RASTER_SOURCE_PROVENANCE, delimiter="\t")
    _, protected_area_records = read_csv(PROTECTED_AREA_DATA, delimiter="\t")
    _, national_park_evidence = read_csv(NATIONAL_PARK_EVIDENCE_DATA, delimiter="\t")
    _, palestinian_natural_reserve_candidates = read_csv(
        PALESTINIAN_NATURAL_RESERVES_DATA, delimiter="\t"
    )
    _, palestinian_natural_reserve_runtime_rows = read_csv(
        PALESTINIAN_NATURAL_RESERVES_RUNTIME_DATA, delimiter="\t"
    )
    _, other_land_supplement_rows = read_csv(OTHER_LAND_SUPPLEMENT_DATA, delimiter="\t")
    _, regional_biomes = read_csv(REGIONAL_BIOME_DATA, delimiter="\t")
    _, historical_countries = read_csv(COUNTRY_HISTORICAL_DATA, delimiter="\t")
    historical_coverage = {
        field: sum(
            str(row.get(f"{field}_available", "")).strip().lower() == "true"
            for row in historical_countries
        )
        for field in (
            "birth_rate", "death_rate", "fertility_rate", "life_expectancy",
            "arable_land_pct", "forest_area_pct", "reference_land_area_km2",
            "reference_total_area_km2", "reference_water_area_km2",
        )
    }
    historical_missing_ids = {
        field: [
            row.get("id", "") for row in historical_countries
            if str(row.get(f"{field}_available", "")).strip().lower() != "true"
        ]
        for field in historical_coverage
    }
    water_area_comparisons: list[tuple[str, float]] = []
    for row in historical_countries:
        provenance = json.loads(row.get("historical_metric_provenance_json", "{}") or "{}")
        land_source = provenance.get("reference_land_area_km2", {}).get("source")
        surface_source = provenance.get("reference_total_area_km2", {}).get("source")
        water_source = provenance.get("reference_water_area_km2", {}).get("source")
        if (
            land_source != "AG.LND.TOTL.K2"
            or surface_source != "AG.SRF.TOTL.K2"
            or water_source != "CIA Factbook 2001"
        ):
            continue
        land = row.get("reference_land_area_km2", "")
        surface = row.get("reference_total_area_km2", "")
        water = row.get("reference_water_area_km2", "")
        if land and surface and water:
            wdi_derived_water = float(surface) - float(land)
            water_area_comparisons.append((row.get("id", ""), float(water) - wdi_derived_water))
    water_area_conflict_ids = sorted(
        country_id for country_id, delta in water_area_comparisons if abs(delta) > 100
    )
    water_area_large_conflict_count = sum(
        abs(delta) > 1000 for _, delta in water_area_comparisons
    )
    land_metric_adjacent_year_count = sum(
        1
        for row in historical_countries
        for field in ("arable_land_pct", "forest_area_pct", "reference_land_area_km2", "reference_water_area_km2")
        if (
            (record := json.loads(row.get("historical_metric_provenance_json", "{}") or "{}").get(field))
            and record.get("observation_year") == 2000
        )
    )
    _, unit_research_rows = read_csv(UNIT_RESEARCH_BASELINE_DATA, delimiter="\t")
    _, language_factbook_rows = read_csv(LANGUAGE_FACTBOOK_DATA, delimiter="\t")
    _, language_supplemental_context_rows = read_csv(LANGUAGE_SUPPLEMENTAL_CONTEXT_DATA, delimiter="\t")
    _, party_roster_rows = read_csv(PARTY_ROSTER_FACTBOOK_DATA, delimiter="\t")
    _, party_roster_coverage = read_csv(PARTY_ROSTER_COVERAGE_DATA, delimiter="\t")
    _, party_roster_supplemental_rows = read_csv(PARTY_ROSTER_SUPPLEMENTAL_DATA, delimiter="\t")
    _, military_personnel_wdi_rows = read_csv(MILITARY_PERSONNEL_WDI_DATA, delimiter="\t")
    _, military_personnel_supplemental_rows = read_csv(MILITARY_PERSONNEL_SUPPLEMENTAL_DATA, delimiter="\t")
    _, military_personnel_gameplay_estimate_rows = read_csv(
        MILITARY_PERSONNEL_GAMEPLAY_ESTIMATES_DATA, delimiter="\t"
    )
    _, military_equipment_supplement_rows = read_csv(MILITARY_EQUIPMENT_SUPPLEMENT_DATA, delimiter="\t")
    _, economic_country_rows = read_csv(COUNTRY_ECONOMIC_HISTORICAL_DATA, delimiter="\t")
    _, economic_source_rows = read_csv(ECONOMIC_INDICATORS_SOURCE, delimiter="\t")
    _, economic_gameplay_proxy_ledger_rows = read_csv(
        ECONOMIC_GAMEPLAY_PROXY_LEDGER, delimiter="\t"
    )
    _, economic_gameplay_proxy_runtime_rows = read_csv(
        ECONOMIC_GAMEPLAY_PROXY_RUNTIME, delimiter="\t"
    )
    _, economic_supplement_rows = read_csv(ECONOMIC_SUPPLEMENT_SOURCE, delimiter="\t")
    _, economic_reported_rows = read_csv(ECONOMIC_REPORTED_SOURCE, delimiter="\t")
    _, development_country_rows = read_csv(DEVELOPMENT_SUPPLEMENT_DATA, delimiter="\t")
    _, international_poverty_rows = read_csv(INTERNATIONAL_POVERTY_SOURCE, delimiter="\t")
    _, international_poverty_country_rows = read_csv(INTERNATIONAL_POVERTY_DATA, delimiter="\t")
    _, poverty_scenario_estimate_rows = read_csv(POVERTY_SCENARIO_ESTIMATES_DATA, delimiter="\t")
    _, national_poverty_supplement_rows = read_csv(NATIONAL_POVERTY_SUPPLEMENT_DATA, delimiter="\t")
    _, election_result_rows = read_csv(ELECTION_RESULTS_DATA, delimiter="\t")
    _, treaty_war_source_rows = read_csv(WORLD_CONFLICTS_TREATIES_SOURCE, delimiter="\t")
    journey_evidence = read_suite_evidence(JOURNEY_SUITE, "results")
    surface_evidence = read_suite_evidence(SURFACE_MATRIX_SUITE, "runs")
    climate_source_counts = historical_metric_source_counts(historical_countries, "climate_description")
    climate_factbook_count = climate_source_counts["CIA Factbook 2001"]
    climate_total_count = sum(climate_source_counts.values())
    climate_context_count = climate_total_count - climate_factbook_count
    poverty_source_counts = historical_metric_source_counts(historical_countries, "historical_poverty_rate_pct")
    poverty_factbook_count = poverty_source_counts["CIA Factbook 2001"]
    poverty_wdi_count = poverty_source_counts["SI.POV.NAHC"]
    poverty_total_count = sum(poverty_source_counts.values())
    development_available_counts = {
        field: sum(
            str(row.get(f"{field}_available", "")).strip().lower() == "true"
            for row in development_country_rows
        )
        for field in (
            "historical_school_life_expectancy_wdi_years_2001",
            "historical_gni_per_capita_wdi_ppp_current_intl_dollars_2001",
            "historical_mean_schooling_barrolee_years_population_15plus_2000",
            "historical_mean_schooling_barrolee_years_population_25plus_2000",
        )
    }
    international_poverty_field = "historical_poverty_global_3usd_2021_ppp_pct"
    international_poverty_country_ids = {
        row.get("id", "")
        for row in international_poverty_country_rows
        if str(row.get(f"{international_poverty_field}_available", "")).strip().lower() == "true"
    } - {""}
    international_poverty_survey_ids = {
        row.get("country_id", "") for row in international_poverty_rows
    } - {""}
    poverty_scenario_estimate_count = sum(
        str(row.get("gameplay_poverty_estimate_3usd_2021_ppp_pct_available", ""))
        .strip()
        .lower()
        == "true"
        for row in poverty_scenario_estimate_rows
    )
    poverty_scenario_unavailable_count = len(poverty_scenario_estimate_rows) - poverty_scenario_estimate_count
    national_poverty_country_ids = {
        row.get("id", "")
        for row in historical_countries
        if str(row.get("historical_poverty_rate_pct_available", "")).strip().lower() == "true"
    } - {""}
    national_poverty_supplement_records = [
        row
        for row in national_poverty_supplement_rows
        if str(row.get("historical_national_poverty_supplement_available", "")).strip().lower() == "true"
    ]
    national_poverty_supplement_ids = {
        row.get("id", "") for row in national_poverty_supplement_records
    } - {""}
    national_poverty_supplement_year_summary = "; ".join(
        f"{row.get('id', '')} (reference {row.get('historical_national_poverty_supplement_reference_year', 'unreported')}; "
        f"survey/fieldwork {row.get('historical_national_poverty_supplement_survey_period', 'unreported')})"
        for row in sorted(national_poverty_supplement_records, key=lambda item: item.get("id", ""))
    ) or "none"
    national_poverty_coverage_with_supplements = len(
        national_poverty_country_ids | national_poverty_supplement_ids
    )
    national_poverty_remaining_gap_count = 199 - national_poverty_coverage_with_supplements
    election_result_country_ids = {
        row.get("country_id", "") for row in election_result_rows
    } - {""}
    election_result_event_ids = {
        row.get("event_id", "") for row in election_result_rows
    } - {""}
    international_poverty_additional_ids = international_poverty_survey_ids - national_poverty_country_ids
    reported_economic_rows = economic_supplement_rows + economic_reported_rows
    reported_economic_country_ids = {
        row.get("country_id", "") for row in reported_economic_rows
    } - {""}
    treaty_count = count_toml_entries(COUNTRIES_TREATY_DATA, "countries_treaties")
    war_count = count_toml_entries(COUNTRIES_WAR_DATA, "countries_wars")
    biome_manifest = json.loads(REGIONAL_BIOME_MANIFEST.read_text(encoding="utf-8"))
    faostat_manifest = json.loads(FAOSTAT_LAND_USE_MANIFEST.read_text(encoding="utf-8"))
    other_land_direct_ids = {
        row.get("id", "")
        for row in historical_countries
        if str(row.get("other_land_pct_available", "")).strip().lower() == "true"
    } - {""}
    if faostat_manifest.get("mapped_game_country_count") != len(other_land_direct_ids):
        raise ValueError("FAOSTAT manifest count does not match direct country observations")
    other_land_scenario_ids = {
        row.get("id", "")
        for row in other_land_supplement_rows
        if str(row.get("scenario_other_land_2001_available", "")).strip().lower()
        == "true"
    } - {""}
    other_land_cia_alternative_ids = {
        row.get("id", "")
        for row in other_land_supplement_rows
        if str(row.get("scenario_cia_land_use_other_2001_available", "")).strip().lower()
        == "true"
    } - {""}
    other_land_coverage_ids = other_land_direct_ids | other_land_scenario_ids
    other_land_missing_ids = sorted(
        {row.get("id", "") for row in historical_countries} - other_land_coverage_ids - {""}
    )
    palestinian_reserve_runtime_ids = {
        row.get("id", "")
        for row in palestinian_natural_reserve_runtime_rows
        if any(
            str(row.get(f"countryinfo_pna_west_bank_natural_reserves_{year}_area_km2_available", ""))
            .strip()
            .lower()
            == "true"
            for year in ("2000", "2001")
        )
    } - {""}
    palestinian_reserve_runtime_years = [
        year
        for year in ("2000", "2001")
        if any(
            str(row.get(f"countryinfo_pna_west_bank_natural_reserves_{year}_area_km2_available", ""))
            .strip()
            .lower()
            == "true"
            for row in palestinian_natural_reserve_runtime_rows
        )
    ]
    hdi_statuses = Counter(row.get("reference_human_dev_status", "unavailable") for row in historical_countries)
    hdi_value_count = sum(row.get("reference_human_dev_available") == "True" for row in historical_countries)
    protected_area_override_rows = [
        row
        for row in national_park_evidence
        if row.get("terrestrial_protected_area_pct_2000_override", "").strip()
    ]
    protected_area_count = len(protected_area_records) + len(protected_area_override_rows)
    national_park_value_count = sum(
        bool(row.get("national_park_land_coverage_pct", "").strip())
        for row in national_park_evidence
    )
    national_park_inferred_value_count = sum(
        bool(row.get("national_park_land_coverage_pct", "").strip())
        and row.get("value_status", "").startswith("park_only_inference_")
        for row in national_park_evidence
    )
    palestinian_natural_reserve_summary = "; ".join(
        f"{row.get('observation_year', 'unknown')}: "
        f"{'about ' if row.get('precision') == 'approximate' else ''}"
        f"{row.get('value', 'unknown')} km²"
        for row in sorted(
            palestinian_natural_reserve_candidates,
            key=lambda row: row.get("observation_year", ""),
        )
    ) or "no dated candidate"
    language_statuses = Counter(row.get("source_status", "") for row in language_factbook_rows)
    language_context_country_ids = {
        row.get("country_id", "")
        for row in language_factbook_rows
        if row.get("source_status") == "reported"
    } | {row.get("country_id", "") for row in language_supplemental_context_rows}
    language_context_country_ids.discard("")
    language_context_coverage_count = len(language_context_country_ids)
    language_unavailable_context_count = max(0, 199 - language_context_coverage_count)
    party_roster_statuses = Counter(row.get("status", "") for row in party_roster_coverage)
    party_roster_country_count = party_roster_statuses["reported"]
    party_roster_supplemental_country_ids = {
        row.get("country_id", "") for row in party_roster_supplemental_rows
    } - {""}
    party_roster_factbook_country_ids = {
        row.get("country_id", "")
        for row in party_roster_coverage
        if row.get("status") == "reported"
    } - {""}
    party_roster_name_context_count = len(
        party_roster_factbook_country_ids | party_roster_supplemental_country_ids
    )
    party_roster_uncovered_ids = sorted(
        {
            row.get("country_id", "")
            for row in party_roster_coverage
            if row.get("status") in {"party_field_not_reported", "no_separate_country_entry"}
        }
        - party_roster_supplemental_country_ids
        - {""}
    )
    military_personnel_covered_ids = {
        row.get("iso3", "") for row in military_personnel_wdi_rows
    } | {
        row.get("country_id", "") for row in military_personnel_supplemental_rows
    }
    military_personnel_covered_ids.discard("")
    military_personnel_uncovered_count = max(0, 199 - len(military_personnel_covered_ids))
    military_personnel_uncovered_ids = sorted(
        row.get("id", "")
        for row in historical_countries
        if row.get("id", "") and row.get("id", "") not in military_personnel_covered_ids
    )
    military_personnel_supplemental_year_counts = Counter(
        row.get("observation_year", "") or "unreported"
        for row in military_personnel_supplemental_rows
    )
    military_personnel_supplemental_year_summary = ", ".join(
        f"{year}: {count}"
        for year, count in sorted(military_personnel_supplemental_year_counts.items())
    ) or "none"
    military_personnel_gameplay_estimate_ids = sorted(
        row.get("country_id", "")
        for row in military_personnel_gameplay_estimate_rows
        if row.get("country_id", "")
        and row.get("gameplay_personnel_estimate", "").strip()
    )
    economic_indicators = {
        "historical_gdp_current_usd_2001": "GDP (current US$)",
        "historical_gdp_per_capita_current_usd_2001": "GDP per capita (current US$)",
        "historical_inflation_cpi_pct_2001": "CPI inflation",
        "historical_unemployment_modeled_ilo_pct_2001": "modeled ILO unemployment",
        "historical_unemployment_imf_weo_pct_2001": "alternate IMF WEO unemployment",
    }
    economic_coverage = {
        field: sum(
            str(row.get(f"{field}_available", "")).strip().lower() == "true"
            for row in economic_country_rows
        )
        for field in economic_indicators
    }
    economic_sources_by_name = Counter(row.get("source_name", "") for row in economic_source_rows)
    economic_wdi_record_count = economic_sources_by_name["World Bank, World Development Indicators"]
    economic_imf_record_count = economic_sources_by_name["World Economic Outlook, October 2026"]
    economic_gameplay_proxy_rows = [
        row
        for row in economic_gameplay_proxy_ledger_rows
        if str(row.get("available", "")).strip().lower() == "true"
    ]
    economic_gameplay_proxy_field_counts = Counter(
        row.get("target_field", "") for row in economic_gameplay_proxy_rows
    )
    economic_gameplay_proxy_field_labels = {
        "historical_gdp_current_usd_2001": "GDP",
        "historical_gdp_per_capita_current_usd_2001": "GDP per capita",
        "historical_inflation_cpi_pct_2001": "CPI inflation",
        "historical_unemployment_modeled_ilo_pct_2001": "unemployment",
    }
    economic_gameplay_proxy_summary = "; ".join(
        f"{label}: {economic_gameplay_proxy_field_counts[field]}"
        for field, label in economic_gameplay_proxy_field_labels.items()
        if economic_gameplay_proxy_field_counts[field]
    ) or "none"
    economic_gameplay_proxy_country_count = len(
        {row.get("id", "") for row in economic_gameplay_proxy_rows} - {""}
    )
    economic_gameplay_proxy_not_applicable_count = sum(
        row.get("estimate_type") == "not_applicable"
        for row in economic_gameplay_proxy_ledger_rows
    )
    economic_gameplay_proxy_runtime_ids = [
        row.get("id", "") for row in economic_gameplay_proxy_runtime_rows
    ]
    if len(economic_gameplay_proxy_runtime_ids) != len(
        set(economic_gameplay_proxy_runtime_ids)
    ):
        raise ValueError("Macro gameplay-proxy runtime table contains duplicate country IDs")
    treaty_war_source_ids = {
        row.get("record_id", "") for row in treaty_war_source_rows
    } - {""}
    unit_research_fields = sorted(
        field for field in (unit_research_rows[0].keys() if unit_research_rows else ())
        if field.startswith("research_characteristic_") and field.endswith("_factor_2001")
    )
    regional_statuses = Counter(row.get("source_status", "") for row in regional_population)
    worldpop_region_count = regional_statuses["worldpop_2001_1km"]
    curated_region_count = sum(
        count
        for status, count in regional_statuses.items()
        if status
        not in {
            "worldpop_2001_1km",
            "retained_unverified_legacy_baseline",
            "assumed_zero_uninhabited_antarctica",
            "assumed_zero_uninhabited_territory",
        }
    )
    unverified_region_count = regional_statuses["retained_unverified_legacy_baseline"]
    assumed_zero_region_count = regional_statuses["assumed_zero_uninhabited_antarctica"]
    assumed_zero_territory_count = regional_statuses["assumed_zero_uninhabited_territory"]
    biome_methods = Counter(row.get("biome_assignment_method", "") for row in regional_biomes)
    imported_raster_count = sum(row.get("status") == "verified" for row in raster_sources)
    unpublished_raster_count = sum(row.get("status") == "not_published" for row in raster_sources)
    overlap_excluded_sources = sorted({
        row.get("source_iso3", "")
        for row in raster_sources
        if "quality limit" in row.get("note", "")
    } - {""})
    source_root_count = counts["REFERENCE GML window"]
    report = f"""# OpenPower interface data completion report (2001 scenario)

**Audit date:** {date.today().isoformat()}  
**Scope:** {len(inventory)} inventory entries: {counts['REFERENCE GML window']} REFERENCE GML window roots, {counts['Native OpenPower panel']} registered OpenPower panels without a one-to-one GML panel mapping, {counts['UI component or dialog']} standalone UI component/dialog modules, and {counts['Top-level client view']} top-level client view modules. Some source windows are implemented by component modules; both sides are listed so each source contract and application surface can be reviewed. The inventory does not claim {len(inventory)} independent runtime windows.

The complete row-by-row inventory is [interface_data_inventory_150.csv](interface_data_inventory_150.csv). For each GML window, it names verified-unavailable fields, unresolved fields, partial display-contract counts, and unavailable/source-hidden interactions. Full field contracts are in [data_contracts.csv](data_contracts.csv), interaction contracts in [interaction_contracts.csv](interaction_contracts.csv), and behavior-level gaps in [gap_table.csv](gap_table.csv). Filter those detailed registers by the exact `window_id` shown in the inventory. The audit covers {source_root_count} source roots, {len(component_rows):,} GML component records, {len(display_rows):,} display-data contracts, {len(interaction_rows):,} interaction contracts, and {len(gap_rows):,} evidence-tagged gap rows.

### Audit status totals

| Contract type | Counts by status |
|---|---|
| Display/data contracts | {"; ".join(f"{status}: {display_statuses[status]}" for status in DISPLAY_STATUS_ORDER if display_statuses[status])} |
| Interaction contracts | {"; ".join(f"{status}: {interaction_statuses[status]}" for status in INTERACTION_STATUS_ORDER if interaction_statuses[status])} |

## Historical data now present

| Data | Coverage among 199 game country records | Source and handling |
|---|---:|---|
| Birth and death rates | {historical_coverage['birth_rate']} and {historical_coverage['death_rate']} | World Bank WDI observation year 2001, with Factbook 2001 edition fallback where recorded. Display unit: per 1,000 residents. |
| Fertility and life expectancy | {historical_coverage['fertility_rate']} and {historical_coverage['life_expectancy']} | WDI year 2001; CIA Factbook fallbacks preserve the estimate year. Remaining fertility gaps: {", ".join(historical_missing_ids['fertility_rate'])}; life-expectancy gaps: {", ".join(historical_missing_ids['life_expectancy'])}. |
| Arable land and forest area | {historical_coverage['arable_land_pct']} and {historical_coverage['forest_area_pct']} | Exact-year WDI percentages plus separately attributed FAOSTAT/FAO supplements; imputed numerators, historic territory scope, and 2000 observations remain explicit in provenance. |
| Terrestrial protected areas | {protected_area_count}/199 | {len(protected_area_records)} direct UNSD observations from its 2010 table. Maldives' 2000 zero is derived from the official dated register; Nauru's zero is directly reported in April 2000. Taiwan's official yearbook reports 18.7% (691,731 ha) for 2000 while excluding maritime area, so its denominator is not identical to UNSD's total-surface measure. The UNSD measure is the share of nationally designated terrestrial protected areas as a percentage of total country surface including inland waters; it covers multiple categories, not national parks only. |
| National-park land coverage | {national_park_value_count} values among the ten formerly missing records ({national_park_value_count - national_park_inferred_value_count} source-backed; {national_park_inferred_value_count} Montenegro lower-bound inference) | Kosovo, Maldives, Nauru, São Tomé and Príncipe, and Taiwan have source-backed 2001 park-only values; Montenegro has an inferred 538.3 km² terrestrial lower bound from 2001 park and lake-area statistics, not a complete park inventory. Nauru's zero is supported by a contemporaneous April 2000 environmental report, not a bounded inference. Palestine's separate PCBS natural-reserve candidates report {palestinian_natural_reserve_summary} for 19 PNA-controlled reserves, all in the West Bank. The 2000 table has a blank Gaza row even though Wadi Gaza was separately declared a reserve, so these observations have incomplete Gaza coverage; the Country Information tooltip shows them as scoped area context only, not as a national percentage, national-park value, or exhaustive all-authority protected-area total. South Sudan's 2004 plan cannot be backcast to a 2001 territorial denominator. Details are in the [Palestinian natural-reserve candidate ledger](../../../modules/base/data/sources/2001/palestinian_natural_reserves_2001_candidate.tsv). The park-only measure is stored separately and shown in the Country Information slot only where the broader protected-area value is unavailable. It is not a full-country park inventory. |
| Land, total surface, and inland water area | {historical_coverage['reference_land_area_km2']}, {historical_coverage['reference_total_area_km2']}, and {historical_coverage['reference_water_area_km2']} | WDI 2001 and dated supplements; direct Factbook water-area observations remain separate from WDI land/surface values. In {len(water_area_comparisons)} matched source trios, {len(water_area_conflict_ids)} differ by more than 100 km² and {water_area_large_conflict_count} by more than 1,000 km². Delta is CIA water minus (WDI surface − WDI land); this does not establish equivalent definitions, and the UI discloses conflicts rather than reconciling them. See the [country-level CIA/WDI conflict ledger](../../../modules/base/data/sources/2001/area_source_conflicts_2001.tsv). Missing water values are derived only when both total and land area exist. |
| National climate description | {climate_factbook_count}/199 CIA Factbook descriptions plus {climate_context_count} sourced territory-context records | The Factbook text is national-level climate context, not a weather observation. Supplemental entries are explicitly scoped proxies for territories without separate 2001 country entries; no national climate is spread across regional biomes. |
| National HDI | {hdi_value_count}/199 | {hdi_statuses['official_undp_hdr2025']} UNDP HDR 2025 values; {hdi_statuses['official_legacy_method']} published UNDP HDR 2003 values using its older method; {hdi_statuses['calculated_estimate']} formula/model estimates; {hdi_statuses['regional_estimate_proxy'] + hdi_statuses['national_report_proxy'] + hdi_statuses['territory_proxy']} regional, national-report, or territory proxies. {hdi_statuses['not_applicable'] + hdi_statuses['not_reported']} records have no comparable HDI and use a neutral simulation fallback that is not shown as an HDI. |
| Unit Research technology factors | {len(unit_research_rows)}/199 countries × {len(unit_research_fields)} characteristics | Low-confidence estimates reproduce OpenPower's starting capability-scaling formula using 2001 HDI inputs and its research-budget scenario setting. They are not measured military research data or weapon specifications. |
| Military personnel totals | {len(military_personnel_wdi_rows)} exact WDI values plus {len(military_personnel_supplemental_rows)} source-backed supplemental records; {military_personnel_uncovered_count} roster entries still lack row-level sources; {len(military_personnel_gameplay_estimate_ids)} separate gameplay estimates | The WDI 2001 series matches its published ISO3 records. Supplemental ledger rows preserve observation year ({military_personnel_supplemental_year_summary}), source scope, method, evidence type, and confidence; nearest-year estimates are not labeled as exact 2001 values. Separate low/very-low-confidence gameplay estimates cover {', '.join(military_personnel_gameplay_estimate_ids)}; each is explicitly non-historical and excluded from factual `military_count`. ATA is not applicable to a sovereign military roster, while SSD remains unavailable for a separate 2001 national-force scope. These estimates do not close the factual gaps. The [gap audit](../../../modules/base/data/sources/2001/military_personnel_gap_audit_2001.md) reviews all 11 unresolved IDs and explains why incompatible caps, faction counts, or partial rosters were not imported. |
| Military equipment by role | 199 scenario inventories; {len(military_equipment_supplement_rows)} additional source-backed role counts | Gulf/Iran/Iraq profiles use selected contemporary IISS-derived table anchors; supplements verify Russia's 17 operational SSBNs, China's 0 carriers, India's 1 in-service carrier, U.S. Navy inventory of 12 carriers and 18 SSBNs, and France's 1 in-service carrier with 60% reported availability. Most remaining equipment values use a deterministic scenario model and are not a complete 2001 census. |
| Historical macroeconomic indicators | {economic_coverage['historical_gdp_current_usd_2001']}/199 GDP; {economic_coverage['historical_gdp_per_capita_current_usd_2001']}/199 GDP per capita; {economic_coverage['historical_inflation_cpi_pct_2001']}/199 CPI inflation; {economic_coverage['historical_unemployment_modeled_ilo_pct_2001']}/199 modeled ILO unemployment; {economic_coverage['historical_unemployment_imf_weo_pct_2001']}/199 alternate IMF WEO unemployment; {len(economic_gameplay_proxy_rows)} separate gameplay proxies across {economic_gameplay_proxy_country_count} countries | Exact-year 2001 WDI observations, supplemented with IMF WEO values only where the corresponding WDI value is absent. The IMF unemployment series remains a separately labeled alternative to modeled ILO unemployment; gameplay proxies retain their own low/very-low quality and do not change measured-series coverage. |
| Reported macroeconomic alternatives | {len(reported_economic_rows)} source records across {len(reported_economic_country_ids)} IDs | UNdata, national statistical offices, IMF staff reports, and census results retain their actual observation year/period, geography, and coverage in separate fields and read-only Economic Health tooltips; they do not replace comparable WDI, ILO, or WEO series. |
| Treaty and conflict records at 2001-01-01 | {treaty_count} treaty records; {war_count} active-conflict records | A source ledger covers {len(treaty_war_source_ids)} changed, contested, or excluded record IDs across {len(treaty_war_source_rows)} citations. Treaty participation is recorded separately from automatic gameplay effects. The ledger flags several French agreements whose 2001 status is inferred from pre-2001 signing and later official listings. Afghanistan and Colombia internal-conflict candidates remain excluded because the runtime schema accepts only country tags on both sides; assigning non-state factions as states would change the historical meaning. Some existing conflict sides are country-level proxies, not legal findings of interstate belligerency. |
| Unit Research progress and funding | 4 primary branches plus 3 strategic subtracks | Current OpenPower branch progress/funding is echoed across characteristic slots; the simulation has no per-characteristic or historical 2001 progress/funding series. |
| Country language descriptions | {language_statuses['reported']}/199 CIA Factbook fields; {language_context_coverage_count}/199 with historical context | CIA World Factbook 2001 wording is shown as historical context. {len(language_supplemental_context_rows)} separately attributed records provide legal, administrative, regional, or population-scope context for six territories without a usable national Factbook language description. Antarctica's entry records the absence of indigenous inhabitants and seasonal multinational research stations; it does not infer national language shares from temporary personnel. {language_statuses['entry_without_language_field']} entry has no Factbook language field; {language_statuses['not_separate_in_2001']} game territories lack separate 2001 Factbook entries. Context text is not converted into population shares. |
| Political-party names and leaders | {len(party_roster_rows):,} CIA records across {party_roster_country_count}/199; plus {len(party_roster_supplemental_rows)} election or political-context records across {len(party_roster_supplemental_country_ids)} other IDs | CIA World Factbook 2001 party/leader text remains the primary roster. Separate OSCE, UN, election commission, and political-pressure-group records bring named party or political context to {party_roster_name_context_count}/199 IDs; source year and scope remain explicit, and the records do not supply consistent leaders. Both appear in distinct read-only sections; neither supplies gameplay support, eligibility, or ruling status. |
| Election results | {len(election_result_rows)} result rows across {len(election_result_event_ids)} events and {len(election_result_country_ids)} game-country IDs | Certified or official results for Bangladesh, Denmark, Kosovo, Montenegro, Serbia, and Timor-Leste retain election date, territory, votes, vote share when reported, seats, result scope, and source. Result publication dates remain blank where the source does not report them. They are exposed as read-only historical outcomes and are not converted to current party support, eligibility, or government status. |
| History time-zero baselines | 5 population indicators plus 19 source-backed country indicator definitions seeded at game minute 0 for new games | Country birth/death/fertility/life-expectancy, land and surface measures, park and protected-area coverage, HDI, schooling, GNI, other land, and dated poverty estimates retain field-level provenance and availability. Adjacent-year/older observations retain their real source year; modeled, imputed, derived, proxy, and inferred values retain their quality kind. Unavailable values are explicit null gaps, distinct from measured zero. Current GDP and live HDI are not relabeled as 2001 observations. Existing saves are not backfilled. |
| World HDI | 1 world aggregate | Official UNDP 2001 aggregate: **0.657**. The interface labels this as a fixed historical baseline, not a live simulation metric. |
| Expected schooling, mean schooling, GNI per capita | 183, 178, 189 primary UNDP observations | UNDP HDR 2025 retrospective series for 2001; GNI is in 2021 PPP dollars. Separate compatible alternates add {development_available_counts['historical_school_life_expectancy_wdi_years_2001']} WDI school-life observations, {development_available_counts['historical_mean_schooling_barrolee_years_population_15plus_2000']} Barro–Lee 2000 observation for ages 15+, {development_available_counts['historical_mean_schooling_barrolee_years_population_25plus_2000']} Barro–Lee 2000 observation for ages 25+, and {development_available_counts['historical_gni_per_capita_wdi_ppp_current_intl_dollars_2001']} WDI current-PPP GNI observations; differing definitions and PPP years stay explicitly labeled. |
| Poverty-line estimate | {poverty_total_count}/199 primary records ({poverty_factbook_count} CIA estimates; {poverty_wdi_count} exact-year WDI national-line observations); {len(national_poverty_supplement_ids)} separate national-line alternatives | WDI core values use country-specific national poverty lines for exact-2001 observations. CIA Factbook estimates retain their stated observation year (1989–2000) or mark it unspecified; the edition date is not misrepresented as the observation year. The separate alternatives retain their actual reference years and survey/fieldwork periods: {national_poverty_supplement_year_summary}. Together the primary series and separate alternatives provide national-line observations for {national_poverty_coverage_with_supplements}/199 IDs; {national_poverty_remaining_gap_count} have no record in either table. These alternatives are displayed separately, preserve their source line, welfare measure and scope, and do not shift the 99/199 primary series or imply a 2001 survey where none occurred. CUB's 41.9% candidate is excluded because the source does not establish survey year and welfare measure; see the [gap audit](../../../modules/base/data/sources/2001/national_poverty_gap_audit_2001.md). |
| International poverty threshold | {len(international_poverty_country_ids)}/199 countries; {len(international_poverty_rows)} survey records; {poverty_scenario_estimate_count} separate gameplay estimates; {poverty_scenario_unavailable_count} unavailable | World Bank PIP national surveys at $3/person/day in 2021 PPP remain unchanged and have no neighboring-year substitution. The separate low-confidence gameplay model estimates the same international-line metric for countries without a 2001 PIP survey; it is not a survey or national-line observation. The observed records include {len(international_poverty_additional_ids)} IDs with no comparable national-line value; NIC income and consumption results remain distinct. |
| Regional population and age cohorts | {worldpop_region_count} WorldPop regions; {curated_region_count} territory-level observations, estimates, or staffing models | WorldPop's modeled 2001 1km total and age-sex rasters, spatially assigned through ISO region codes, with more specific territory-level observations taking precedence. Provenance records source year and any cohort-allocation assumption. |
| Regional biome and ecoregion | {len(regional_biomes)}/{len(regional_population)} regions | RESOLVE Ecoregions 2017 terrestrial polygons assigned by region center; a later spatial classification used as a scenario baseline, not a 2001 observation. |
| Other land (% of land area) | {len(other_land_direct_ids)}/199 direct FAOSTAT values; plus {len(other_land_scenario_ids)} separate low-confidence estimates ({', '.join(sorted(other_land_scenario_ids))}); {len(other_land_coverage_ids)}/199 values total | Direct values divide FAOSTAT 2001 `Other land` area by FAOSTAT 2001 `Land area`; all matched values in the October 2026 archive carry the `I` (imputed) source flag. The separate MNE and SRB residual estimates retain mixed observation periods, scope, and low confidence. CIA's non-comparable `other` alternatives for {', '.join(sorted(other_land_cia_alternative_ids))} remain separately labeled and do not fill the FAOSTAT field. Remaining FAOSTAT-compatible gaps: {', '.join(other_land_missing_ids)}. |
| Macroeconomic baselines | GDP {economic_coverage['historical_gdp_current_usd_2001']}/199; GDP per capita {economic_coverage['historical_gdp_per_capita_current_usd_2001']}/199; inflation {economic_coverage['historical_inflation_cpi_pct_2001']}/199; modeled ILO unemployment {economic_coverage['historical_unemployment_modeled_ilo_pct_2001']}/199; alternate IMF WEO unemployment {economic_coverage['historical_unemployment_imf_weo_pct_2001']}/199 | {economic_wdi_record_count} WDI and {economic_imf_record_count} IMF WEO exact-year source records, in addition to a coverage row for every country. The separate proxy ledger contains {len(economic_gameplay_proxy_rows)} low/very-low-confidence scenario estimates across {economic_gameplay_proxy_country_count} countries ({economic_gameplay_proxy_summary}) and {economic_gameplay_proxy_not_applicable_count} explicit not-applicable fields. Its runtime extension has {len(economic_gameplay_proxy_runtime_ids)} unique country rows; proxies do not replace measured baselines or reported alternatives. |
| Treaties and active conflicts | {treaty_count} treaty records; {war_count} conflict records | {len(treaty_war_source_ids)} record IDs have {len(treaty_war_source_rows)} source-ledger entries documenting corrections, contested scope, and excluded candidates. Membership records do not imply automatic gameplay effects. Several French agreements have status inferred from pre-2001 signing and later official listings. Afghanistan and Colombia internal-conflict candidates remain excluded because the runtime schema accepts only country tags on both sides; assigning non-state factions as states would change the historical meaning. Some conflict sides are country-tag proxies. |

Source bytes and per-field attribution are stored in [modules/base/data/sources/2001](../../../modules/base/data/sources/2001/README.md), with country-specific availability flags in `countries_historical.tsv` and `countries_economic_historical.tsv`. WDI and UNDP are retrospective revisions: they describe the year 2001 and do not reconstruct what policymakers knew on 1 January 2001. The UNSD protected-area figure is an adjacent 2000 observation, not a 2001 value.

**Regional coverage:** {worldpop_region_count} of {len(regional_population)} regions use WorldPop 2001 population and age-cohort rasters; {curated_region_count} use territory-specific observations or clearly labeled estimates and models; {unverified_region_count} still retain a legacy value without source verification. {assumed_zero_region_count} Antarctic regions and {assumed_zero_territory_count} territories use explicitly labeled uninhabited zero-population assumptions. Sources for {len(overlap_excluded_sources)} countries ({", ".join(overlap_excluded_sources) or "none"}) were excluded when fewer than 20% of their raster totals mapped to candidate game regions; details and checksums are in `worldpop_regional_raster_sources.tsv`. The per-region source status is in [regional_population_provenance.tsv](../../../modules/base/data/sources/2001/regional_population_provenance.tsv). The raster manifest records {imported_raster_count} published source files with SHA-256 checksums and {unpublished_raster_count} files that WorldPop does not publish. Duplicate Gaza/West Bank extension rows remain reconciled to their matching master-map region keys.

**Biome coverage:** {len(regional_biomes)} of {len(regional_population)} regions have a biome, ecoregion, and ecological realm from {biome_manifest['dataset']} ({biome_manifest['source_year']}). {biome_methods['contained']} map centers fell inside source polygons; {biome_methods['nearest']} offshore or unmatched centers use the nearest WGS84 source polygon. The snapshot contains {biome_manifest['ecoregion_count']} named ecoregions plus {biome_manifest['special_rock_and_ice_feature_count']} Rock and Ice classification feature; {biome_manifest['geometry_repaired_feature_count']} geometries required topology repair after the service generalized polygons by up to {biome_manifest['geometry_generalization_degrees']} degrees. The compressed source snapshot and SHA-256 are recorded in `resolve_ecoregions_2017_manifest.json`; assignment details are in `regions_biomes.tsv`. This source postdates the 2001 scenario and is explicitly a spatial classification baseline, not a historical 2001 ecological survey.

## Interface data changes

- **Country Information:** shows sourced arable land, forest area, birth/death rates, national climate, water and total area; tooltips expose field source, observation year, scope, quality flags, and conflicts such as Ukraine's CIA water-area report versus the WDI area pair. It uses UNDP's world aggregate. The land slot shows `Protected areas (2000)` when a broad all-category measure is available; for Kosovo, Montenegro, and São Tomé and Príncipe it falls back to separately sourced or explicitly inferred `National parks (2001)` coverage. Taiwan's broad 2000 measure is available, while its separate park-only value remains in the source data. Maldives' broad terrestrial value is a derived zero; Nauru's is a directly reported zero from April 2000. Palestine's 2000 (54.4 km²) and approximate 2001 (about 54 km²) PNA-controlled natural-reserve areas appear in the protected-area tooltip as West Bank context only; the 2000 Gaza row is blank despite the separate Wadi Gaza designation, so neither is converted to a national percentage or park value. The `Other land` slot prioritizes the FAOSTAT series, shows MNE/SRB residuals only as low-confidence estimates when no direct value exists, and keeps Taiwan's and Kosovo's differently defined CIA `other` figures in the tooltip as non-comparable alternatives. The old `Unusable land` slot now says `Other land`, and the broader residual category is not described as unusable. Human-development tooltips keep UNDP schooling/GNI separate from WDI school life expectancy/current-PPP GNI and the 2000 Barro–Lee estimate. Population detail exposes the $3/day 2021-PPP survey record and, where the survey is unavailable, a separately labeled gameplay estimate with its model inputs and confidence; neither replaces the country-specific national-poverty series. Other tooltips expose available fertility, life expectancy, poverty-estimate year, region composition, leading production sectors, and the 2001 population-source coverage caveat. Population age composition uses WorldPop estimates where region-level raster coverage exists and source-specific observations or labeled models elsewhere; each region's provenance is recorded in the source table. The country HDI shows historical scores only where a dated value, disclosed estimate, or explicit proxy is available; tooltips distinguish current UNDP series, older published methodology, models, proxies, and non-applicable cases.
- **Politics and Treaty Details:** displays live treaty pressure derived from current fielded military value and pressure sponsors. Pressure support and treaty acceptance are separate actions. This is a simulation-derived measure, not historical 2001 data or domestic approval.
- **Economic Health:** tooltips expose exact-year 2001 GDP, GDP per capita, CPI inflation, and unemployment with per-value source attribution, plus separately labeled national, census, city-only, fiscal-year, and agency estimates where available. Low/very-low-confidence gameplay proxies appear only in a distinct, explicitly modeled section with scenario year, method, quality, scope, source note, and URLs; they do not appear as observed national baselines. WDI is preferred; October 2026 IMF WEO supplements only missing GDP, GDP-per-capita, and inflation cells. IMF WEO unemployment and reported supplemental observations remain alternatives to modeled ILO unemployment, not replacements for its missing values.
- **Resources:** global tax, signed desired trade in annual USD, and meet-consumption now persist through policy actions and the shared-market clearing policy. The 2% default is a gameplay default, not historical national tax data.
- **Unit production:** normal and fast production use a common authoritative quote. The premium and work reduction are gameplay tuning, not historical unit-cost measurements.
- **Internal Laws — Languages:** the Details view adds CIA Factbook 2001 wording where reported and separately attributed legal, administrative, regional, or population-scope context for six territories without a usable national Factbook language description, while continuing to label numeric population shares as OpenPower gameplay estimates.
- **History:** new games begin with provenance-linked minute-zero observations for regional cohorts/population and historical country measures. The History selector labels each baseline measure and its reference year; CSV export retains actual observation years, source URLs, and method notes. Unavailable country values are explicit null gaps, distinct from measured zeros, and existing saves are not backfilled.
- **Political parties:** Country Information's party roster button opens separate CIA Factbook and alternate-source sections. The Factbook roster retains party/leader text; a separately labeled section shows {len(party_roster_supplemental_rows)} source-cited election/party records across {len(party_roster_supplemental_country_ids)} additional IDs, including Serbia's 2000 election and Palestine's 1996 PLC outcome categories, without inferred leaders. Neither section populates gameplay party IDs or creates support shares, a ruling-party flag, or eligibility.
- **Unit Research:** all 12 Technology meters load a low-confidence country baseline; Progress and Funding show authoritative branch-level simulation values echoed across characteristic slots. The UI explains that these values are modeled/shared and has no source-backed historical per-characteristic research record.

## Remaining data gaps and source limits

- **Country Information land tab:** a full-country national-parks-only series remains unavailable. The UI shows the all-category terrestrial share for 2000 in {protected_area_count} of 199 countries ({len(protected_area_records)} direct UNSD observations, the derived Maldives zero, Nauru's directly reported zero, and Taiwan's reported 18.7% all-category share). Taiwan's yearbook excludes maritime area, so its denominator differs from the UNSD total-surface measure and is labeled separately. Where the broader value is absent, the same slot instead shows park-only 2001 coverage for Kosovo, Montenegro, and São Tomé and Príncipe; Maldives' separately sourced park-only area is also retained. Nauru's direct April 2000 report supports its 0% broad coverage and 0 km² of designated national parks; it is not inferred from later reports. The ten-row evidence ledger keeps broad and park-only measures separate and leaves unsupported cases blank. Palestine's 2000 54.4 km² and approximate 2001 about 54 km² PNA-controlled natural-reserve observations appear in the tooltip as scoped West Bank area context only. The 2000 table's Gaza row is blank despite Wadi Gaza's separate designation, leaving incomplete Gaza coverage; the candidate series therefore does not fill a national percentage or national-park field. The current WDPA series is not substituted because it backfills earlier designations and cannot reconstruct the 2001 database snapshot.
- **Other land:** the old `Unusable land` label was corrected to FAOSTAT's `Other land (2001)` category for {len(other_land_direct_ids)} countries. The October 2026 source archive marks every matched value as imputed by a receiving agency (`I`); the UI displays this flag. Separate low-confidence estimates cover {', '.join(sorted(other_land_scenario_ids))} where direct FAOSTAT values are absent; their tooltips disclose actual input periods, residual method, territorial scope, confidence and source limitations. CIA's differently defined `other` land-use categories for {', '.join(sorted(other_land_cia_alternative_ids))} remain tooltip-only alternatives; they do not compare directly with FAOSTAT's residual or fill the plotted value. FAOSTAT-compatible values remain unavailable for {', '.join(other_land_missing_ids)}.
- **Regional population coverage:** {unverified_region_count} of {len(regional_population)} rows still use a legacy baseline without source verification. The 18 formerly unverified regions now use territory-specific estimates, station staffing models, or explicit zero-resident assumptions, each labeled in the provenance table. Station models count people present in the scenario and are distinct from indigenous or family settlement; exact 2001 age bands are unavailable for several territories, so those cohorts are modeled. Antarctica's two zero assumptions exclude transient research-station populations; Bouvet and Rose Atoll are separately sourced uninhabited-territory assumptions. WorldPop estimates are retrospective model outputs, not a record of what was known in 2001. Region totals are assigned by source-cell center and proportionally reconciled to source-country totals only when overlap meets the documented threshold; see the region-level method and correction factor in `regional_population_provenance.tsv`.
- **Regional biomes:** every region is populated from the licensed RESOLVE Ecoregions 2017 classification. It fills the regional display with real ecoregion and biome labels, but the source year is 2017; it cannot verify which classification a 2001 snapshot would have used. Exact historical 2001 boundary/biome changes remain unmeasured. National climate descriptions are not spread across regional hexes.
- **Unit Research:** the 12 Technology factors are low-confidence scenario estimates aligned with OpenPower's existing bootstrap model, using UNDP-derived human development and a game research-budget setting. They do not establish a country's deployed technology, defense R&D, weapon specification, or historical technology ceiling. Progress and Funding are live branch-level game state rather than 2001 observations; the system does not contain a factual, per-country 2001 series for those measures.
- **Macroeconomic series:** after supplementing missing WDI values with exact-year IMF WEO data, {199 - economic_coverage['historical_gdp_current_usd_2001']} GDP records, {199 - economic_coverage['historical_gdp_per_capita_current_usd_2001']} GDP-per-capita records, and {199 - economic_coverage['historical_inflation_cpi_pct_2001']} CPI inflation records remain unavailable. Modeled ILO unemployment remains unavailable for {199 - economic_coverage['historical_unemployment_modeled_ilo_pct_2001']} countries; the separate IMF WEO unemployment alternative covers {economic_coverage['historical_unemployment_imf_weo_pct_2001']} countries and does not close ILO series gaps. All absent observations retain explicit availability flags.
- **Poverty estimates:** dated country-specific national-poverty estimates cover {poverty_total_count}/199 primary records, including {poverty_wdi_count} exact-year 2001 WDI observations used only where the CIA Factbook field is blank. {len(national_poverty_supplement_ids)} separately displayed national-line alternatives preserve their actual reference years and survey/fieldwork periods: {national_poverty_supplement_year_summary}. They bring distinct source-backed coverage to {national_poverty_coverage_with_supplements}/199 without entering the primary series or being relabeled as 2001 observations. The remaining {national_poverty_remaining_gap_count} IDs have no comparable national-line value in the reviewed sources. The separate PIP $3/day 2021-PPP survey series covers {len(international_poverty_country_ids)}/199 and contributes {len(international_poverty_additional_ids)} otherwise-missing IDs. A reproducible nearest-neighbor scenario model adds {poverty_scenario_estimate_count} low-confidence estimates for this international line; {poverty_scenario_unavailable_count} cases have no estimate. Those estimates are not surveys or national-line observations, and the later PPP vintage was not used in 2001.
- **Land and surface area:** arable land is still unavailable for {len(historical_missing_ids['arable_land_pct'])} IDs ({", ".join(historical_missing_ids['arable_land_pct'])}); forest share for {len(historical_missing_ids['forest_area_pct'])} ({", ".join(historical_missing_ids['forest_area_pct'])}); land area for {len(historical_missing_ids['reference_land_area_km2'])} ({", ".join(historical_missing_ids['reference_land_area_km2'])}); total surface for {len(historical_missing_ids['reference_total_area_km2'])} ({", ".join(historical_missing_ids['reference_total_area_km2'])}); and inland water for {len(historical_missing_ids['reference_water_area_km2'])} ({", ".join(historical_missing_ids['reference_water_area_km2'])}). {land_metric_adjacent_year_count} populated land/forest/water values are explicitly dated 2000. For country-by-country values, signed deltas, source notes, and unmatched territories, see the [199-country CIA/WDI comparison ledger](../../../modules/base/data/sources/2001/area_source_conflicts_2001.tsv) and its [methods report](../../../modules/base/data/sources/2001/area_source_conflicts_2001.md). Kosovo-area candidates remain excluded while the Serbia row includes Kosovo; source gaps are not encoded as zero.
- **Treaty and conflict scope:** the current roster contains {treaty_count} treaty records and {war_count} active-conflict records. It is a bounded country-tag dataset, not a complete registry of every bilateral agreement or armed group. The war schema cannot independently encode non-state forces, peacekeepers, external support, or legal belligerent status; proxy sides are documented in the source ledger and report.
- **Military stocks:** {military_personnel_uncovered_count} of 199 active-personnel counts have no row-level historical source yet ({", ".join(military_personnel_uncovered_ids)}). Nine separate gameplay estimates cover {", ".join(military_personnel_gameplay_estimate_ids)}; they are explicitly non-historical and are not imported into factual `military_count`, so they do not close those gaps. ATA is not applicable to a sovereign military roster and SSD is unavailable for a separate national-force scope in 2001. The [personnel gap audit](../../../modules/base/data/sources/2001/military_personnel_gap_audit_2001.md) lists reviewed candidates and their incompatible scopes. The equipment-role inventories are broader OpenPower scenario estimates; the supplemental ledger verifies {len(military_equipment_supplement_rows)} specific counts for Russia, China, India, the United States, and France, while most countries and roles still lack comparable open 2001 equipment totals.
- **Country language shares:** CIA Factbook 2001 descriptions are available for {language_statuses['reported']} countries; separately sourced legal/administrative/regional context brings historical language context coverage to {language_context_coverage_count}/199. The supplemental records do not supply comparable language prevalence or population shares. For Antarctica, seasonal multinational research-station staffing cannot establish a national language community. {language_unavailable_context_count} game-country records still lack a source-backed language description or contextual record; those numeric shares remain labeled as gameplay estimates.
- **Party support and status:** the CIA Factbook names parties and sometimes leaders but contains no comparable vote/support shares, eligibility rules, or ruling-party field. The {len(party_roster_supplemental_rows)} supplemental rows include bounded election results/lists and one political-pressure-group context record for {", ".join(sorted(party_roster_supplemental_country_ids))}; source dates vary and are shown in the interface and ledger, so they are historical context rather than a complete 2001 roster. Together the sources provide named party or political context for {party_roster_name_context_count}/199 IDs. The remaining uncovered IDs are {", ".join(party_roster_uncovered_ids)}; no support or ruling status is inferred. Separately, {len(election_result_rows)} documented election-result rows cover {", ".join(sorted(election_result_country_ids))}; they report only the metrics present in each source.
- **National HDI:** 170 of 199 country records use the UNDP HDR 2025 retrospective series; 16 use an official UNDP-published 2001 value from HDR 2003 with its older methodology; 7 use transparent component/formula estimates; and 4 use clearly labeled regional/national/territory proxies. Antarctica and Vatican City have no historical HDI score; the simulation uses a neutral 0.50 fallback that the UI does not display as an observed index. See `hdi_backfills_2001.tsv` and the source notes in the data archive. Older and estimated values are not methodologically interchangeable with the HDR 2025 series.
- **Visual and workflow assets:** exact source-localization tables and the full 3D reference model/texture assets are absent. Multiplayer discovery, lobby presence, and chat also lack an authoritative session backend.
- A visible em dash means the relevant observation is unavailable, not measured zero. Availability flags are preserved because the loader normalizes absent numeric values.

## Verification record

The source audit regenerated 150 inventory entries from {source_root_count} GML roots, {len(component_rows):,} resolved component records, {len(display_rows):,} display contracts, {len(interaction_rows):,} interaction contracts, and {len(gap_rows):,} gap rows. The latest recorded evidence includes {journey_evidence['passed']}/{journey_evidence['total']} journey cases and {surface_evidence['passed']}/{surface_evidence['total']} surface-matrix runs across {surface_evidence['surfaces']} surfaces and {surface_evidence['viewports']} requested viewport sizes. See `artifacts/ui/reference/goal-2001-journeys-final-20261115/suite.json` and `artifacts/ui/reference/goal-2001-surface-matrix-final-20261115/suite.json` for the machine-readable results. The current audit found 20 configured functional-matrix suites but no `suite.json` run records (0/0), so no current functional-matrix pass is claimed; the older 80/80 statement in `verification.md` is not represented in current machine-readable artifacts. The poverty scenario generator validates {poverty_scenario_estimate_count} reproducible international-line estimates among {len(poverty_scenario_estimate_rows)} countries without a PIP survey, with {poverty_scenario_unavailable_count} cases left unestimated. The macro proxy generator validates {len(economic_gameplay_proxy_rows)} separate scenario estimates in {len(economic_gameplay_proxy_ledger_rows)} ledger records; its runtime extension keeps one unique row for each of {len(economic_gameplay_proxy_runtime_ids)} target IDs, preventing duplicate-country joins. The Other land extension has {len(other_land_supplement_rows)} unique country rows with {len(other_land_scenario_ids)} separately labeled estimates; its generator verifies the residual against the cached FAOSTAT archive. Palestinian reserve context uses {len(palestinian_natural_reserve_runtime_rows)} unique country row for {len(palestinian_reserve_runtime_ids)} ID and retains observation years {', '.join(palestinian_reserve_runtime_years)} without creating a national share. The WorldPop import processed {len({row.get('source_iso3', '') for row in raster_sources})} source codes and validated matching unique keys across all {len(regional_population)} region, population, and provenance rows; no cohort is negative, all {worldpop_region_count} accepted raster regions use a reconciliation factor at or below 5x, and every verified raster has a SHA-256 digest. The biome import matched all {len(regional_biomes)} region keys against the same roster; its snapshot contains {biome_manifest['source_feature_count']} attributed source features, including {biome_manifest['ecoregion_count']} named ecoregions, with a recorded checksum. Imported data and interface behavior were validated by focused tests, source-loader checks, and the architecture checker; current counts are recorded in the run artifacts. The equipment supplement importer verified all {len(military_equipment_supplement_rows)} recorded role counts; regional keys and importer provenance were validated.

The 2001 country-info native journey screenshot is at `.tmp/country-historical-2001/actual.png`.

## Source references

- [World Bank indicator metadata for terrestrial protected areas](https://databank.worldbank.org/metadataglossary/millennium-development-goals/series/ER.LND.PTLD.ZS) defines the measure and its 2013–2025 reference period.
- Taiwan's [Statistical Yearbook of the Republic of China 2009, Table 69](https://ws.dgbas.gov.tw/001/Upload/466/ebook/ebook_90360/pdf/full.pdf) retrospectively reports 2000 nature-protected areas as 691,731 ha and 18.7% of national territory, excluding maritime area; this remains separately scoped from the UNSD denominator and Taiwan's park-only 2001 inventory.
- Official election tabulations include the [Bangladesh Election Commission's 2001 results](https://www.ecs.gov.bd/files/WqafvkDhpbk4kb1MV6PNWIHvIngSvbLWrVIhVxEK.pdf) and the [Danish Ministry of the Interior's final 20 November 2001 result](https://www.valg.im.dk/noegletal/folketingsvalg/tidligere-folketingsvalg/endelig-opgoerelse-af-folketingsvalget-den-20-november-2001).
- [Nauru's April 2000 Pacific Community environmental-vulnerability report](https://spccfpstore1.blob.core.windows.net/digitallibrary-docs/files/71/71445f1b5a59f2d843955a1baa0d9d08.pdf) directly reports no terrestrial or marine reserves set aside for environmental management or refugia, supporting a reported 0% broad terrestrial protected-area share for 2000 and zero designated national-park area. The 1996 Nauru National Environmental Management Strategy describes candidate conservation sites and future designation work; the later [CBD Sixth National Report](https://www.cbd.int/doc/nr/nr-06/nr-nr-06-en.pdf) reports no gazetted protected areas.
- [Protected Planet: why WDPA releases differ](https://www.protectedplanet.net/en/news-and-stories/why-do-we-have-different-versions-of-the-wdpa) explains data-provider usage restrictions; [the WDPA lag-effect note](https://www.protectedplanet.net/en/news-and-stories/the-lag-effect-in-the-world-database-on-protected-areas) explains retrospective backfilling of earlier designations.
- [WorldPop Global1 2000–2020](https://hub.worldpop.org/Global1_2000-2020) documents the archived population products and CC BY 4.0 license; [2001 1km population rasters](https://data.worldpop.org/GIS/Population/Global_2000_2020_1km/2001/) and [2001 1km age-sex rasters](https://data.worldpop.org/GIS/AgeSex_structures/Global_2000_2020_1km/unconstrained/2001/) are the source files used for the regional estimate.
- [Maldives Bureau of Statistics, Table 3.3](https://statisticsmaldives.gov.mv/yearbook2012/yearbook/Population/3.3.htm) reports 2000 counts for Malé and each atoll; [Table 2.2](https://statisticsmaldives.gov.mv/yearbook/statisticalarchive/wp-content/uploads/sites/3/2025/06/2.2.pdf) provides the national 2000 age profile used only to allocate regional cohorts.
- [Statistics Mauritius, 2000 Population Census](https://statsmauritius.govmu.org/Documents/Census_and_Surveys/HPC/2000/TR_VOLVI-Geopraphical_Migration_Characteristics.pdf) reports 289 residents on Agalega; [BITRE Table 6](https://www.bitre.gov.au/sites/default/files/stats_002_ar03.pdf) reports four on Coral Sea Islands in 2001.
- [INSEE's 1 January 2001 population estimates for the French departments](https://www.bnsp.insee.fr/ark:/12148/bc6p06wfxm5.pdf) supply totals and broad age bands for Guadeloupe, Martinique, and French Guiana; [INSEE's Réunion demographic report](https://www.insee.fr/fr/statistiques/fichier/1293474/resultats31.pdf) supplies the 2001 total. Their modeled detailed cohorts use the [1999 age tables](https://www.vie-publique.fr/files/rapport/pdf/014000573.pdf). [INSEE Mayotte census counts](https://www.insee.fr/fr/statistiques/fichier/1291531/insee_infos_32.pdf) supply the 1997 and 2002 totals used for linear interpolation.
- [Gibraltar's 2001 Census](https://www.gibraltar.gov.gi/new/sites/default/files/HMGoG_Documents/Statistics/Downloads/census_of_gibraltar_2001.pdf) reports total population and age groups. [Cook Islands' 2001 Census](https://cookislands-data.sprep.org/system/files/2001%20Census%20of%20Population%20and%20Dwellings.pdf) reports island populations and five-year age tables used for Aitutaki, Pukapuka, Manihiki, and Penrhyn.
- [Malta's Demographic Review 2001](https://nso.gov.mt/wp-content/uploads/Demography2001.pdf) provides total-population locality estimates in Table 6B and national age-group totals used to model locality cohorts. [The Netherlands Antilles 2001 census, Table DE.6](https://www.cbs.cw/_flysystem/media/tables-de-demographic-characteristics.pdf) reports exact island age groups for Bonaire, Saba, and Sint Eustatius, cross-checked against [island totals in Table G.1](https://www.cbs.cw/_flysystem/media/tables-g-geographical-characteristics.pdf).
- [Anguilla's 2001 National Census Report](https://statistics.caricom.org/wp-content/uploads/2026/01/Anguilla.pdf) reports district 0-14 and 15-64 cohorts in Tables 8.3 and 8.10; [the Government of Anguilla's district census table](https://www.gov.ai/stats/cab_Population_files/sheet006.htm) provides 2001 totals for Island Harbour and Sandy Ground.
- [Slovenia's Statistical Office, 2002 census table 05W0402S](https://pxweb.stat.si/SiStatData/pxweb/en/Data/-/05W0402S.px) provides Razkrižje's exact municipality total and five-year age groups; the 2002 census count is carried as the nearest 2001 scenario baseline.
- [Seychelles' 2002 Population and Housing Census, Table 30](https://digitallibrary.un.org/record/725970/files/CEDAW_C_SYC_1-5-EN.pdf) provides the Saint Louis district total. Its [national age-group table](https://uil.unesco.org/fileadmin/multimedia/uil/confintea/pdf/National_Reports/Africa/Africa/Seychelles.pdf) is used only to model the district cohorts.
- [Tuvalu's June 2001 Central Statistics Division estimate](https://www.adb.org/sites/default/files/publication/28817/tuvalu-2002-epsr.pdf) is reported in the ADB 2002 review, Table 1.1 note. Age shares are allocated from [Tuvalu's 2002 Census Volume II, Table A7](https://www.fao.org/fileadmin/templates/ess/ess_test_folder/World_Census_Agriculture/Country_info_2000/Reports_2/TUV_ENG_REP2_2002.pdf).
- [The CIA World Factbook 2001](https://www.gutenberg.org/cache/epub/27638/pg27638-images.html) identifies Ashmore and Cartier as having no indigenous inhabitants and seasonal caretakers, and Heard and Clipperton as uninhabited. Seasonal personnel and visitors are excluded from resident-population assumptions. [Stats NZ's 2001 census introduction](https://www.otago.ac.nz/__data/assets/pdf_file/0012/302412/2001-introduction-to-the-census-025338.pdf) confirms the Kermadec Islands were in the census coverage; the [official yearbook](https://www3.stats.govt.nz/new_zealand_official_yearbooks/2002/NZOYB_2002.html) shows that public totals aggregate them with the North Island or areas outside territorial authorities. A secondary [2001 census island summary](https://www.olps.co.za/kiwix/content/wikipedia_en_all_maxi_2024-01/A/Territorial_authorities_of_New_Zealand) lists three Kermadec residents; the value remains labeled as secondary-source evidence, and its age split is a working-age station-staff assumption.
- [Palau's Statistical Yearbook 2002-2003](https://www.palaugov.pw/wp-content/uploads/2013/10/2002-2003-Statistical-Yearbook.pdf) reports 2000 state totals; age cohorts for Hatohobei and Sonsorol are proportional allocations from the national 2000 census distribution. [The UN Tokelau country paper](https://documents.un.org/doc/undoc/gen/n04/283/12/pdf/n0428312.pdf) reports 1,518 at the 11 October 2001 census; other UN summaries report 1,537, and the selected source discrepancy is recorded in provenance.
- [Statistics Norway's Svalbard population table](https://www.ssb.no/198199/population-in-the-settlements.svalbard) reports the 2001 aggregate. The [U.S. Census Bureau Census 2000 report](https://www2.census.gov/programs-surveys/decennial/2000/data/phc/phc-3-01-pt1.pdf) gives the Johnston Atoll count and zero-value dashes for the other U.S. Minor Outlying Islands. [The Norwegian Government's Bouvet Island report](https://www.regjeringen.no/no/dokumenter/meld.-st.-33-20142015/id2415895/?ch=2) describes the island as uninhabited; its scenario zero is explicitly an assumption rather than a 2001 census count.
- [Morocco's High Commission for Planning](https://www.hcp.ma/region-drda/attachment/396869/) reports 1994 and 2004 Oued Ed-Dahab census totals; the 2001 scenario value is interpolated between those counts.
- [The CIA World Factbook 2001](https://www.thefactbook.org/western-sahara/2001) reports 250,559 for Western Sahara and [890 for the Holy See](https://thefactbook.org/holy-see/2001); its [British Indian Ocean Territory entry](https://www.thefactbook.org/british-indian-ocean-territory/2001) records the nearest numeric Diego Garcia staffing estimate in 1995. The [CIA 2000 Factbook entries for Paracel](https://www.thefactbook.org/paracel-islands/2000) and [Spratly](https://www.thefactbook.org/spratly-islands/2000) provide the nearest numeric garrison estimates carried into 2001.
- [Government of Jammu and Kashmir regional indicators](https://www.ecostatjk.nic.in/pdf/publications/regindicator/Regional%20indicators%202016-17%20web.pdf) report the Kashmir Region's 2001 census total. The [TRNC Statistical Yearbook 2020](https://stat.gov.ct.tr/Portals/39/IST-YILLIK-2020.pdf) publishes the 1996 and 2006 census totals used to interpolate the 2001 Northern Cyprus value.
- [UK Parliament's 2004 written answer](https://publications.parliament.uk/pa/cm200304/cmhansrd/vo041025/text/41025w22.htm) gives the 2001 SBA civilian counts and an approximate UK personnel/dependent population; the [2001 Republic of Cyprus census](https://library.cystat.gov.cy/Documents/Publication/CENSUS%20OF%20POPULATION%202001-VOL.1.pdf) supplies the national age shares used for the Cypriot cohorts, and the [Council of Europe SBA report](https://assembly.coe.int/Documents/WorkingDocs/2007/EDOC11232.pdf) supplies the station military split used for allocation.
- The [2001 Guantanamo estimate](https://www.chron.com/news/article/high-security-jail-being-built-at-Guantanamo-2071878.php) covers military personnel, contractors, and dependents. The [UNESCO Malpelo nomination](https://whc.unesco.org/uploads/nominations/1216.pdf) describes the rotating Colombian Navy post; the [Venezuelan Academy of Physical, Mathematical and Natural Sciences](https://acfiman.org/wp-content/uploads/2024/03/isla_de_aves.pdf) documents the Simón Bolívar station at Isla de Aves.
- The French [Senate's 1991 TAAF wintering report](https://www.senat.fr/rap/r92-279/r92-2791.pdf) supplies a district staffing ratio; the CIA 2001 Factbook gives the later aggregate researcher estimate. The [French National Assembly's Eparses staffing answer](https://questions.assemblee-nationale.fr/q13/13-78874QE.htm) gives the military and weather-station personnel used for the Scattered Islands model. British Antarctic Survey pages report current winter staffing at [King Edward Point](https://www.bas.ac.uk/polar-operations/sites-and-facilities/facility/king-edward-point/) and [Bird Island](https://www.bas.ac.uk/polar-operations/sites-and-facilities/facility/bird-island/); the CIA 2001 entry records the March 2001 change from the South Georgia garrison to BAS operation.
- [U.S. Fish and Wildlife Service](https://stage.fws.gov/refuge/rose-atoll/what-we-do) identifies Rose Atoll as uninhabited. Station staffing values and zero assumptions are labeled separately in the provenance table rather than presented as census counts.
- [RESOLVE Ecoregions 2017](https://ecoregions2017.appspot.com/) provides the 846 terrestrial ecoregion classification under CC BY 4.0; the corresponding [ArcGIS Feature Service](https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/Resolve_Ecoregions/FeatureServer/0) supplies the attributed polygon snapshot used for map assignment.
- [FAOSTAT Land Use](https://www.fao.org/faostat/en/#data/RL) provides the historical land-use series; its official catalog lists `Other land` from 1990 and the area unit as 1,000 hectares. The [FAOSTAT terms](https://www.fao.org/contact-us/terms/db-terms-of-use/en/) and source quality flags apply to the archived data.
- `utils/generate_other_land_supplement_2001.py` verifies the cached FAOSTAT Serbia-and-Montenegro residual and emits separate MNE/SRB scenario estimates. Its input ledger records the 2000 FAO and mixed-period national sources; neither estimate overwrites the primary FAOSTAT field. CIA's Taiwan `other: 15%` and Kosovo `other: 5.5%` alternatives stay separate because their category definitions do not match FAOSTAT `Other land`.
- `utils/generate_palestinian_reserve_context_2001.py` preserves the PCBS 2000 and 2001 PNA-controlled natural-reserve areas in one namespaced PSE runtime row. PCBS scope limitations and source locations remain visible in the Country Information protected-area tooltip; these observations do not establish a national parks total or national protected-area percentage.
- The accepted land supplements retain raw FAOSTAT flags and numerator/denominator calculations in `faostat_land_metric_supplement_2001.tsv`; Montenegro's land, inland water, and forest observations remain explicitly dated 2000 from [FAO's Montenegro FRA report](https://www.fao.org/4/al572E/al572E.pdf). Kosovo area candidates remain excluded pending a consistent Serbia/Kosovo boundary definition.
- The [World Bank WDI military-personnel series](https://api.worldbank.org/v2/country/all/indicator/MS.MIL.TOTL.P1?date=2001&format=json&per_page=300) and [indicator definition](https://databank.worldbank.org/metadataglossary/world-development-indicators/series/MS.MIL.TOTL.P1) provide the exact-year baseline; the [supplemental personnel ledger](../../../modules/base/data/sources/2001/military_personnel_supplemental_2001.tsv) records additional row-level sources, observation years, and scope qualifications.
- The separate [military gameplay-estimate ledger](../../../modules/base/data/sources/2001/military_personnel_gameplay_estimates_2001.tsv) and [method note](../../../modules/base/data/sources/2001/military_personnel_gameplay_estimates_2001.md) document nine low/very-low-confidence scenario values for {", ".join(military_personnel_gameplay_estimate_ids)}; all are excluded from factual `military_count`, ATA is not applicable, and SSD remains unavailable.
- Exact-year 2001 World Bank WDI series supply [GDP](https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.CD?date=2001&format=json&per_page=1000), [GDP per capita](https://api.worldbank.org/v2/country/all/indicator/NY.GDP.PCAP.CD?date=2001&format=json&per_page=1000), [CPI inflation](https://api.worldbank.org/v2/country/all/indicator/FP.CPI.TOTL.ZG?date=2001&format=json&per_page=1000), and [modeled ILO unemployment](https://api.worldbank.org/v2/country/all/indicator/SL.UEM.TOTL.ZS?date=2001&format=json&per_page=1000). Their archived responses and field-level coverage are recorded with the economic extension.
- `utils/generate_economic_gameplay_proxies_2001.py` builds a separate long-form ledger and one-row-per-country runtime extension for 12 explicitly modeled 2001 scenario proxies; the method note describes peer inputs and limits. Proxies remain separate from source-backed baseline and alternative series.
- October 2026 IMF WEO supplements missing 2001 values for [GDP](https://www.imf.org/external/datamapper/api/v2/NGDPD?periods=2001), [GDP per capita](https://www.imf.org/external/datamapper/api/v2/NGDPDPC?periods=2001), and [consumer-price inflation](https://www.imf.org/external/datamapper/api/v2/PCPIPCH?periods=2001). Its separate [unemployment series](https://www.imf.org/external/datamapper/api/v2/LUR?periods=2001) is retained as an alternative; source timestamps, definitions, and field-level coverage are documented in the economic extension.
- The exact-year 2001 World Bank WDI [national poverty headcount series](https://api.worldbank.org/v2/country/all/indicator/SI.POV.NAHC?date=2001&format=json&per_page=1000) adds values only to otherwise blank country records. The [indicator definition](https://databank.worldbank.org/metadataglossary/world-development-indicators/series/SI.POV.NAHC) states that these estimates use country-specific national poverty lines.
- Five separate national-line observations for {national_poverty_supplement_year_summary} are preserved in the [supplement table](../../../modules/base/data/countries/countries_poverty_national_supplement_2001.tsv); its source references retain each actual reference year, survey period, line definition, welfare measure, and scope.
- The separate [World Bank PIP API](https://api.worldbank.org/pip/v1/pip) provides the 2001 national survey results at $3 per person per day in 2021 PPP; its [documentation](https://worldbank.github.io/pip/help_file.html) defines the survey fields and welfare measures. The response snapshot, version, PPP factors, coverage, and unchanged survey-year values are in `pip_2021_ppp_3usd_2001.json` and `pip_2021_ppp_3usd_2001.tsv`.
- `utils/generate_poverty_scenario_estimates_2001.py` derives separate gameplay estimates for countries without a 2001 PIP survey using the PIP observation snapshot, exact-year WDI GNI per capita PPP, and the scenario's dated HDI inputs. The generated TSV records its nearest training cases, input quality, confidence, method, source URLs, and SHA-256; it does not alter national-line or survey values.
- The education and income supplements use exact-year World Bank WDI [school life expectancy](https://api.worldbank.org/v2/country/all/indicator/SE.SCH.LIFE?date=2001&format=json&per_page=1000) and [GNI per capita in current PPP dollars](https://api.worldbank.org/v2/country/all/indicator/NY.GNP.PCAP.PP.CD?date=2001&format=json&per_page=1000), plus Barro and Lee's [2013 educational-attainment dataset](https://barrolee.github.io/BarroLeeDataSet/) for its 2000 estimate. Each stays distinct from the differently defined UNDP components.
- Separate reported macroeconomic observations and their limitations are documented in `economic_supplement_2001.md` and `economic_macro_gap_research_notes_2001.md`; annual, city-only, census, and fiscal-year figures do not replace the primary WDI/ILO measures.
- The World Bank's [surface-area definition](https://databank.worldbank.org/metadataglossary/world-development-indicators/series/AG.SRF.TOTL.K2) includes inland water bodies and some coastal waterways and warns that country-area consistency is limited. CIA Factbook 2001 provides a separate edition snapshot; for Canada, Statistics Canada's [2009 land and freshwater table](https://www150.statcan.gc.ca/n1/pub/11-402-x/2009000/pdf/geography-geographie-eng.pdf) demonstrates a distinct national area series. Provenance and unresolved country-level discrepancies are recorded separately; these sources are not silently reconciled.
- Supplemental climate context for territories without separate 2001 Factbook entries cites the [CIA World Factbook 2001](https://www.gutenberg.org/ebooks/27638), the UN's [East Timor report A/AC.109/2000/12](https://digitallibrary.un.org/record/417940/files/A_AC.109_2000_12-EN.pdf), and the UN [Kosovo core document](https://digitallibrary.un.org/record/626003/files/HRI_CORE_UNK_2007-EN.pdf), which cites the 1999 Kosovo climate assessment. The displayed text is attributed context, not a 2001 weather observation.
- The military equipment supplement cites [Norris et al., Russian Nuclear Forces 2001](https://journals.sagepub.com/doi/full/10.2968/057003023), [CRS on China's 2001 carrier inventory](https://www.everycrsreport.com/files/20011112_RL31183_d196d88b6fb391d800fa28fde4d8a465fee91937.html), the [Indian Parliament's March 2001 carrier answer](https://eparlib.sansad.in/bitstream/123456789/402862/1/19961.pdf), the [U.S. Naval History and Heritage Command fleet table](https://www.history.navy.mil/research/histories/ship-histories/us-ship-force-levels.html), and the [French Senate's 2002 Navy budget opinion](https://www.senat.fr/rap/a01-090-8/a01-090-86.html); its ledger restricts each claim to the cited operational role, date, and availability scope.
- The [2001 treaty and conflict review](../../../modules/base/data/sources/2001/world_conflicts_treaties_2001.md) and [row-level source ledger](../../../modules/base/data/sources/2001/world_conflicts_treaties_2001.tsv) cite the U.S. State Department's [Treaties in Force 2001](https://1997-2001.state.gov/www/global/legal_affairs/tif_01d.pdf), the [Manila Pact text](https://treaties.un.org/doc/publication/unts/volume%20209/volume-209-i-2819-english.pdf), and conflict-specific UN and historical records.
- [UNDP Human Development Report 2003](https://hdr.undp.org/system/files/documents/human-development-report-2003-english.human-development-report-2003-english) publishes the 2001 HDI values and methodology used for 16 countries without a 2025-series value; the [2025 technical notes](https://hdr.undp.org/sites/default/files/2025_HDR/HDR25_Technical_Notes.pdf) describe the current component formula used for labeled estimates.
- [Kosovo HDR 2002](https://hdr.undp.org/system/files/documents/khdr2002.pdf), Taiwan's [Executive Yuan statistical report](https://ws.ndc.gov.tw/Download.ashx?icon=.pdf&n=5LiK56%2BHX%2BesrOS6jOeroF8g5ZyL5YWn57i96auU55m85bGV55Kw5aKDICgxNjg4IEspLnBkZg%3D%3D&u=LzAwMS9hZG1pbmlzdHJhdG9yLzEwL3JlbGZpbGUvMC8yMzQvMDAwMDc0MF80LnBkZg%3D%3D), and the [Puerto Rico Planning Board 2003 diagnosis](https://gis.jp.pr.gov/Externo_Econ/Programa%20de%20Planificaci%C3%B3n%20Econ%C3%B3mica%20y%20Social/2003.12-PR_2025_Diagnostico_%28Dic-2003%29.pdf) inform clearly labeled HDI proxies; they are not all comparable 2001 observations.
- [CIA World Factbook 2001](https://www.gutenberg.org/ebooks/27638) supplies country language descriptions and Antarctica's reported absence of indigenous inhabitants and multinational seasonal research-station population. This context does not establish uniform or national language population shares.
- Supplemental language context records retain their narrower scope in `country_languages_supplemental_context_2001.tsv`: [UNMIK Administrative Direction 2000/16](https://unmik.unmissions.org/sites/default/files/regulations/02english/E2000ads/ADE2000_16.htm), [Montenegro's 1992 Constitution](https://rm.coe.int/168008b14a), [the Federal Republic of Yugoslavia's 1992 Constitution](https://www.refworld.org/legal/legislation/natlegbod/1992/20809), the [April 2001 Sudan assessment](https://www.ecoi.net/en/file/local/1302675/1329_1200641528_sudan-april-2001.pdf), and the [U.S. State Department's 2001 East Timor report](https://www.refworld.org/reference/annualreport/usdos/2002/en/25902). These describe administrative/legal or regional context, not language-share totals.
- [CIA World Factbook 2001](https://www.gutenberg.org/ebooks/27638) supplies the separate party and leader text shown by the read-only Country Information roster; its source manifest and per-country coverage ledger are stored alongside the imported records. It does not supply comparable support or ruling-party data.
- Separate election-context party records remain in `country_party_roster_supplemental_2001.tsv`. Certified results in `country_election_results_2001.tsv` and the read-only Country Information results section cover Kosovo, Montenegro, Timor-Leste, and Serbia; their source notes distinguish event dates, result dates, territory, turnout, vote totals, shares, and seat scopes as reported. Sources include [OSCE and Kosovo Central Election Commission final results](https://omik.osce.org/kosovo/54021), [Montenegro's OSCE/ODIHR election report](https://www.osce.org/files/f/documents/a/2/15168.pdf), [UNTAET East Timor Constituent Assembly results](https://peacekeeping.un.org/sites/default/files/past/etimor/DB/db060901.htm), and [the Serbian National Assembly's post-war election records](https://www.parlament.gov.rs/national-assembly/history/after-second-world-war.534.html). These dated results do not create current gameplay party support or status.
"""
    REPORT_PATH.write_text(report, encoding="utf-8", newline="\n")


def main() -> None:
    inventory, display_statuses, interaction_statuses = enrich_inventory()
    write_report(inventory, display_statuses, interaction_statuses)
    print(
        f"Updated {len(inventory)} interface entries; "
        f"{sum(display_statuses.values())} display contracts and "
        f"{sum(interaction_statuses.values())} interaction contracts."
    )


if __name__ == "__main__":
    main()
