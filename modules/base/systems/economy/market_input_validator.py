from modules.base.systems.economy.input_validation import validate_numeric_columns
from src.shared.state import GameState


class MarketInputValidator:
    """Validate the economy tables consumed by market simulation paths."""

    def validate(self, state: GameState) -> None:
        validate_numeric_columns(
            state.get_table("domestic_production"),
            "domestic_production",
            ("domestic_production", "tax_rate", "desired_trade_usd"),
            nonnegative=("domestic_production", "tax_rate"),
        )
        resource_ledger = state.tables.get("resource_ledger")
        if resource_ledger is not None:
            validate_numeric_columns(
                resource_ledger,
                "resource_ledger",
                ("consumption_usd",),
                nonnegative=("consumption_usd",),
            )
        stockpiles = state.tables.get("stockpiles")
        if stockpiles is not None:
            validate_numeric_columns(
                stockpiles,
                "stockpiles",
                ("stock_amount",),
                nonnegative=("stock_amount",),
            )
        validate_numeric_columns(
            state.get_table("countries"),
            "countries",
            ("economic_trade_modifier", "global_resource_tax_modifier"),
        )
        countries = state.get_table("countries")
        if "global_resource_tax_modifier" in countries.columns:
            values = countries["global_resource_tax_modifier"].cast(float)
            if ((values < 0.0) | (values > 1.0)).any():
                raise ValueError("countries.global_resource_tax_modifier must be a finite ratio from 0 to 1.")
