from __future__ import annotations

import polars as pl

from modules.base.systems.economy.market_flow_resolver import MarketFlowResolution
from src.shared.frames import ensure_sorted
from src.shared.state import GameState


class MarketCyclePublisher:
    """Publish a resolved market cycle in the established table order."""

    @staticmethod
    def publish(state: GameState, resolution: MarketFlowResolution) -> None:
        # Downstream projections preserve this order, so the market is sorted once.
        market = resolution.market.sort(["country_id", "game_resource_id"])
        state.update_table("stockpiles", MarketCyclePublisher._stockpile_table(market))
        state.update_table(
            "trade_network",
            MarketCyclePublisher._trade_network_table(
                market,
                resolution.constrained_flows,
            ),
        )
        state.update_table(
            "domestic_production",
            MarketCyclePublisher._production_table(market),
        )
        state.update_table(
            "countries",
            ensure_sorted(resolution.countries, ("id",)),
        )

    @staticmethod
    def _stockpile_table(market: pl.DataFrame) -> pl.DataFrame:
        return market.select(
            [
                "country_id",
                "game_resource_id",
                pl.col("new_stock_amount").alias("stock_amount"),
            ]
        )

    @staticmethod
    def _trade_network_table(
        market: pl.DataFrame,
        constrained_flows: pl.DataFrame | None,
    ) -> pl.DataFrame:
        if constrained_flows is not None:
            return constrained_flows.sort(
                ["exporter_id", "importer_id", "game_resource_id"]
            )
        exports = market.filter(pl.col("export_actual") > 0).select(
            [
                pl.col("country_id").alias("exporter_id"),
                pl.lit("WORLD").alias("importer_id"),
                pl.col("game_resource_id"),
                pl.col("export_actual").alias("trade_value_usd"),
            ]
        )
        imports = market.filter(pl.col("import_actual") > 0).select(
            [
                pl.lit("WORLD").alias("exporter_id"),
                pl.col("country_id").alias("importer_id"),
                pl.col("game_resource_id"),
                pl.col("import_actual").alias("trade_value_usd"),
            ]
        )
        return pl.concat([exports, imports]).sort(
            ["exporter_id", "importer_id", "game_resource_id"]
        )

    @staticmethod
    def _production_table(market: pl.DataFrame) -> pl.DataFrame:
        final_production_columns = [
            column
            for column in market.columns
            if column
            not in [
                "demand",
                "stock_amount",
                "local_supply",
                "export_desired",
                "import_desired",
                "priority",
                "affordable_import",
                "global_supply",
                "global_demand",
                "imp_ratio",
                "exp_ratio",
                "import_actual",
                "export_actual",
                "unsold_amount",
                "new_stock_amount",
                "stock_to_prod_ratio",
                "production_penalty_pct",
                "total_tax",
                "gov_import_expense",
                "gov_tax_revenue",
                "is_storable",
                "decay_rate",
                "_economic_trade_modifier",
            ]
        ]
        return market.select(final_production_columns)
