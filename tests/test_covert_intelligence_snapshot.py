import math
from types import SimpleNamespace

import polars as pl

from modules.base.systems.military.covert_intelligence_snapshot import (
    IntelligenceSnapshotServices,
    build_intelligence_snapshot,
    target_regional_telecom_capacity,
)


def _services():
    def finite_number(value):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        return number if math.isfinite(number) else 0.0

    def table_value_by_key(frame, key_column, key, value_column, default=None):
        if frame is None or not {key_column, value_column}.issubset(frame.columns):
            return default
        match = frame.filter(pl.col(key_column).str.to_uppercase() == str(key).upper())
        return match.get_column(value_column)[0] if not match.is_empty() else default

    def metric_value(frame, value_column, **keys):
        filters = [pl.col(column) == value for column, value in keys.items()]
        match = frame.filter(pl.all_horizontal(filters)).get_column(value_column)
        return match[0] if len(match) else 0

    return IntelligenceSnapshotServices(
        normalize_tag=lambda value: str(value or "").strip().upper(),
        finite_number=finite_number,
        table_value_by_key=table_value_by_key,
        metric_value=metric_value,
        country_population=lambda _state, _country_id: 0.0,
    )


def test_government_snapshot_uses_population_metrics_and_bounds_estimates():
    state = SimpleNamespace(
        tables={
            "country_governments": pl.DataFrame(
                {"country_id": ["CAN"], "government_type": ["democracy"]}
            ),
            "country_laws": pl.DataFrame(
                {"country_id": ["CAN", "CAN", "CAN"], "law_id": ["a", "b", "c"]}
            ),
        }
    )
    population_metrics = pl.DataFrame(
        {"country_id": ["CAN", "USA"], "population": [123.0, 900.0]}
    )

    snapshot = build_intelligence_snapshot(
        state,
        {"id": "can", "gdp": -4, "budget_research_ratio": 1.7},
        "civilian_espionage",
        0.75,
        None,
        population_metrics,
        services=_services(),
    )

    assert snapshot == {
        "government_estimate": "democracy",
        "economic_output_estimate": 0.0,
        "population_estimate": 123.0,
        "budget_research_ratio_estimate": 1.0,
        "law_ids": ["a", "b", "c"],
        "confidence": 0.75,
    }


def test_regional_telecom_defaults_when_regions_are_unavailable():
    state = SimpleNamespace(tables={})

    capacity = target_regional_telecom_capacity(
        state,
        {"id": "cell-1"},
        {"id": "CAN"},
        services=_services(),
    )

    assert capacity == 1.0


def test_military_snapshot_without_design_or_weapon_tables_keeps_unit_estimates():
    state = SimpleNamespace(
        tables={
            "units": pl.DataFrame(
                {
                    "owner": ["CAN"],
                    "design_id": ["unknown-design"],
                    "unit_type": ["infantry"],
                    "readiness_status": ["ready"],
                }
            )
        }
    )

    snapshot = build_intelligence_snapshot(
        state,
        {"id": "can"},
        "military_espionage",
        0.8,
        None,
        None,
        services=_services(),
    )

    assert snapshot["unit_count_estimate"] == 1
    assert sum(snapshot["unit_role_count_estimates"].values()) == 1
    assert snapshot["strategic_weapon_quantity_estimate"] == 0
