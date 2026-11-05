from __future__ import annotations

import polars as pl

from src.shared.numeric import stable_group_sums, stable_sum
from src.shared.state import GameState


class TreatyProductionBonusPolicy:
    """Apply treaty production bonuses before market supply is calculated."""

    @staticmethod
    def apply(state: GameState, production: pl.LazyFrame) -> pl.LazyFrame:
        effects = state.tables.get("treaty_effects")
        if (
            effects is None
            or effects.is_empty()
            or "domestic_production" not in production.collect_schema().names()
        ):
            return production
        bonuses = stable_group_sums(
            effects.filter(pl.col("effect") == "resource_production_bonus"),
            ("country_id",),
            {"value": "treaty_production_bonus"},
        ).with_columns(pl.col("treaty_production_bonus").clip(0.0, 0.25))
        return (
            production
            .join(bonuses.lazy(), on="country_id", how="left")
            .with_columns(
                (
                    pl.col("domestic_production")
                    * (1.0 + pl.col("treaty_production_bonus").fill_null(0.0))
                ).alias("domestic_production")
            )
            .drop("treaty_production_bonus")
        )


class MarketBalanceCalculator:
    """Calculate global supply, demand, stock, and fiscal market columns."""

    def calculate(self, market: pl.LazyFrame, fraction: float) -> pl.DataFrame:
        market = market.with_columns(
            (pl.col("domestic_production") + pl.col("stock_amount")).alias(
                "local_supply"
            )
        )
        market = market.with_columns(
            [
                pl.when(pl.col("local_supply") >= pl.col("demand"))
                .then(pl.col("local_supply") - pl.col("demand"))
                .otherwise(0.0)
                .alias("export_desired"),
                pl.when(pl.col("demand") > pl.col("local_supply"))
                .then(pl.col("demand") - pl.col("local_supply"))
                .otherwise(0.0)
                .alias("import_desired"),
            ]
        )
        market = market.with_columns(
            (pl.col("import_desired") * pl.col("_economic_trade_modifier")).alias(
                "affordable_import"
            )
        )

        world_market = market.group_by("game_resource_id").agg(
            stable_sum("export_desired").alias("global_supply"),
            stable_sum("affordable_import").alias("global_demand"),
        )
        market = market.join(world_market, on="game_resource_id", how="left")
        market = market.with_columns(
            (
                pl.col("affordable_import")
                * pl.when(pl.col("global_demand") > 0)
                .then(
                    pl.min_horizontal(
                        1.0, pl.col("global_supply") / pl.col("global_demand")
                    )
                )
                .otherwise(0.0)
            ).alias("import_actual"),
            (
                pl.col("export_desired")
                * pl.when(pl.col("global_supply") > 0)
                .then(
                    pl.min_horizontal(
                        1.0, pl.col("global_demand") / pl.col("global_supply")
                    )
                )
                .otherwise(0.0)
            ).alias("export_actual"),
            (pl.col("tax_rate") + 0.02).alias("total_tax"),
        )

        unsold_amount = pl.col("export_desired") - pl.col("export_actual")
        new_stock_amount = (
            pl.when(pl.col("is_storable"))
            .then(unsold_amount * (1.0 - pl.col("decay_rate") * fraction))
            .otherwise(0.0)
        )
        production_denominator = pl.max_horizontal(pl.col("domestic_production"), 1.0)
        stock_to_production = new_stock_amount / production_denominator
        market = market.with_columns(
            unsold_amount.alias("unsold_amount"),
            new_stock_amount.alias("new_stock_amount"),
            pl.when(~pl.col("is_storable"))
            .then((unsold_amount / production_denominator) * 0.5 * fraction)
            .when(pl.col("is_storable") & (stock_to_production > 0.5))
            .then(pl.min_horizontal(stock_to_production * 0.05, 0.10) * fraction)
            .otherwise(0.0)
            .alias("production_penalty_pct"),
        )
        market = market.with_columns(
            (
                pl.col("domestic_production")
                * (1.0 - pl.col("production_penalty_pct"))
            ).alias("domestic_production"),
            pl.when(pl.col("is_gov_controlled"))
            .then(pl.col("import_actual") * 1.5)
            .otherwise(0.0)
            .alias("gov_import_expense"),
            pl.when(pl.col("is_gov_controlled"))
            .then(pl.col("export_actual") * 1.5)
            .when(pl.col("is_legal"))
            .then(
                (pl.col("import_actual") + pl.col("export_actual"))
                * pl.col("total_tax")
            )
            .otherwise(0.0)
            .alias("gov_tax_revenue"),
        )
        return market.collect()


