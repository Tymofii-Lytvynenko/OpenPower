import math
from collections.abc import Iterable, Mapping


DEFAULT_SECTOR_ALLOCATION = 0.50
DEFAULT_PERSONAL_INCOME_TAX_RATE = 0.20


def default_budget_allocations(
    sector_keys: Iterable[str], income_tax_key: str
) -> dict[str, float]:
    allocations = {
        key: DEFAULT_SECTOR_ALLOCATION
        for key in sector_keys
    }
    allocations[income_tax_key] = DEFAULT_PERSONAL_INCOME_TAX_RATE
    return allocations


def country_budget_allocations(
    country: Mapping[str, object] | None,
    sector_keys: Iterable[str],
    income_tax_key: str,
) -> dict[str, float] | None:
    if country is None:
        return None

    defaults = default_budget_allocations(sector_keys, income_tax_key)
    return {
        key: normalize_budget_ratio(country.get(key), fallback)
        for key, fallback in defaults.items()
    }


def normalize_budget_ratio(value: object, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        number = fallback

    if not math.isfinite(number):
        number = fallback
    return max(0.0, min(number, 1.0))
