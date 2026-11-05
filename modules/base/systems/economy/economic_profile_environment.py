from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol

import polars as pl

from modules.base.systems.economy.economic_health_policy import EconomicProfileEnvironment
from modules.base.systems.world.random_event_effects import aggregate_active_effects


@dataclass(frozen=True)
class EconomicProfileEnvironmentInputs:
    now: int
    random_event_effects: pl.DataFrame | None
    regions: pl.DataFrame | None
    resource_ledger: pl.DataFrame | None


class EconomicProfileEnvironmentCalculator(Protocol):
    def calculate(self, inputs: EconomicProfileEnvironmentInputs) -> EconomicProfileEnvironment: ...


class DeterministicEconomicProfileEnvironmentCalculator:
    def calculate(self, inputs: EconomicProfileEnvironmentInputs) -> EconomicProfileEnvironment:
        country_effects = aggregate_active_effects(
            inputs.random_event_effects,
            inputs.now,
            categories={"labour", "employment"},
            subject_type="country",
        )
        health_effect_by_country = self._health_effect_by_country(inputs)
        labor_by_country = self._labor_supply_by_country(inputs.regions)
        shortage_by_country = self._resource_shortage_by_country(inputs.resource_ledger)
        return EconomicProfileEnvironment(
            country_effects=country_effects,
            health_effect_by_country=health_effect_by_country,
            labor_by_country=labor_by_country,
            shortage_by_country=shortage_by_country,
        )

    def _health_effect_by_country(
        self,
        inputs: EconomicProfileEnvironmentInputs,
    ) -> dict[str, float]:
        regional_health_effects = aggregate_active_effects(
            inputs.random_event_effects,
            inputs.now,
            categories={"health"},
            subject_type="region",
        )
        regions = inputs.regions
        region_owners = {}
        if regions is not None and {"id", "owner"}.issubset(regions.columns):
            region_owners = {
                str(row.get("id")): str(row.get("owner") or "").strip().upper()
                for row in regions.select("id", "owner").iter_rows(named=True)
            }
        health_effect_by_country: dict[str, float] = {}
        for (_, region_id, _), magnitude in regional_health_effects.items():
            owner = region_owners.get(region_id, "")
            if owner:
                health_effect_by_country[owner] = (
                    health_effect_by_country.get(owner, 0.0) + magnitude
                )
        return health_effect_by_country

    def _labor_supply_by_country(
        self,
        regions: pl.DataFrame | None,
    ) -> dict[str, float]:
        if regions is None or not {"owner", "pop_15_64"}.issubset(regions.columns):
            return {}
        return {
            str(row["owner"]): max(0.0, _finite_number(row["labor_supply"]))
            for row in regions.group_by("owner").agg(
                pl.col("pop_15_64").fill_null(0).sum().alias("labor_supply")
            ).iter_rows(named=True)
        }

    def _resource_shortage_by_country(
        self,
        ledger: pl.DataFrame | None,
    ) -> dict[str, float]:
        if ledger is None or not {
            "country_id",
            "balance_usd",
            "consumption_usd",
        }.issubset(ledger.columns):
            return {}
        shortage = ledger.group_by("country_id").agg(
            pl.col("balance_usd").filter(pl.col("balance_usd") < 0).abs().sum().alias("shortage"),
            pl.col("consumption_usd").sum().alias("demand"),
        )
        return {
            str(row["country_id"]): _bounded_number(
                _finite_number(row["shortage"]) / max(1.0, _finite_number(row["demand"])),
                0.0,
                1.0,
            )
            for row in shortage.iter_rows(named=True)
        }


def _finite_number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _bounded_number(value: Any, minimum: float, maximum: float, default: float = 0.0) -> float:
    return min(max(_finite_number(value, default), minimum), maximum)
