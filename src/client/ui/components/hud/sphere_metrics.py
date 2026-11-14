"""OpenPower-native values shown by the Main Bar sphere meters."""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import polars as pl

from src.client.services.client_presentation import contribution_for
from src.shared.mod_api import ClientPresentationKeys


@dataclass(frozen=True, slots=True)
class SphereMetric:
    label: str
    value: float | None


def main_bar_sphere_metrics(state, country_tag: str) -> dict[str, SphereMetric]:
    """Resolve displayed values for the selected country without source-formula guesses."""
    tables = getattr(state, "tables", {})
    countries = tables.get("countries") if isinstance(tables, Mapping) else None
    country = _country_row(countries, country_tag)
    units = tables.get("units") if isinstance(tables, Mapping) else None

    return {
        "frmMeterPolitic": SphereMetric(
            "Government approval", _bounded(country.get("gvt_approval"), 0.0, 100.0)
        ),
        "frmMeterMilitary": SphereMetric(
            "Ready or fortified military units",
            _ready_unit_share(state, units, country_tag),
        ),
        "frmMeterEconomic": SphereMetric(
            "Economic health", _scaled_index(country.get("economic_health"))
        ),
    }


def _country_row(countries: pl.DataFrame | None, country_tag: str) -> dict:
    if countries is None or "id" not in countries.columns:
        return {}
    rows = countries.filter(pl.col("id").cast(pl.Utf8) == str(country_tag))
    return rows.to_dicts()[0] if not rows.is_empty() else {}


def _ready_unit_share(state, units: pl.DataFrame | None, country_tag: str) -> float | None:
    if units is None or "owner" not in units.columns or "readiness_status" not in units.columns:
        return None
    owned = units.filter(pl.col("owner").cast(pl.Utf8) == str(country_tag))
    if owned.is_empty():
        return 0.0

    policy = contribution_for(
        state,
        ClientPresentationKeys.READINESS_POLICY_FACTORY,
    )()
    statuses = owned.get_column("readiness_status").to_list()
    ready = sum(
        policy.normalize(status) != "parked"
        for status in statuses
    )
    return ready * 100.0 / len(statuses)


def _scaled_index(value: object) -> float | None:
    normalized = _bounded(value, 0.0, 1.0)
    return normalized * 100.0 if normalized is not None else None


def _bounded(value: object, minimum: float, maximum: float) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return min(maximum, max(minimum, number))
