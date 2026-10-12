"""Persists military control separately from political ownership."""

from __future__ import annotations

from typing import Any

import polars as pl

from src.shared.events import EventNewHour
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase


OCCUPATION_SCHEMA = {
    "region_id": pl.Int32,
    "controller_country_id": pl.Utf8,
    "garrison_strength": pl.Int64,
    "resistance": pl.Float64,
    "occupation_status": pl.Utf8,
    "started_at_minute": pl.Int64,
    "updated_at_minute": pl.Int64,
    "contested": pl.Boolean,
}


class OccupationSystem(ISystem):
    """Maintains occupation rows after combat has selected a controller."""

    access = SystemAccess(
        reads=frozenset({"regions", "units", "occupations", "countries_wars"}),
        writes=frozenset({"regions", "occupations"}),
        phase=SystemPhase.POST_PROCESS,
    )

    @property
    def id(self) -> str:
        return "base.occupation"

    @property
    def dependencies(self) -> list[str]:
        return ["base.combat"]

    def update(self, state: GameState, delta_time: float) -> None:
        regions = state.tables.get("regions")
        units = state.tables.get("units")
        if regions is None or units is None:
            self._update_table_if_changed(
                state,
                "occupations",
                pl.DataFrame(schema=OCCUPATION_SCHEMA),
            )
            return
        existing = state.tables.get("occupations")
        if existing is not None and not any(isinstance(event, EventNewHour) for event in state.events):
            return
        now = int(state.time.total_minutes)
        current = existing if existing is not None else pl.DataFrame(schema=OCCUPATION_SCHEMA)
        current = current.select(
            [column for column in OCCUPATION_SCHEMA if column in current.columns]
        )
        for column, dtype in OCCUPATION_SCHEMA.items():
            if column not in current.columns:
                current = current.with_columns(pl.lit(None, dtype=dtype).alias(column))
        current = current.select(
            [
                pl.col(column).cast(dtype, strict=False).alias(column)
                for column, dtype in OCCUPATION_SCHEMA.items()
            ]
        ).with_row_index("_row_order").with_columns(pl.col("_row_order").cast(pl.Int64))

        occupied = (
            regions.with_row_index("_region_order")
            .select(
                pl.col("id").cast(pl.Int32, strict=False).fill_null(0).alias("region_id"),
                pl.col("owner").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase().alias("_owner"),
                pl.col("controller").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase().alias("controller_country_id"),
                "_region_order",
            )
            .filter(
                (pl.col("_owner") != "")
                & (pl.col("controller_country_id") != "")
                & (pl.col("controller_country_id") != pl.col("_owner"))
            )
            .drop("_owner")
        )
        # Aggregate the roster once so every occupied region does not rescan all units.
        garrisons = (
            units.filter(~pl.col("is_moving").fill_null(False))
            .select(
                pl.col("current_region_id").cast(pl.Int32, strict=False).fill_null(0).alias("region_id"),
                pl.col("owner").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase().alias("controller_country_id"),
                pl.col("strength").cast(pl.Int64, strict=False).fill_null(0).clip(lower_bound=0).alias("_strength"),
            )
            .group_by(["region_id", "controller_country_id"])
            .agg(pl.col("_strength").sum().alias("garrison_strength"))
        )
        updates = (
            occupied.join(garrisons, on=["region_id", "controller_country_id"], how="left", maintain_order="left")
            .join(
                current.select("region_id", pl.col("started_at_minute").alias("_started_at_minute")),
                on="region_id",
                how="left",
                maintain_order="left",
            )
            .with_columns(
                pl.col("garrison_strength").fill_null(0).cast(pl.Int64),
                pl.when(pl.col("_started_at_minute").is_null())
                .then(pl.lit(now))
                .otherwise(pl.col("_started_at_minute").cast(pl.Int64, strict=False))
                .alias("started_at_minute"),
                pl.lit(0.0).alias("resistance"),
                pl.when(pl.col("garrison_strength").fill_null(0) > 0)
                .then(pl.lit("active"))
                .otherwise(pl.lit("contested"))
                .alias("occupation_status"),
                pl.lit(now).cast(pl.Int64).alias("updated_at_minute"),
                (pl.col("garrison_strength").fill_null(0) <= 0).alias("contested"),
            )
            .drop("_started_at_minute")
            .join(
                current.select("region_id", "_row_order"),
                on="region_id",
                how="left",
                maintain_order="left",
            )
            .with_columns(
                pl.when(pl.col("_row_order").is_null())
                .then(pl.lit(current.height) + pl.col("_region_order"))
                .otherwise(pl.col("_row_order"))
                .cast(pl.Int64)
                .alias("_row_order")
            )
            .select([*OCCUPATION_SCHEMA, "_row_order"])
        )
        unchanged = current.join(
            updates.select("region_id").unique(),
            on="region_id",
            how="anti",
            maintain_order="left",
        ).select([*OCCUPATION_SCHEMA, "_row_order"])
        frame = (
            pl.concat([unchanged, updates], how="vertical")
            .sort("_row_order")
            .select(list(OCCUPATION_SCHEMA))
        )
        self._update_table_if_changed(state, "occupations", frame)

    def _update_table_if_changed(self, state: GameState, name: str, frame: pl.DataFrame) -> bool:
        current = state.tables.get(name)
        if current is not None and current.equals(frame):
            return False
        state.update_table(name, frame)
        return True
