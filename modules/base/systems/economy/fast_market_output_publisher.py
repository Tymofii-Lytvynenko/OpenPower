from __future__ import annotations

import numpy as np
import polars as pl

from modules.base.systems.economy.market_clearing_kernel import UnconstrainedMarketResult
from modules.base.systems.economy.market_data import (
    _FastMarketArrays,
    _FastMarketLayout,
    _PreparedFastMarketOutput,
)
from src.shared.frames import ensure_sorted
from src.shared.state import GameState


class FastMarketOutputPublisher:
    @staticmethod
    def prepare(
        layout: _FastMarketLayout,
        arrays: _FastMarketArrays,
        clearing: UnconstrainedMarketResult,
    ) -> _PreparedFastMarketOutput:
        context = layout.context
        production = context.production
        production_updates = [
            pl.Series("domestic_production", clearing.updated_production),
            pl.Series("stock_amount", clearing.new_stock),
        ]
        if "is_gov_controlled" not in production.columns:
            production_updates.append(
                pl.Series("is_gov_controlled", arrays.government_controlled)
            )
        if "is_legal" not in production.columns:
            production_updates.append(pl.Series("is_legal", arrays.legal))
        if "tax_rate" not in production.columns:
            production_updates.append(pl.Series("tax_rate", arrays.tax_rates))
        market_output = production.with_columns(production_updates)

        cached_country_indices = layout.country_indices
        cached_resource_indices = layout.resource_indices
        if not layout.keys_are_sorted:
            # Keep the cached row mapping aligned with the canonical market output order.
            sort_order = np.lexsort(
                (
                    context.production_resource_ids.to_numpy(),
                    context.production_country_ids.to_numpy(),
                )
            )
            cached_country_indices = layout.country_indices[sort_order]
            cached_resource_indices = layout.resource_indices[sort_order]
            market_output = ensure_sorted(market_output, layout.context.key_columns)
        return _PreparedFastMarketOutput(
            market_output=market_output,
            cached_country_indices=cached_country_indices,
            cached_resource_indices=cached_resource_indices,
        )

    @staticmethod
    def publish(
        state: GameState,
        layout: _FastMarketLayout,
        prepared: _PreparedFastMarketOutput,
        clearing: UnconstrainedMarketResult,
    ) -> None:
        context = layout.context
        production_country_ids = context.production_country_ids
        production_resource_ids = context.production_resource_ids
        market_output = prepared.market_output
        state.update_table(
            "stockpiles",
            market_output.select("country_id", "game_resource_id", "stock_amount"),
        )

        flow_schema = {
            "exporter_id": pl.Utf8,
            "importer_id": pl.Utf8,
            "game_resource_id": pl.Utf8,
            "trade_value_usd": pl.Float64,
        }
        positive_exports = np.flatnonzero(clearing.export_actual > 0.0)
        positive_imports = np.flatnonzero(clearing.import_actual > 0.0)
        export_rows = pl.DataFrame(
            {
                "exporter_id": production_country_ids.gather(positive_exports),
                "importer_id": ["WORLD"] * len(positive_exports),
                "game_resource_id": production_resource_ids.gather(positive_exports),
                "trade_value_usd": clearing.export_actual[positive_exports],
            },
            schema=flow_schema,
        )
        import_rows = pl.DataFrame(
            {
                "exporter_id": ["WORLD"] * len(positive_imports),
                "importer_id": production_country_ids.gather(positive_imports),
                "game_resource_id": production_resource_ids.gather(positive_imports),
                "trade_value_usd": clearing.import_actual[positive_imports],
            },
            schema=flow_schema,
        )
        trade_network = pl.concat([export_rows, import_rows])
        if not (layout.keys_are_sorted and layout.country_ids_precede_world):
            trade_network = trade_network.sort(
                ["exporter_id", "importer_id", "game_resource_id"]
            )
        state.update_table("trade_network", trade_network)
        state.update_table("domestic_production", market_output.drop("stock_amount"))

        updated_countries = context.countries.with_columns(
            pl.Series("trade_income", clearing.trade_income),
            pl.Series("trade_expense", clearing.trade_expense),
        )
        if not context.country_id_series.is_sorted():
            updated_countries = ensure_sorted(updated_countries, ("id",))
        state.update_table("countries", updated_countries)
