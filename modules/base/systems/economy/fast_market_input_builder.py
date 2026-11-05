from __future__ import annotations

import numpy as np
import polars as pl

from modules.base.systems.economy.market_data import _FastMarketArrays, _FastMarketLayout
from modules.base.systems.economy.missing_column_warning_registry import (
    MissingColumnWarningRegistry,
)


class FastMarketInputBuilder:
    @staticmethod
    def _numeric_values(frame: pl.DataFrame, column: str, default: float, row_count: int) -> np.ndarray:
        if column not in frame.columns:
            return np.full(row_count, default, dtype=np.float64)
        return (
            frame.get_column(column)
            .cast(pl.Float64, strict=False)
            .fill_null(default)
            .to_numpy()
        )

    def build(
        self,
        layout: _FastMarketLayout,
        warning_registry: MissingColumnWarningRegistry,
    ) -> _FastMarketArrays | None:
        context = layout.context
        row_count = context.production.height
        production_values = self._production_values(context.production)
        if production_values is None:
            return None

        demand, stock = self._demand_and_stock(layout, row_count)
        trade_modifiers_by_country = self._country_trade_modifiers(
            context.countries
        )
        if not np.isfinite(trade_modifiers_by_country).all():
            raise ValueError("countries.economic_trade_modifier must contain finite values.")
        trade_modifiers = np.clip(trade_modifiers_by_country, 0.5, 1.0)[layout.country_indices]
        government_controlled, legal, tax_rates = self._policy_arrays(
            context.production,
            row_count,
            warning_registry,
        )

        self._validate_numeric_values(
            production_values,
            demand,
            stock,
            tax_rates,
            trade_modifiers_by_country,
        )
        return _FastMarketArrays(
            production_values=production_values,
            demand=demand,
            stock=stock,
            trade_modifiers=trade_modifiers,
            trade_modifiers_by_country=trade_modifiers_by_country,
            government_controlled=government_controlled,
            legal=legal,
            tax_rates=tax_rates,
        )

    def _production_values(self, production: pl.DataFrame) -> np.ndarray | None:
        for column in (
            "domestic_production",
            "tax_rate",
            "is_gov_controlled",
            "is_legal",
        ):
            if column in production.columns and production.get_column(column).null_count():
                return None
        values = production.get_column("domestic_production").cast(
            pl.Float64, strict=False
        ).to_numpy()
        return values if np.isfinite(values).all() else None

    def _demand_and_stock(
        self,
        layout: _FastMarketLayout,
        row_count: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        demand = self._numeric_values(
            layout.context.ledger, "consumption_usd", 0.0, row_count
        )
        stock = (
            self._numeric_values(layout.stockpiles, "stock_amount", 0.0, row_count)
            if layout.stockpiles is not None
            else np.zeros(row_count, dtype=np.float64)
        )
        return demand, stock

    @staticmethod
    def _country_trade_modifiers(countries: pl.DataFrame) -> np.ndarray:
        if "economic_trade_modifier" not in countries.columns:
            return np.ones(countries.height, dtype=np.float64)
        return (
            countries.get_column("economic_trade_modifier")
            .cast(pl.Float64, strict=False)
            .fill_null(1.0)
            .to_numpy()
        )

    def _policy_arrays(
        self,
        production: pl.DataFrame,
        row_count: int,
        warning_registry: MissingColumnWarningRegistry,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        government_controlled = self._boolean_values(
            production, "is_gov_controlled", False, warning_registry
        )
        legal = self._boolean_values(
            production, "is_legal", True, warning_registry
        )
        tax_rates = self._numeric_values(production, "tax_rate", 0.05, row_count)
        if "tax_rate" not in production.columns:
            warning_registry.report_missing("tax_rate", 0.05)
        return government_controlled, legal, tax_rates

    def _boolean_values(
        self,
        production: pl.DataFrame,
        column: str,
        default: bool,
        warning_registry: MissingColumnWarningRegistry,
    ) -> np.ndarray:
        if column not in production.columns:
            warning_registry.report_missing(column, default)
            return np.full(production.height, default, dtype=np.bool_)
        return (
            production.get_column(column)
            .cast(pl.Boolean, strict=False)
            .fill_null(False)
            .to_numpy()
        )

    @staticmethod
    def _validate_numeric_values(
        production_values: np.ndarray,
        demand: np.ndarray,
        stock: np.ndarray,
        tax_rates: np.ndarray,
        trade_modifiers_by_country: np.ndarray,
    ) -> None:
        for table_name, column_name, values, require_nonnegative in (
            ("domestic_production", "domestic_production", production_values, True),
            ("resource_ledger", "consumption_usd", demand, True),
            ("stockpiles", "stock_amount", stock, True),
            ("domestic_production", "tax_rate", tax_rates, True),
            ("countries", "economic_trade_modifier", trade_modifiers_by_country, False),
        ):
            if not np.isfinite(values).all() or (
                require_nonnegative and (values < 0.0).any()
            ):
                raise ValueError(
                    f"{table_name}.{column_name} must contain finite"
                    f"{' and non-negative' if require_nonnegative else ''} values."
                )
