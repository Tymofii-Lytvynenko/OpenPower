"""Generate the low-confidence 2001 unit-research capability proxy."""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COUNTRY_DIR = ROOT / "modules" / "base" / "data" / "countries"
HISTORICAL_PATH = COUNTRY_DIR / "countries_historical.tsv"
DEVELOPMENT_PATH = COUNTRY_DIR / "countries_dem.tsv"
ECONOMY_PATH = COUNTRY_DIR / "countries_eco.tsv"
COUNTRY_LIST_PATH = COUNTRY_DIR / "countries.tsv"
OUTPUT_PATH = COUNTRY_DIR / "countries_unit_research_2001.tsv"

# These floors reproduce the characteristic scaling in BootstrapSystem.
CHARACTERISTIC_FLOORS = {
    "gun_range": 0.75,
    "gun_precision": 0.50,
    "gun_damage": 0.70,
    "missile_range": 0.65,
    "missile_precision": 0.50,
    "missile_damage": 0.70,
    "missile_payload": 0.80,
    "speed": 0.75,
    "sensors": 0.55,
    "armor": 0.80,
    "stealth": 0.70,
    "countermeasures": 0.50,
}


def read_tsv(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            row["id"].strip().upper(): row
            for row in csv.DictReader(handle, delimiter="\t")
            if row.get("id", "").strip()
        }


def number(value: str | None, default: float) -> tuple[float, bool]:
    try:
        parsed = float(value or "")
    except (TypeError, ValueError, OverflowError):
        return default, False
    return parsed, True


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def build_rows() -> list[dict[str, str]]:
    countries = read_tsv(COUNTRY_LIST_PATH)
    historical = read_tsv(HISTORICAL_PATH)
    development = read_tsv(DEVELOPMENT_PATH)
    economy = read_tsv(ECONOMY_PATH)

    columns = [
        "id",
        "research_technology_index_2001",
        *(f"research_characteristic_{name}_factor_2001" for name in CHARACTERISTIC_FLOORS),
        "research_model_confidence_2001",
        "research_model_hdi_source_2001",
        "research_model_budget_source_2001",
        "research_model_definition_2001",
    ]
    rows: list[dict[str, str]] = []

    for country_id in sorted(countries):
        historical_row = historical.get(country_id, {})
        development_row = development.get(country_id, {})
        economy_row = economy.get(country_id, {})
        hdi, hdi_available = number(
            historical_row.get("reference_human_dev"), float("nan")
        )
        hdi_status = historical_row.get("reference_human_dev_status", "").strip()
        if not hdi_available:
            hdi, hdi_available = number(development_row.get("human_dev"), 0.45)

        research_budget, budget_available = number(
            economy_row.get("budget_research_ratio"), 0.10
        )
        hdi = clamp(hdi, 0.0, 1.0)
        research_budget = clamp(research_budget, 0.0, 1.0)

        # Keep the starting national index aligned with the existing scenario model.
        technology_index = clamp(0.45 + (hdi * 0.50) + (research_budget * 0.10), 0.35, 0.98)
        row = {
            "id": country_id,
            "research_technology_index_2001": f"{technology_index:.3f}",
            "research_model_confidence_2001": "low",
            "research_model_hdi_source_2001": (
                f"historical_{hdi_status}"
                if hdi_available and hdi_status
                else "historical_score_source_unspecified"
                if hdi_available and historical_row.get("reference_human_dev", "").strip()
                else f"neutral_simulation_fallback_{hdi_status}"
                if hdi_status in {"not_applicable", "not_reported"}
                else "country_development_input_fallback"
                if hdi_available
                else "default_HDI_proxy_0.45"
            ),
            "research_model_budget_source_2001": (
                "OpenPower_scenario_budget_input_not_historical_RnD"
                if budget_available
                else "default_budget_proxy_0.10"
            ),
            "research_model_definition_2001": "bootstrap_capability_scaling_v1",
        }
        for characteristic, floor in CHARACTERISTIC_FLOORS.items():
            factor = floor + technology_index * (1.0 - floor)
            row[f"research_characteristic_{characteristic}_factor_2001"] = f"{factor:.3f}"
        rows.append({column: row[column] for column in columns})

    return rows


def main() -> None:
    rows = build_rows()
    columns = list(rows[0]) if rows else []
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} country research baselines to {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
