from __future__ import annotations

import polars as pl

from src.shared.schema import ColumnSpec, TableSchema


ENERGY_CRISIS_SCHEMA = TableSchema(
    name="energy_crises",
    columns={
        "country_id": ColumnSpec(pl.Utf8, ""),
        "policy": ColumnSpec(pl.Utf8, "market"),
        "reserve_days": ColumnSpec(pl.Float64, 90.0),
        "import_dependency": ColumnSpec(pl.Float64, 0.5),
        "shock_intensity": ColumnSpec(pl.Float64, 0.0),
        "response_level": ColumnSpec(pl.Float64, 0.0),
        "stress_index": ColumnSpec(pl.Float64, 0.0),
        "economic_drag": ColumnSpec(pl.Float64, 0.0),
    },
    key_columns=("country_id",),
    owner="energy_crisis",
    preserve_extra_columns=False,
)

COUNTRY_ENERGY_SCHEMA = TableSchema(
    name="countries",
    columns={
        "id": ColumnSpec(pl.Utf8, ""),
        "energy_security_index": ColumnSpec(pl.Float64, 1.0),
        "energy_economic_drag": ColumnSpec(pl.Float64, 0.0),
    },
    key_columns=("id",),
    owner="energy_crisis",
    preserve_extra_columns=True,
)

ENERGY_CRISIS_SCHEMAS = (
    ENERGY_CRISIS_SCHEMA,
    COUNTRY_ENERGY_SCHEMA,
)
