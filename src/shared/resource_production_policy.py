"""Shared estimates for the resource production increase command."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import polars as pl

from src.shared.economy_meta import RESOURCE_MAPPING


PRODUCTION_INCREASE_PERCENTAGES = (1, 2, 5, 10, 25)


@dataclass(frozen=True)
class ProductionIncreaseBasis:
    """The output value OpenPower can safely increase for a country/resource."""

    source: str
    annual_value_usd: float
    regional_row_ids: tuple[str, ...] = ()


def production_increase_basis(
    state: Any,
    country_tag: str,
    resource_id: str,
) -> ProductionIncreaseBasis | None:
    """Prefer explicit controlled regional data and otherwise use national output."""

    country = str(country_tag or "").strip().upper()
    resource = str(resource_id or "").strip().lower()
    if not country or resource not in RESOURCE_MAPPING:
        return None

    tables = getattr(state, "tables", {})
    national = tables.get("domestic_production")
    required_national = {"country_id", "game_resource_id", "domestic_production"}
    if national is None or not required_national.issubset(national.columns):
        return None

    national_rows = national.filter(
        (pl.col("country_id").cast(pl.Utf8, strict=False).str.strip_chars().str.to_uppercase() == country)
        & (pl.col("game_resource_id").cast(pl.Utf8, strict=False).str.strip_chars().str.to_lowercase() == resource)
    )
    if national_rows.height != 1:
        return None
    national_value = _finite_nonnegative(national_rows["domestic_production"][0])
    if national_value is None or national_value <= 0.0:
        return None

    regional = tables.get("regional_production")
    if regional is None or regional.is_empty():
        return ProductionIncreaseBasis("national", national_value)
    required_regional = {
        "id", "country_id", "region_id", "game_resource_id", "domestic_production",
    }
    if not required_regional.issubset(regional.columns):
        return ProductionIncreaseBasis("national", national_value)

    resource_rows = regional.filter(
        (pl.col("country_id").cast(pl.Utf8, strict=False).str.strip_chars().str.to_uppercase() == country)
        & (pl.col("game_resource_id").cast(pl.Utf8, strict=False).str.strip_chars().str.to_lowercase() == resource)
    )
    if resource_rows.is_empty():
        return ProductionIncreaseBasis("national", national_value)

    regions = tables.get("regions")
    if regions is None or not {"id", "owner"}.issubset(regions.columns):
        return None

    control_by_region: dict[int, str] = {}
    for row in regions.iter_rows(named=True):
        try:
            region_id = int(row["id"])
        except (TypeError, ValueError, OverflowError):
            continue
        controller = str(row.get("controller") or row.get("owner") or "").strip().upper()
        control_by_region[region_id] = controller

    eligible: list[tuple[str, float]] = []
    for row in resource_rows.iter_rows(named=True):
        try:
            region_id = int(row["region_id"])
        except (TypeError, ValueError, OverflowError):
            continue
        if control_by_region.get(region_id) != country:
            continue
        row_id = str(row.get("id") or "").strip()
        amount = _finite_nonnegative(row.get("domestic_production"))
        if not row_id or amount is None:
            return None
        eligible.append((row_id, amount))

    if not eligible:
        return None
    row_ids = tuple(row_id for row_id, _ in eligible)
    if len(set(row_ids)) != len(row_ids):
        return None
    annual_value = math.fsum(amount for _, amount in eligible)
    if not math.isfinite(annual_value) or annual_value <= 0.0:
        return None
    return ProductionIncreaseBasis("regional", annual_value, row_ids)


def estimate_production_increase_cost(
    annual_value_usd: float,
    increase_percent: int,
) -> float | None:
    """Price expansion at one year of its added annual output value in OpenPower."""

    if type(increase_percent) is not int or increase_percent not in PRODUCTION_INCREASE_PERCENTAGES:
        return None
    annual_value = _finite_nonnegative(annual_value_usd)
    if annual_value is None or annual_value <= 0.0:
        return None
    # Resource production and money are already expressed on the same USD-value scale.
    cost = round(annual_value * increase_percent / 100.0, 2)
    return cost if math.isfinite(cost) and cost > 0.0 else None


def _finite_nonnegative(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0.0 else None
