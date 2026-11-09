from types import SimpleNamespace

import polars as pl

from src.client.ui.panels.military.production_snapshot import capacity_ratio, working_age_population


def test_capacity_uses_country_orders_and_clamps_allocation():
    state = SimpleNamespace(tables={
        "countries": pl.DataFrame([{"id": "AAA", "annual_production_capacity": 100.0}]),
        "production_orders": pl.DataFrame([
            {"country_id": "AAA", "assigned_capacity": 30.0},
            {"country_id": "BBB", "assigned_capacity": 90.0},
        ]),
    })
    assert capacity_ratio(state, "AAA") == 0.3
    state.tables["production_orders"] = pl.DataFrame([
        {"country_id": "AAA", "assigned_capacity": 150.0},
    ])
    assert capacity_ratio(state, "AAA") == 1.0
    assert capacity_ratio(state, "BBB") is None


def test_workforce_prefers_country_value_and_falls_back_to_owned_regions():
    state = SimpleNamespace(tables={
        "countries": pl.DataFrame([{"id": "AAA", "total_core_manpower": 42.0}]),
        "regions": pl.DataFrame([
            {"owner": "AAA", "pop_15_64": 20.0},
            {"owner": "BBB", "pop_15_64": 100.0},
        ]),
    })
    assert working_age_population(state, "AAA") == 42
    state.tables.pop("countries")
    assert working_age_population(state, "AAA") == 20
    state.tables.pop("regions")
    assert working_age_population(state, "AAA") is None


def test_capacity_ratio_handles_missing_data_and_legacy_capacity_fallback():
    assert capacity_ratio(SimpleNamespace(tables={}), "AAA") is None

    state = SimpleNamespace(
        tables={
            "countries": pl.DataFrame(
                [
                    {
                        "id": "AAA",
                        "annual_production_capacity": None,
                        "military_production_capacity": 40.0,
                    }
                ]
            ),
            "production_orders": pl.DataFrame(
                [{"country_id": "AAA", "assigned_capacity": 10.0}]
            ),
        }
    )

    assert capacity_ratio(state, "AAA") == 0.25


def test_capacity_ratio_rejects_invalid_and_nonpositive_capacity():
    orders = pl.DataFrame(schema={"country_id": pl.String, "assigned_capacity": pl.Float64})
    invalid = SimpleNamespace(
        tables={
            "countries": pl.DataFrame(
                {"id": ["AAA"], "annual_production_capacity": ["invalid"]}
            ),
            "production_orders": orders,
        }
    )
    nonpositive = SimpleNamespace(
        tables={
            "countries": pl.DataFrame(
                {"id": ["AAA"], "annual_production_capacity": [0.0]}
            ),
            "production_orders": orders,
        }
    )

    assert capacity_ratio(invalid, "AAA") is None
    assert capacity_ratio(nonpositive, "AAA") is None
