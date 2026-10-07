"""Deterministic production-capacity calculations independent of game state."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable


DEFAULT_PRODUCTION_COEFFICIENT = 48.0
_DAYS_PER_YEAR = 365.25
_TERMINAL_ORDER_STATES = {"cancelled", "completed", "delivered", "awaiting_deployment"}


def annual_production_capacity(
    national_output: Any,
    economic_health: Any,
    coefficient: Any = DEFAULT_PRODUCTION_COEFFICIENT,
) -> float:
    """Return output × bounded health × configured production coefficient."""

    output = _finite_nonnegative(national_output)
    health = min(1.0, max(0.0, _finite_nonnegative(economic_health)))
    scale = _finite_nonnegative(coefficient)
    return output * health * scale


def allocate_production_capacity(
    orders: Iterable[dict[str, Any]],
    annual_capacity_by_country: dict[str, float],
    elapsed_year_fraction: float,
    allocation_policy: str = "priority",
) -> list[dict[str, Any]]:
    """Allocate this update's capacity, preserving queue progress and order."""

    rows = [dict(row) for row in orders]
    by_country: dict[str, list[int]] = defaultdict(list)
    for original_index, row in enumerate(rows):
        country = _tag(row.get("country_id"))
        if country:
            by_country[country].append(original_index)

    elapsed = _finite_nonnegative(elapsed_year_fraction)
    proportional = str(allocation_policy or "priority").strip().lower() == "proportional"
    terminal_states = _TERMINAL_ORDER_STATES
    for country, indexes in by_country.items():
        annual_capacity = _finite_nonnegative(annual_capacity_by_country.get(country, 0.0))
        update_capacity = annual_capacity * elapsed
        queued = [
            index
            for index in indexes
            if str(rows[index].get("status") or "queued").strip().lower() not in terminal_states
            and str(rows[index].get("status") or "queued").strip().lower() != "paused"
        ]
        queued.sort(
            key=lambda index: (
                -max(1, _integer(rows[index].get("priority"), 1)),
                str(rows[index].get("id") or ""),
                index,
            )
        )

        def remaining_work(index: int) -> float:
            row = rows[index]
            required = _finite_nonnegative(row.get("work_required"))
            remaining = row.get("remaining_work")
            if remaining is None or _finite_nonnegative(remaining) == 0.0 and _number(row.get("progress")) < 1.0:
                amount = required * (1.0 - min(1.0, max(0.0, _number(row.get("progress")))))
            else:
                amount = _finite_nonnegative(remaining)
            return min(required, amount) if required > 0.0 else 0.0

        demand_ahead = 0.0
        if proportional and queued and annual_capacity > 0.0 and elapsed > 0.0:
            remaining_values = [remaining_work(index) for index in queued]
            demanded = sum(remaining_values)
            ratio = min(1.0, update_capacity / demanded) if demanded > 0.0 else 0.0
            allocations = zip(queued, remaining_values, strict=True)
        else:
            capacity_left = update_capacity if annual_capacity > 0.0 and elapsed > 0.0 else 0.0
            allocations = (
                (index, remaining_work(index))
                for index in queued
            )

        for index, remaining in allocations:
            row = rows[index]
            required = _finite_nonnegative(row.get("work_required"))
            if proportional:
                allocated = min(remaining, remaining * ratio) if queued and annual_capacity > 0.0 and elapsed > 0.0 else 0.0
            else:
                allocated = min(remaining, capacity_left)
                capacity_left = max(0.0, capacity_left - allocated)
            remaining_after = max(0.0, remaining - allocated)
            row["remaining_work"] = remaining_after
            row["assigned_capacity"] = allocated
            row["progress"] = 1.0 if required <= 0.0 else min(1.0, max(0.0, 1.0 - remaining_after / required))
            row["blocking_reason"] = (
                "No production capacity is available."
                if annual_capacity <= 0.0 and remaining_after > 0.0
                else "Waiting for higher-priority orders."
                if not proportional and allocated <= 0.0 and remaining_after > 0.0
                else ""
            )
            if remaining_after <= 1e-9:
                row["remaining_work"] = 0.0
                row["progress"] = 1.0
                row["status"] = "completed"
                row["eta_days"] = 0
            else:
                row["status"] = "queued"
                if annual_capacity <= 0.0:
                    row["eta_days"] = -1
                else:
                    row["eta_days"] = max(
                        1,
                        math.ceil((demand_ahead + remaining_after) / annual_capacity * _DAYS_PER_YEAR),
                    )
            demand_ahead += remaining_after

        for index in indexes:
            row = rows[index]
            if str(row.get("status") or "").strip().lower() == "paused":
                row["assigned_capacity"] = 0.0
                row["blocking_reason"] = "Order is paused."
            elif str(row.get("status") or "").strip().lower() in _TERMINAL_ORDER_STATES:
                row["assigned_capacity"] = 0.0
                if str(row.get("status") or "").strip().lower() in {"completed", "delivered"}:
                    row["blocking_reason"] = ""

    return rows


def _tag(value: Any) -> str:
    return str(value or "").strip().upper()


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _number(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return result if math.isfinite(result) else 0.0


def _finite_nonnegative(value: Any) -> float:
    return max(0.0, _number(value))