class ConstrainedMarketReconciler:
    """Reconcile market balances after bilateral treaty allocation."""

    @staticmethod
    def reconcile(
        market: pl.DataFrame,
        flows: pl.DataFrame,
        fraction: float,
    ) -> pl.DataFrame:
        exports = stable_group_sums(
            flows,
            ("exporter_id", "game_resource_id"),
            {"trade_value_usd": "export_actual"},
        ).rename({"exporter_id": "country_id"})
        imports = stable_group_sums(
            flows,
            ("importer_id", "game_resource_id"),
            {"trade_value_usd": "import_actual"},
        ).rename({"importer_id": "country_id"})
        reconciled = (
            market.drop(["import_actual", "export_actual"], strict=False)
            .join(exports, on=["country_id", "game_resource_id"], how="left")
            .join(imports, on=["country_id", "game_resource_id"], how="left")
            .with_columns(pl.col(["import_actual", "export_actual"]).fill_null(0.0))
        )
        base_production = pl.when(
            1.0 - pl.col("production_penalty_pct") > 0.0
        ).then(
            pl.col("domestic_production") / (1.0 - pl.col("production_penalty_pct"))
        ).otherwise(pl.col("domestic_production"))
        reconciled = reconciled.with_columns(
            base_production.alias("base_domestic_production")
        )
        reconciled = reconciled.with_columns(
            (pl.col("export_desired") - pl.col("export_actual"))
            .clip(0.0, None)
            .alias("unsold_amount")
        )
        reconciled = reconciled.with_columns(
            pl.when(pl.col("is_storable"))
            .then(pl.col("unsold_amount") * (1.0 - pl.col("decay_rate") * fraction))
            .otherwise(0.0)
            .alias("new_stock_amount")
        )
        reconciled = reconciled.with_columns(
            pl.when(~pl.col("is_storable"))
            .then(
                (pl.col("unsold_amount") / pl.max_horizontal(
                    pl.col("base_domestic_production"), 1.0
                )) * 0.5 * fraction
            )
            .when(
                pl.col("is_storable")
                & (
                    pl.col("new_stock_amount")
                    / pl.max_horizontal(pl.col("base_domestic_production"), 1.0)
                    > 0.5
                )
            )
            .then(
                pl.min_horizontal(
                    (
                        pl.col("new_stock_amount")
                        / pl.max_horizontal(pl.col("base_domestic_production"), 1.0)
                    )
                    * 0.05,
                    0.10,
                )
                * fraction
            )
            .otherwise(0.0)
            .alias("production_penalty_pct")
        ).with_columns(
            [
                (
                    pl.col("base_domestic_production")
                    * (1.0 - pl.col("production_penalty_pct"))
                ).alias("domestic_production"),
                pl.when(pl.col("is_gov_controlled"))
                .then(pl.col("import_actual") * 1.5)
                .otherwise(0.0)
                .alias("gov_import_expense"),
                pl.when(pl.col("is_gov_controlled"))
                .then(pl.col("export_actual") * 1.5)
                .when(pl.col("is_legal"))
                .then(
                    (pl.col("import_actual") + pl.col("export_actual"))
                    * pl.col("total_tax")
                )
                .otherwise(0.0)
                .alias("gov_tax_revenue"),
            ]
        )
        return reconciled.drop("base_domestic_production")
