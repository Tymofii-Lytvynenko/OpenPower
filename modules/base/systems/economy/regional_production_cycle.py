"""Project regional output into the national market for the current territory map."""

import polars as pl

from src.shared.state import GameState


_KEYS = ["country_id", "game_resource_id"]
_OUTPUT = "domestic_production"


def _ownership(state: GameState) -> pl.DataFrame | None:
    regions = state.tables.get("regions")
    if regions is None or not {"id", "owner"}.issubset(regions.columns):
        return None
    owner = pl.col("owner").fill_null("").str.strip_chars().str.to_uppercase()
    controller = owner
    if "controller" in regions.columns:
        tag = pl.col("controller").fill_null("").str.strip_chars().str.to_uppercase()
        controller = pl.when(tag == "").then(owner).otherwise(tag)
    return regions.select(
        pl.col("id").alias("region_id"),
        owner.alias("_owner"),
        ((owner != "") & (owner == controller)).alias("_operating"),
    )


def refresh_regional_production(state: GameState) -> None:
    regional = state.tables.get("regional_production")
    national = state.tables.get("domestic_production")
    if regional is None or regional.is_empty() or national is None:
        return
    ownership = _ownership(state)
    if ownership is None:
        return

    # Retain former keys during annexation so the old owner's derived total becomes zero.
    former_keys = regional.select(_KEYS).unique()
    mapped = regional.join(ownership, on="region_id", how="left", maintain_order="left")
    mapped = mapped.with_columns(
        pl.col("country_id").alias("_former_country"),
        pl.when(pl.col("_owner").fill_null("") != "")
        .then(pl.col("_owner"))
        .otherwise(pl.col("country_id"))
        .alias("country_id")
    )
    if not regional["country_id"].equals(mapped["country_id"]):
        mapped = mapped.with_columns(
            pl.when(pl.col("country_id") != pl.col("_former_country"))
            .then(pl.concat_str("country_id", "region_id", "game_resource_id", separator=":"))
            .otherwise(pl.col("id")).alias("id")
        )
        state.update_table("regional_production", mapped.select(regional.columns))

    totals = mapped.group_by(_KEYS).agg(
        pl.when(pl.col("_operating").fill_null(False)).then(pl.col(_OUTPUT))
        .otherwise(0.0).sum().alias("_regional_output")
    )
    totals = former_keys.join(totals, on=_KEYS, how="full", coalesce=True).with_columns(
        pl.col("_regional_output").fill_null(0.0)
    )
    updated = national.join(totals, on=_KEYS, how="full", coalesce=True).with_columns(
        pl.coalesce("_regional_output", _OUTPUT).alias(_OUTPUT)
    )
    for name, default in (("is_legal", True), ("is_gov_controlled", False), ("tax_rate", 0.0)):
        if name in updated.columns:
            updated = updated.with_columns(pl.col(name).fill_null(default))
    state.update_table("domestic_production", updated.select(national.columns).sort(_KEYS))


def apply_national_production_changes(state: GameState, previous: pl.DataFrame) -> None:
    """Distribute lasting market or growth changes over operating regions only."""
    regional = state.tables.get("regional_production")
    if regional is None or regional.is_empty():
        return
    ownership = _ownership(state)
    if ownership is None:
        return
    national = state.get_table("domestic_production")
    rates = national.select(*_KEYS, _OUTPUT).join(
        previous.select(*_KEYS, pl.col(_OUTPUT).alias("_previous")), on=_KEYS,
    ).filter((pl.col("_previous") > 0) & (pl.col("_previous") != pl.col(_OUTPUT))).select(
        *_KEYS, (pl.col(_OUTPUT) / pl.col("_previous")).alias("_rate")
    )
    if rates.is_empty():
        return
    updated = regional.join(rates, on=_KEYS, how="left", maintain_order="left").join(
        ownership.select("region_id", "_operating"), on="region_id", how="left", maintain_order="left",
    ).with_columns(
        pl.when(pl.col("_operating").fill_null(False) & pl.col("_rate").is_not_null())
        .then(pl.col(_OUTPUT) * pl.col("_rate"))
        .otherwise(pl.col(_OUTPUT)).alias(_OUTPUT)
    )
    state.update_table("regional_production", updated.select(regional.columns))


def operating_regional_production(state: GameState, regional: pl.DataFrame) -> pl.DataFrame:
    ownership = _ownership(state)
    if ownership is None:
        return regional
    return regional.join(ownership.filter(pl.col("_operating")).select("region_id"), on="region_id", how="semi")
