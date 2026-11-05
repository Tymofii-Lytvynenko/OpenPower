"""Pure NumPy policy for unconstrained global market clearing."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class UnconstrainedMarketResult:
    updated_production: np.ndarray
    new_stock: np.ndarray
    import_actual: np.ndarray
    export_actual: np.ndarray
    trade_income: np.ndarray
    trade_expense: np.ndarray


def calculate_unconstrained_market(
    *,
    production_values: np.ndarray,
    demand: np.ndarray,
    stock: np.ndarray,
    trade_modifiers: np.ndarray,
    resource_indices: np.ndarray,
    country_indices: np.ndarray,
    decay_rates_by_resource: np.ndarray,
    storable_by_resource: np.ndarray,
    government_controlled: np.ndarray,
    legal: np.ndarray,
    tax_rates: np.ndarray,
    fraction: float,
    row_count: int,
    country_count: int,
) -> UnconstrainedMarketResult:
    """Calculate market outputs from aligned, validated arrays without mutating them."""
    local_supply = production_values + stock
    export_desired = np.maximum(local_supply - demand, 0.0)
    import_desired = np.maximum(demand - local_supply, 0.0)
    affordable_import = import_desired * trade_modifiers
    global_supply = np.bincount(
        resource_indices,
        weights=export_desired,
        minlength=len(decay_rates_by_resource),
    )
    global_demand = np.bincount(
        resource_indices,
        weights=affordable_import,
        minlength=len(decay_rates_by_resource),
    )
    resource_supply = global_supply[resource_indices]
    resource_demand = global_demand[resource_indices]
    import_ratio = np.divide(
        resource_supply,
        resource_demand,
        out=np.zeros(row_count, dtype=np.float64),
        where=resource_demand > 0.0,
    )
    export_ratio = np.divide(
        resource_demand,
        resource_supply,
        out=np.zeros(row_count, dtype=np.float64),
        where=resource_supply > 0.0,
    )
    import_actual = affordable_import * np.minimum(1.0, import_ratio)
    export_actual = export_desired * np.minimum(1.0, export_ratio)
    unsold_amount = export_desired - export_actual
    storable = storable_by_resource[resource_indices]
    decay_rates = decay_rates_by_resource[resource_indices]
    new_stock = np.where(storable, unsold_amount * (1.0 - decay_rates * fraction), 0.0)
    production_denominator = np.maximum(production_values, 1.0)
    stock_to_production = new_stock / production_denominator
    production_penalty = np.where(
        ~storable,
        (unsold_amount / production_denominator) * 0.5 * fraction,
        np.where(
            stock_to_production > 0.5,
            np.minimum(stock_to_production * 0.05, 0.10) * fraction,
            0.0,
        ),
    )
    updated_production = production_values * (1.0 - production_penalty)
    total_tax = tax_rates + 0.02
    government_import_expense = np.where(government_controlled, import_actual * 1.5, 0.0)
    government_tax_revenue = np.where(
        government_controlled,
        export_actual * 1.5,
        np.where(legal, (import_actual + export_actual) * total_tax, 0.0),
    )
    trade_income = np.bincount(
        country_indices,
        weights=government_tax_revenue,
        minlength=country_count,
    )
    trade_expense = np.bincount(
        country_indices,
        weights=government_import_expense,
        minlength=country_count,
    )

    return UnconstrainedMarketResult(
        updated_production=updated_production,
        new_stock=new_stock,
        import_actual=import_actual,
        export_actual=export_actual,
        trade_income=trade_income,
        trade_expense=trade_expense,
    )
