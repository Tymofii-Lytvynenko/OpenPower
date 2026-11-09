from __future__ import annotations

import polars as pl

from modules.base.systems.military.production_policy import (
    _capacity_frame,
    _integer,
    _number,
    _tag,
    annual_production_capacity_frame,
    initialize_production_order_work,
)


def test_capacity_frame_handles_missing_country_data():
    assert annual_production_capacity_frame(None).is_empty()
    assert annual_production_capacity_frame(pl.DataFrame({"id": ["AAA"]})).is_empty()


def test_order_work_initialization_without_designs_or_design_ids():
    orders = pl.DataFrame(
        {
            "work_required": [0.0],
            "unit_cost": [0.0],
            "quantity": [2],
            "progress": [0.0],
            "remaining_work": [0.0],
        }
    )

    result = initialize_production_order_work(orders, None)

    assert result.item(0, "unit_cost") == 0.0
    assert result.item(0, "work_required") == 0.0


def test_capacity_frame_accepts_alternate_keys_and_rejects_incomplete_tables():
    alternate = _capacity_frame(
        pl.DataFrame({"country_id": ["AAA"], "annual_capacity": [12.0]})
    )
    assert alternate.columns == ["_country", "_annual_capacity"]
    assert alternate.item(0, "_annual_capacity") == 12.0
    assert _capacity_frame(pl.DataFrame({"unknown": ["AAA"]})).is_empty()
    assert _capacity_frame(pl.DataFrame({"country_id": ["AAA"]})).is_empty()
    assert _capacity_frame({}).is_empty()


def test_scalar_normalizers_handle_invalid_and_nonfinite_values():
    assert _tag(" aaa ") == "AAA"
    assert _tag(None) == ""
    assert _integer("4") == 4
    assert _integer(object(), default=7) == 7
    assert _integer(float("inf"), default=9) == 9
    assert _number(object()) == 0.0
