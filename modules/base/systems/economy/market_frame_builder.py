import polars as pl

from src.shared.state import GameState
from modules.base.systems.economy.missing_column_warning_registry import MissingColumnWarningRegistry


class MarketFrameBuilder:
    """Compose the lazy market frame from the current economy tables."""

    def build(
        self,
        state: GameState,
        production_with_treaty_bonuses: pl.LazyFrame,
        resource_physics: pl.DataFrame,
        warning_registry: MissingColumnWarningRegistry,
    ) -> pl.LazyFrame:
        countries = state.get_table("countries")
        country_columns = set(countries.columns)
        trade_modifier = (
            pl.col("economic_trade_modifier").cast(pl.Float64, strict=False).fill_null(1.0).clip(0.5, 1.0)
            if "economic_trade_modifier" in country_columns
            else pl.lit(1.0)
        )
        trade_modifiers = countries.lazy().select(
            pl.col("id").alias("country_id"),
            trade_modifier.alias("_economic_trade_modifier"),
        )

        if "resource_ledger" in state.tables:
            demand = state.get_table("resource_ledger").lazy().select(
                pl.col("country_id"),
                pl.col("game_resource_id"),
                pl.col("consumption_usd").alias("demand"),
            )
        else:
            demand = production_with_treaty_bonuses.select(
                ["country_id", "game_resource_id"]
            ).with_columns(pl.lit(0.0).alias("demand"))

        if "stockpiles" in state.tables:
            stock = state.get_table("stockpiles").lazy()
        else:
            stock = production_with_treaty_bonuses.select(
                ["country_id", "game_resource_id"]
            ).with_columns(pl.lit(0.0).alias("stock_amount"))

        market = production_with_treaty_bonuses.join(
            demand, on=["country_id", "game_resource_id"], how="left"
        ).with_columns(pl.col("demand").fill_null(0.0))
        market = market.join(trade_modifiers, on="country_id", how="left").with_columns(
            pl.col("_economic_trade_modifier").fill_null(1.0)
        )
        market = market.join(
            stock, on=["country_id", "game_resource_id"], how="left"
        ).with_columns(pl.col("stock_amount").fill_null(0.0))

        # Older module data may omit metadata, so retain the established defaults.
        production_columns = state.get_table("domestic_production").columns
        market = self._with_default_column(
            market, production_columns, warning_registry, "is_gov_controlled", False
        )
        market = self._with_default_column(
            market, production_columns, warning_registry, "is_legal", True
        )
        market = self._with_default_column(
            market, production_columns, warning_registry, "tax_rate", 0.05
        )

        return market.join(
            resource_physics.lazy(), on="game_resource_id", how="left"
        ).with_columns([
            pl.col("is_storable").fill_null(True),
            pl.col("decay_rate").fill_null(0.10),
        ])

    @staticmethod
    def _with_default_column(
        market: pl.LazyFrame,
        production_columns: list[str],
        warning_registry: MissingColumnWarningRegistry,
        column: str,
        default: bool | float,
    ) -> pl.LazyFrame:
        if column in production_columns:
            return market
        warning_registry.report_missing(column, default)
        return market.with_columns(pl.lit(default).alias(column))
