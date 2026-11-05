"""Prepare resource market flows for presentation."""

import polars as pl

RESOURCE_LEDGER_COLUMNS = frozenset({
    "country_id", "game_resource_id", "category", "production_usd",
    "consumption_usd", "trade_usd", "balance_usd",
})
TRADE_NETWORK_COLUMNS = frozenset({
    "exporter_id", "importer_id", "game_resource_id", "trade_value_usd",
})


def validate_resource_ledger(ledger: pl.DataFrame | None) -> None:
    if ledger is None:
        raise ValueError("Resource market data requires the resource_ledger table.")
    missing = RESOURCE_LEDGER_COLUMNS.difference(ledger.columns)
    if missing:
        raise ValueError("resource_ledger is missing required columns: " + ", ".join(sorted(missing)))


def build_resource_flows(ledger: pl.DataFrame, trade: pl.DataFrame | None, country: str) -> pl.DataFrame:
    country_ledger = ledger.filter(pl.col("country_id") == country) if country else ledger
    production = country_ledger.group_by("game_resource_id").agg(
        pl.col("production_usd").sum().alias("production_usd"),
        pl.col("consumption_usd").sum().alias("consumption_usd"),
        pl.col("trade_usd").sum().alias("ledger_trade_usd"),
        pl.col("balance_usd").sum().alias("balance_usd"),
    )
    if trade is None:
        trade_flows = pl.DataFrame(
            schema={"game_resource_id": pl.Utf8, "exports": pl.Float64, "imports": pl.Float64}
        )
    else:
        missing = TRADE_NETWORK_COLUMNS.difference(trade.columns)
        if missing:
            raise ValueError("Trade network is missing required columns: " + ", ".join(sorted(missing)))
        exports = trade.filter(pl.col("exporter_id") == country).group_by("game_resource_id").agg(
            pl.col("trade_value_usd").sum().alias("exports")
        )
        imports = trade.filter(pl.col("importer_id") == country).group_by("game_resource_id").agg(
            pl.col("trade_value_usd").sum().alias("imports")
        )
        trade_flows = exports.join(imports, on="game_resource_id", how="full", coalesce=True)

    return (
        production.join(trade_flows, on="game_resource_id", how="full", coalesce=True)
        .with_columns(
            pl.col("production_usd").fill_null(0.0),
            pl.col("consumption_usd").fill_null(0.0),
            pl.col("ledger_trade_usd").fill_null(0.0),
            pl.col("balance_usd").fill_null(0.0),
            pl.col("exports").fill_null(0.0),
            pl.col("imports").fill_null(0.0),
        )
        .with_columns((pl.col("exports") - pl.col("imports")).alias("net_trade_usd"))
        .with_columns(pl.col("balance_usd").abs().alias("_abs_balance"))
        .sort(["_abs_balance", "game_resource_id"], descending=[True, False])
        .drop("_abs_balance")
    )
