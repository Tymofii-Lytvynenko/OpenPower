from __future__ import annotations

import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = (
    ROOT
    / "modules"
    / "base"
    / "data"
    / "sources"
    / "2001"
    / "military_personnel_gameplay_estimates_2001.tsv"
)
OUTPUT_PATH = (
    ROOT
    / "modules"
    / "base"
    / "data"
    / "countries"
    / "countries_military_personnel_gameplay_estimates_2001.tsv"
)
EXPECTED_IDS = frozenset(
    {"AFG", "KOS", "MCO", "MNE", "PRI", "PSE", "SLB", "SMR", "SOM"}
)
FIELDNAMES = (
    "id",
    "gameplay_military_personnel_estimate_2001",
    "gameplay_military_personnel_estimate_2001_available",
    "gameplay_military_personnel_estimate_2001_kind",
    "gameplay_military_personnel_estimate_2001_quality",
    "gameplay_military_personnel_estimate_2001_population",
    "gameplay_military_personnel_estimate_2001_population_method",
    "gameplay_military_personnel_estimate_2001_rate_per_1000",
    "gameplay_military_personnel_estimate_2001_peer_group",
    "gameplay_military_personnel_estimate_2001_peer_iso3s",
    "gameplay_military_personnel_estimate_2001_peer_count",
    "gameplay_military_personnel_estimate_2001_rate_method",
    "gameplay_military_personnel_estimate_2001_source_release",
    "gameplay_military_personnel_estimate_2001_population_source_reference",
    "gameplay_military_personnel_estimate_2001_population_source_url",
    "gameplay_military_personnel_estimate_2001_military_source_reference",
    "gameplay_military_personnel_estimate_2001_military_source_url",
    "gameplay_military_personnel_estimate_2001_display_label",
    "gameplay_military_personnel_estimate_2001_note",
)
_FIELD_MAP = {
    "gameplay_military_personnel_estimate_2001": "gameplay_personnel_estimate",
    "gameplay_military_personnel_estimate_2001_kind": "estimate_kind",
    "gameplay_military_personnel_estimate_2001_quality": "quality_label",
    "gameplay_military_personnel_estimate_2001_population": "population_2001",
    "gameplay_military_personnel_estimate_2001_population_method": "population_method",
    "gameplay_military_personnel_estimate_2001_rate_per_1000": "regional_service_rate_per_1000",
    "gameplay_military_personnel_estimate_2001_peer_group": "peer_group",
    "gameplay_military_personnel_estimate_2001_peer_iso3s": "peer_iso3s",
    "gameplay_military_personnel_estimate_2001_peer_count": "peer_count",
    "gameplay_military_personnel_estimate_2001_rate_method": "rate_method",
    "gameplay_military_personnel_estimate_2001_source_release": "military_source_release",
    "gameplay_military_personnel_estimate_2001_population_source_reference": "population_source_reference",
    "gameplay_military_personnel_estimate_2001_population_source_url": "population_source_url",
    "gameplay_military_personnel_estimate_2001_military_source_reference": "military_source_reference",
    "gameplay_military_personnel_estimate_2001_military_source_url": "military_source_url",
    "gameplay_military_personnel_estimate_2001_display_label": "display_label",
    "gameplay_military_personnel_estimate_2001_note": "note",
}
_REQUIRED_NONFACTUAL_FIELDS = {
    "scenario_year": "2001",
    "unit": "people",
    "historical_observation": "no",
    "factual_active_personnel_eligible": "no",
    "import_target": "none",
    "display_label": "Gameplay estimate — not a historical count",
}


def build_extension_rows(source_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Convert the source ledger into a unique-key runtime extension."""
    by_id: dict[str, dict[str, str]] = {}
    for source_row in source_rows:
        country_id = source_row.get("country_id", "").strip().upper()
        if country_id in by_id:
            raise ValueError(f"Duplicate gameplay personnel estimate for {country_id}.")
        if country_id not in EXPECTED_IDS:
            raise ValueError(
                f"Unexpected gameplay personnel estimate ID: {country_id!r}."
            )
        for field, expected in _REQUIRED_NONFACTUAL_FIELDS.items():
            if source_row.get(field, "").strip() != expected:
                raise ValueError(
                    f"{country_id} has invalid {field}: {source_row.get(field)!r}; "
                    f"expected {expected!r}."
                )
        try:
            estimate = int(source_row.get("gameplay_personnel_estimate", ""))
            population = int(source_row.get("population_2001", ""))
            rate = float(source_row.get("regional_service_rate_per_1000", ""))
            peer_count = int(source_row.get("peer_count", ""))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                f"{country_id} has an invalid numeric gameplay estimate input."
            ) from exc
        if estimate <= 0 or population <= 0 or rate <= 0 or peer_count <= 0:
            raise ValueError(
                f"{country_id} must have positive estimate and peer inputs."
            )
        if source_row.get("quality_label", "").strip() not in {"low", "very_low"}:
            raise ValueError(
                f"{country_id} must retain a low or very-low quality label."
            )

        output_row = {
            "id": country_id,
            "gameplay_military_personnel_estimate_2001_available": "true",
        }
        output_row.update(
            {
                target_field: source_row.get(source_field, "").strip()
                for target_field, source_field in _FIELD_MAP.items()
            }
        )
        by_id[country_id] = output_row

    if set(by_id) != EXPECTED_IDS:
        missing = ", ".join(sorted(EXPECTED_IDS - set(by_id)))
        extra = ", ".join(sorted(set(by_id) - EXPECTED_IDS))
        raise ValueError(
            f"Gameplay personnel estimate coverage mismatch; missing={missing}; extra={extra}."
        )
    return [by_id[country_id] for country_id in sorted(by_id)]


def render_tsv(rows: list[dict[str, str]]) -> str:
    from io import StringIO

    buffer = StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=FIELDNAMES, delimiter="\t", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the 2001 military personnel gameplay estimate extension."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the checked-in extension is stale.",
    )
    args = parser.parse_args()

    with SOURCE_PATH.open(encoding="utf-8-sig", newline="") as source_file:
        rows = build_extension_rows(list(csv.DictReader(source_file, delimiter="\t")))
    output = render_tsv(rows)
    if args.check:
        current = (
            OUTPUT_PATH.read_text(encoding="utf-8-sig") if OUTPUT_PATH.exists() else ""
        )
        if current != output:
            raise SystemExit(f"Generated file is stale: {OUTPUT_PATH}")
        print(f"Verified {len(rows)} unique 2001 gameplay estimate country rows.")
        return

    OUTPUT_PATH.write_text(output, encoding="utf-8", newline="")
    print(
        f"Generated {len(rows)} unique 2001 gameplay estimate country rows at {OUTPUT_PATH}."
    )


if __name__ == "__main__":
    main()
