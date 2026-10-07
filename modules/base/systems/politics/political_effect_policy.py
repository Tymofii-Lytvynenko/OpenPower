"""Shared aggregation rules for political outputs consumed by their domain owners."""

from __future__ import annotations

import math
from collections.abc import Iterable

import polars as pl


def aggregate_political_effects(
    effects: pl.DataFrame | None,
    now_minute: int,
    *,
    domain: str,
    effect: str,
) -> dict[str, float]:
    """Sum active country effects for one typed signal without changing its source rows."""

    selector = (str(domain or "").strip().casefold(), str(effect or "").strip().casefold())
    values = aggregate_political_effects_by_type(effects, now_minute, selectors={selector})
    return {
        country_id: value
        for (country_id, selected_domain, selected_effect), value in values.items()
        if (selected_domain, selected_effect) == selector
    }


def aggregate_political_effects_by_type(
    effects: pl.DataFrame | None,
    now_minute: int,
    *,
    selectors: Iterable[tuple[str, str]],
) -> dict[tuple[str, str, str], float]:
    """Aggregate a set of signals in one pass, which suits frequent dependent-system updates."""

    selected = {
        (str(domain or "").strip().casefold(), str(effect or "").strip().casefold())
        for domain, effect in selectors
    }
    if not selected or effects is None or effects.is_empty():
        return {}
    required = {
        "country_id",
        "domain",
        "effect",
        "value",
        "effective_at_minute",
        "expires_at_minute",
        "status",
    }
    if not required.issubset(effects.columns):
        return {}

    totals: dict[str, float] = {}
    for row in effects.iter_rows(named=True):
        if str(row.get("status") or "").strip().casefold() != "active":
            continue
        domain_key = str(row.get("domain") or "").strip().casefold()
        effect_key = str(row.get("effect") or "").strip().casefold()
        if (domain_key, effect_key) not in selected:
            continue
        try:
            effective_at = int(row.get("effective_at_minute") or 0)
            expires_at = int(row.get("expires_at_minute") or 0)
            value = float(row.get("value"))
        except (TypeError, ValueError, OverflowError):
            continue
        if effective_at > now_minute or (expires_at > 0 and now_minute >= expires_at):
            continue
        if not math.isfinite(value):
            continue
        country_id = str(row.get("country_id") or "").strip().upper()
        if not country_id:
            continue
        key = (country_id, domain_key, effect_key)
        totals[key] = totals.get(key, 0.0) + value
    return {
        key: min(1.0, max(-1.0, value)) for key, value in totals.items()
    }


def bounded_ratio(value: object, default: float = 0.0) -> float:
    """Normalize an optional ratio or additive effect to the inclusive 0–1 range."""

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        number = float(default)
    if not math.isfinite(number):
        number = float(default)
    return min(1.0, max(0.0, number))


def bounded_modifier(value: float, *, minimum: float = 0.5, maximum: float = 1.5) -> float:
    """Translate an additive political signal into a safe multiplicative modifier."""

    return min(maximum, max(minimum, 1.0 + float(value)))
