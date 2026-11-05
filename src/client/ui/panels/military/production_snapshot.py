"""Read production capacity and workforce values from a world snapshot."""

import math


def nonnegative_number(value) -> float:
    try:
        number = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) and number >= 0.0 else 0.0


def capacity_ratio(state, country_tag: str) -> float | None:
    countries = state.tables.get("countries")
    orders = state.tables.get("production_orders")
    if countries is None or orders is None or "id" not in countries.columns:
        return None
    country = next((row for row in countries.to_dicts()
                    if str(row.get("id") or "").strip().upper() == country_tag), None)
    if country is None:
        return None
    denominator = country.get("annual_production_capacity")
    if denominator is None:
        denominator = country.get("military_production_capacity")
    try:
        capacity = float(denominator)
    except (TypeError, ValueError):
        return None
    if not (capacity > 0.0):
        return None
    assigned = 0.0
    if {"country_id", "assigned_capacity"}.issubset(orders.columns):
        assigned = sum(
            max(0.0, nonnegative_number(row.get("assigned_capacity")))
            for row in orders.to_dicts()
            if str(row.get("country_id") or "").strip().upper() == country_tag
        )
    return max(0.0, min(1.0, assigned / capacity))


def working_age_population(state, country_tag: str) -> int | None:
    countries = state.tables.get("countries")
    if countries is not None and {"id", "total_core_manpower"}.issubset(countries.columns):
        row = next((item for item in countries.to_dicts()
                    if str(item.get("id") or "").strip().upper() == country_tag), None)
        if row is not None and row.get("total_core_manpower") is not None:
            return int(round(nonnegative_number(row["total_core_manpower"])))
    regions = state.tables.get("regions")
    if regions is None or not {"owner", "pop_15_64"}.issubset(regions.columns):
        return None
    population = sum(
        nonnegative_number(row.get("pop_15_64"))
        for row in regions.to_dicts()
        if str(row.get("owner") or "").strip().upper() == country_tag
    )
    return int(round(population))
