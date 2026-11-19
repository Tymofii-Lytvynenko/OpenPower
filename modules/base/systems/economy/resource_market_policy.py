"""Validated resource market choices shared by authoritative economy stages."""
import math

import polars as pl


def validate_market_policy_update(action) -> str:
    for field, lower, upper in (("global_tax_modifier", 0.0, 1.0),
                                 ("desired_trade_usd", -1e15, 1e15)):
        value = getattr(action, field)
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return f"{field} must be a finite number between {lower} and {upper}."
        if not math.isfinite(number) or not lower <= number <= upper:
            return f"{field} must be a finite number between {lower} and {upper}."
    if action.meet_consumption is not None and type(action.meet_consumption) is not bool:
        return "Meet consumption must be a boolean value."
    return ""


def apply_trade_targets(market: pl.LazyFrame) -> pl.LazyFrame:
    """Bound discretionary exports by supply and avoid buying unstorable excess."""
    columns = market.collect_schema().names()
    defaults = {"desired_trade_usd": 0.0, "meet_consumption": True}
    market = market.with_columns([pl.lit(value).alias(key) for key, value in defaults.items() if key not in columns])
    automatic = pl.col("meet_consumption").fill_null(True)
    desired = pl.col("desired_trade_usd").fill_null(0.0)
    gap = (pl.col("demand") - pl.col("local_supply")).clip(lower_bound=0.0)
    manual_import = (-desired).clip(lower_bound=0.0)
    return market.with_columns(
        pl.when(automatic).then((pl.col("local_supply") - pl.col("demand")).clip(lower_bound=0.0))
        .otherwise(pl.min_horizontal(desired.clip(lower_bound=0.0), pl.col("local_supply")))
        .alias("export_desired"),
        pl.when(automatic).then(gap)
        .when(pl.col("is_storable")).then(manual_import)
        .otherwise(pl.min_horizontal(manual_import, gap)).alias("import_desired"),
    )


def remaining_market_stock() -> pl.Expr:
    # Manual targets can withhold exports or purchase reserves; neither may destroy physical goods.
    return (pl.col("local_supply") + pl.col("import_actual")
            - pl.col("export_actual") - pl.col("demand")).clip(lower_bound=0.0)
