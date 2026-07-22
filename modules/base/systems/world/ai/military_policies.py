from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import polars as pl

from modules.base.systems.world.ai.common import (
    active_war_members,
    active_war_pairs,
    country_frame,
    country_strength,
    treaty_member_rows,
    with_defaults,
)
from src.core.ai_framework import AITableContext
from src.shared.actions import (
    ActionAttackUnit,
    ActionBuyMarketUnit,
    ActionMoveUnit,
    ActionQueueUnitProduction,
    GameAction,
)


class ProcurementPolicy:
    id = "procurement"
    required_tables = frozenset({"countries", "unit_designs", "production_orders"})
    cadence_days = 7

    def build_candidates(self, context: AITableContext) -> pl.LazyFrame:
        need = self._procurement_need(context)
        return pl.concat(
            [
                self._production_candidates(context, need),
                self._market_candidates(context, need),
            ],
            how="diagonal_relaxed",
        )

    def resolve_action(self, row: Mapping[str, Any]) -> GameAction | None:
        kind = str(row.get("action_kind") or "")
        country = str(row.get("country_id") or "")
        quantity = max(1, int(row.get("quantity") or 1))
        if kind == "queue_production":
            return ActionQueueUnitProduction(
                "ai_system",
                country,
                str(row.get("design_id") or ""),
                quantity,
                1,
            )
        if kind == "buy_market_unit":
            return ActionBuyMarketUnit(
                "ai_system",
                str(row.get("listing_id") or ""),
                country,
                quantity,
            )
        return None

    def _procurement_need(self, context: AITableContext) -> pl.LazyFrame:
        countries = country_frame(context, self.cadence_days)
        strengths = country_strength(context)
        wars = active_war_pairs(context)
        hostile = (
            wars.join(
                strengths.rename(
                    {"country_id": "target_country", "military_strength": "_hostile_strength"}
                ),
                on="target_country",
                how="left",
            )
            .group_by("source_country")
            .agg(pl.col("_hostile_strength").fill_null(0.0).sum().alias("hostile_strength"))
            .rename({"source_country": "country_id"})
        )
        allies = self._allied_strength(context, strengths)
        orders = context.table("production_orders")
        assert orders is not None
        order_schema = set(orders.collect_schema().names())
        if {"country_id", "quantity"}.issubset(order_schema):
            active_orders = orders
            if "status" in order_schema:
                active_orders = active_orders.filter(
                    pl.col("status").fill_null("queued").str.to_lowercase().is_in(
                        ["queued", "producing", "active"]
                    )
                )
            active_orders = (
                active_orders.group_by(
                    pl.col("country_id").cast(pl.Utf8).str.to_uppercase().alias("country_id")
                )
                .agg(
                    pl.col("quantity").cast(pl.Float64, strict=False).fill_null(0.0).sum().alias("ordered_strength"),
                    pl.len().alias("active_order_count"),
                )
            )
        else:
            active_orders = pl.DataFrame(
                schema={
                    "country_id": pl.Utf8,
                    "ordered_strength": pl.Float64,
                    "active_order_count": pl.UInt32,
                }
            ).lazy()

        return (
            countries.join(strengths, on="country_id", how="left")
            .join(hostile, on="country_id", how="left")
            .join(allies, on="country_id", how="left")
            .join(active_orders, on="country_id", how="left")
            .with_columns(
                pl.col("military_strength").fill_null(0.0),
                pl.col("hostile_strength").fill_null(0.0),
                pl.col("allied_strength").fill_null(0.0),
                pl.col("ordered_strength").fill_null(0.0),
                pl.col("active_order_count").fill_null(0),
            )
            .with_columns(
                pl.max_horizontal(
                    pl.col("military_count"),
                    pl.col("hostile_strength") * 1.10,
                    pl.col("allied_strength") * 0.75,
                    pl.lit(1.0),
                ).alias("_target_strength")
            )
            .with_columns(
                (
                    pl.col("_target_strength")
                    - pl.col("military_strength")
                    - pl.col("ordered_strength")
                ).clip(lower_bound=0.0).alias("strength_gap")
            )
            .filter(
                (pl.col("strength_gap") > 0.0)
                & (pl.col("active_order_count") == 0)
                & (pl.col("money_reserves") > 0.0)
            )
        )

    def _production_candidates(
        self,
        context: AITableContext,
        need: pl.LazyFrame,
    ) -> pl.LazyFrame:
        designs = context.table("unit_designs")
        assert designs is not None
        schema = set(designs.collect_schema().names())
        required = {"id", "country_id", "cost"}
        if not required.issubset(schema):
            return need.filter(pl.lit(False))
        designs = with_defaults(
            designs,
            {
                "quality": (pl.Float64, 0.0),
                "speed": (pl.Float64, 0.0),
                "firepower": (pl.Float64, 0.0),
            },
        ).select(
            pl.col("id").cast(pl.Utf8).alias("design_id"),
            pl.col("country_id").cast(pl.Utf8).str.to_uppercase().alias("country_id"),
            pl.col("cost").cast(pl.Float64).clip(lower_bound=1.0).alias("unit_cost"),
            "quality",
            "speed",
            "firepower",
        )
        return (
            need.join(designs, on="country_id", how="inner")
            .with_columns(
                (pl.col("unit_cost") * 1.50).alias("_five_year_cost"),
                (
                    pl.col("quality") * 0.30
                    + pl.col("speed") * 0.20
                    + pl.col("firepower") * 0.50
                ).alias("_combat_value"),
            )
            .with_columns(
                pl.min_horizontal(
                    pl.col("strength_gap").floor(),
                    (pl.col("money_reserves") * 0.20 / pl.col("_five_year_cost")).floor(),
                    pl.lit(250.0),
                ).cast(pl.Int64).alias("quantity")
            )
            .filter(pl.col("quantity") > 0)
            .with_columns(
                pl.lit(self.id).alias("policy_id"),
                pl.lit("procurement").alias("domain"),
                (
                    0.35
                    + (pl.col("strength_gap") / pl.col("_target_strength").clip(lower_bound=1.0)).clip(0.0, 1.0) * 0.40
                    + (pl.col("_combat_value") / pl.col("_five_year_cost")).clip(0.0, 1.0) * 0.25
                ).alias("utility"),
                pl.concat_str([pl.lit("procurement:"), pl.col("country_id")]).alias("conflict_key"),
                pl.lit("queue_production").alias("action_kind"),
                pl.lit("force_shortfall").alias("reason_code"),
                pl.lit(1).alias("quota"),
                pl.lit(None, dtype=pl.Utf8).alias("listing_id"),
            )
        )

    def _market_candidates(
        self,
        context: AITableContext,
        need: pl.LazyFrame,
    ) -> pl.LazyFrame:
        listings = context.table("unit_market_listings")
        designs = context.table("unit_designs")
        if listings is None or designs is None:
            return need.filter(pl.lit(False))
        listing_schema = set(listings.collect_schema().names())
        required = {"id", "seller_country_id", "design_id", "quantity", "price"}
        if not required.issubset(listing_schema):
            return need.filter(pl.lit(False))

        eligible = with_defaults(
            listings,
            {"eligibility": (pl.Utf8, "open")},
        )
        trade_members = treaty_member_rows(context).filter(
            (pl.col("status").str.to_lowercase() == "active")
            & (pl.col("treaty_type") == "weapons_trade")
        )
        market_access = (
            trade_members.select(
                "treaty_id",
                pl.col("country_id").alias("country_id"),
            )
            .join(
                trade_members.select(
                    "treaty_id",
                    pl.col("country_id").alias("seller_country"),
                ),
                on="treaty_id",
                how="inner",
            )
            .filter(pl.col("country_id") != pl.col("seller_country"))
            .select("country_id", "seller_country")
            .unique()
            .with_columns(pl.lit(True).alias("_market_access"))
        )
        own_cost = (
            designs.group_by(
                pl.col("country_id").cast(pl.Utf8).str.to_uppercase().alias("country_id")
            )
            .agg(pl.col("cost").cast(pl.Float64).min().alias("_own_unit_cost"))
        )
        market = eligible.select(
            pl.col("id").cast(pl.Utf8).alias("listing_id"),
            pl.col("seller_country_id").cast(pl.Utf8).str.to_uppercase().alias("seller_country"),
            pl.col("design_id").cast(pl.Utf8).alias("design_id"),
            pl.col("quantity").cast(pl.Int64).alias("available_quantity"),
            pl.col("price").cast(pl.Float64).clip(lower_bound=1.0).alias("unit_cost"),
            pl.col("eligibility").str.to_lowercase().alias("eligibility"),
        )
        return (
            need.join(market, how="cross")
            .filter(pl.col("country_id") != pl.col("seller_country"))
            .join(market_access, on=["country_id", "seller_country"], how="left")
            .filter(
                (pl.col("eligibility") == "open")
                | pl.col("_market_access").fill_null(False)
            )
            .join(own_cost, on="country_id", how="left")
            .filter(
                pl.col("_own_unit_cost").is_null()
                | (pl.col("unit_cost") < pl.col("_own_unit_cost"))
            )
            .with_columns(
                pl.min_horizontal(
                    pl.col("strength_gap").floor(),
                    pl.col("available_quantity"),
                    (pl.col("money_reserves") * 0.20 / (pl.col("unit_cost") * 1.50)).floor(),
                    pl.lit(250),
                ).cast(pl.Int64).alias("quantity")
            )
            .filter(pl.col("quantity") > 0)
            .with_columns(
                pl.lit(self.id).alias("policy_id"),
                pl.lit("procurement").alias("domain"),
                (
                    0.60
                    + (
                        (pl.col("_own_unit_cost").fill_null(pl.col("unit_cost") * 2.0) - pl.col("unit_cost"))
                        / pl.col("_own_unit_cost").fill_null(pl.col("unit_cost") * 2.0)
                    ).clip(0.0, 1.0) * 0.30
                    + (pl.col("strength_gap") / pl.col("_target_strength").clip(lower_bound=1.0)).clip(0.0, 1.0) * 0.10
                ).alias("utility"),
                pl.concat_str([pl.lit("procurement:"), pl.col("country_id")]).alias("conflict_key"),
                pl.lit("buy_market_unit").alias("action_kind"),
                pl.lit("cheaper_available_stock").alias("reason_code"),
                pl.lit(1).alias("quota"),
            )
        )

    def _allied_strength(
        self,
        context: AITableContext,
        strengths: pl.LazyFrame,
    ) -> pl.LazyFrame:
        members = treaty_member_rows(context).filter(
            (pl.col("status").str.to_lowercase() == "active")
            & (pl.col("treaty_type") == "alliance")
        )
        return (
            members.join(strengths, on="country_id", how="left")
            .group_by("treaty_id")
            .agg(pl.col("military_strength").fill_null(0.0).sum().alias("_treaty_strength"))
            .join(members.select("treaty_id", "country_id"), on="treaty_id", how="inner")
            .group_by("country_id")
            .agg(pl.col("_treaty_strength").max().alias("allied_strength"))
        )


class MilitaryOperationsPolicy:
    id = "military_operations"
    required_tables = frozenset({"countries", "regions", "units", "countries_wars"})
    cadence_days = 1

    def build_candidates(self, context: AITableContext) -> pl.LazyFrame:
        units = self._idle_units(context)
        return pl.concat(
            [
                self._attack_candidates(context, units),
                self._wartime_move_candidates(context, units),
                self._return_home_candidates(context, units),
            ],
            how="diagonal_relaxed",
        )

    def resolve_action(self, row: Mapping[str, Any]) -> GameAction | None:
        kind = str(row.get("action_kind") or "")
        if kind == "attack_unit":
            return ActionAttackUnit(
                "ai_system",
                str(row.get("unit_id") or ""),
                str(row.get("target_unit_id") or ""),
            )
        if kind == "move_unit":
            return ActionMoveUnit(
                "ai_system",
                str(row.get("unit_id") or ""),
                int(row.get("target_region_id") or 0),
                self._optional_float(row.get("target_latitude")),
                self._optional_float(row.get("target_longitude")),
            )
        return None

    def _idle_units(self, context: AITableContext) -> pl.LazyFrame:
        units = context.table("units")
        assert units is not None
        defaults = {
            "strength": (pl.Float64, 0.0),
            "current_region_id": (pl.Int32, 0),
            "latitude": (pl.Float64, 0.0),
            "longitude": (pl.Float64, 0.0),
            "is_moving": (pl.Boolean, False),
            "engagement_mode": (pl.Utf8, "idle"),
        }
        units = with_defaults(units, defaults)
        controlled = country_frame(context, 1).select("country_id")
        return (
            units.select(
                pl.col("id").cast(pl.Utf8).alias("unit_id"),
                pl.col("owner").cast(pl.Utf8).str.to_uppercase().alias("country_id"),
                "strength",
                "current_region_id",
                "latitude",
                "longitude",
                "is_moving",
                "engagement_mode",
            )
            .join(controlled, on="country_id", how="inner")
            .filter(
                ~pl.col("is_moving")
                & ~pl.col("engagement_mode").str.to_lowercase().is_in(["assault", "positional"])
                & (pl.col("strength") > 0.0)
            )
        )

    def _attack_candidates(
        self,
        context: AITableContext,
        units: pl.LazyFrame,
    ) -> pl.LazyFrame:
        all_units = context.table("units")
        assert all_units is not None
        defenders = with_defaults(
            all_units,
            {
                "strength": (pl.Float64, 0.0),
                "current_region_id": (pl.Int32, 0),
                "is_moving": (pl.Boolean, False),
                "engagement_mode": (pl.Utf8, "idle"),
            },
        ).select(
            pl.col("id").cast(pl.Utf8).alias("target_unit_id"),
            pl.col("owner").cast(pl.Utf8).str.to_uppercase().alias("target_country"),
            pl.col("strength").alias("target_strength"),
            "current_region_id",
            pl.col("is_moving").alias("_target_moving"),
            pl.col("engagement_mode").alias("_target_engagement"),
        )
        wars = active_war_pairs(context).select("source_country", "target_country").unique()
        return (
            units.join(defenders, on="current_region_id", how="inner")
            .filter(
                (pl.col("country_id") != pl.col("target_country"))
                & ~pl.col("_target_moving")
                & ~pl.col("_target_engagement").str.to_lowercase().is_in(["assault", "positional"])
                & (pl.col("strength") > pl.col("target_strength"))
            )
            .join(
                wars,
                left_on=["country_id", "target_country"],
                right_on=["source_country", "target_country"],
                how="inner",
            )
            .with_columns(
                pl.lit(self.id).alias("policy_id"),
                pl.lit("military_orders").alias("domain"),
                (
                    1.25
                    + (
                        pl.col("strength") / pl.col("target_strength").clip(lower_bound=1.0) - 1.0
                    ).clip(0.0, 2.0) * 0.25
                ).alias("utility"),
                pl.concat_str([pl.lit("unit-command:"), pl.col("unit_id")]).alias("conflict_key"),
                pl.lit("attack_unit").alias("action_kind"),
                pl.lit("local_superiority").alias("reason_code"),
                pl.lit(4).alias("quota"),
            )
        )

    def _wartime_move_candidates(
        self,
        context: AITableContext,
        units: pl.LazyFrame,
    ) -> pl.LazyFrame:
        regions = self._regions(context)
        wars = active_war_pairs(context)
        occupied_home = regions.filter(
            pl.col("owner_country").is_not_null()
            & pl.col("controller_country").is_not_null()
            & (pl.col("owner_country") != pl.col("controller_country"))
        ).select(
            pl.col("owner_country").alias("country_id"),
            pl.col("controller_country").alias("target_country"),
            "target_region_id",
            "target_latitude",
            "target_longitude",
            "_region_value",
            pl.lit(1.0).alias("_liberation_priority"),
        )
        enemy_regions = (
            wars.join(
                regions,
                left_on="target_country",
                right_on="owner_country",
                how="inner",
            )
            .select(
                pl.col("source_country").alias("country_id"),
                "target_country",
                "target_region_id",
                "target_latitude",
                "target_longitude",
                "_region_value",
                pl.lit(0.0).alias("_liberation_priority"),
            )
        )
        targets = pl.concat([occupied_home, enemy_regions], how="vertical_relaxed").unique(
            ["country_id", "target_region_id"], maintain_order=True
        )
        return (
            units.join(targets, on="country_id", how="inner")
            .filter(pl.col("current_region_id") != pl.col("target_region_id"))
            .with_columns(
                (
                    (pl.col("latitude") - pl.col("target_latitude")).pow(2)
                    + (pl.col("longitude") - pl.col("target_longitude")).pow(2)
                ).sqrt().alias("_distance")
            )
            .with_columns(
                pl.lit(self.id).alias("policy_id"),
                pl.lit("military_orders").alias("domain"),
                (
                    0.65
                    + pl.col("_liberation_priority") * 0.35
                    + pl.col("_region_value") * 0.15
                    + (1.0 / (1.0 + pl.col("_distance"))) * 0.15
                ).alias("utility"),
                pl.concat_str([pl.lit("unit-command:"), pl.col("unit_id")]).alias("conflict_key"),
                pl.lit("move_unit").alias("action_kind"),
                pl.when(pl.col("_liberation_priority") > 0.0)
                .then(pl.lit("liberate_home_region"))
                .otherwise(pl.lit("advance_to_valuable_region"))
                .alias("reason_code"),
                pl.lit(4).alias("quota"),
                pl.lit(None, dtype=pl.Utf8).alias("target_unit_id"),
            )
        )

    def _return_home_candidates(
        self,
        context: AITableContext,
        units: pl.LazyFrame,
    ) -> pl.LazyFrame:
        regions = self._regions(context)
        war_members = active_war_members(context).select("country_id").unique()
        home_regions = (
            regions.sort(
                ["owner_country", "_region_value", "target_region_id"],
                descending=[False, True, False],
            )
            .unique("owner_country", keep="first", maintain_order=True)
            .select(
                pl.col("owner_country").alias("country_id"),
                "target_region_id",
                "target_latitude",
                "target_longitude",
            )
        )

        all_units = context.table("units")
        assert all_units is not None
        unit_strength = with_defaults(
            all_units,
            {
                "strength": (pl.Float64, 0.0),
                "current_region_id": (pl.Int32, 0),
            },
        ).select(
            pl.col("owner").cast(pl.Utf8).str.to_uppercase().alias("country_id"),
            "current_region_id",
            "strength",
        )
        home_control = regions.select(
            pl.col("target_region_id").alias("current_region_id"),
            "owner_country",
        )
        shares = (
            unit_strength.join(home_control, on="current_region_id", how="left")
            .with_columns(
                pl.when(pl.col("country_id") == pl.col("owner_country"))
                .then(pl.col("strength"))
                .otherwise(0.0)
                .alias("_home_strength")
            )
            .group_by("country_id")
            .agg(
                pl.col("strength").sum().alias("_total_strength"),
                pl.col("_home_strength").sum().alias("_home_strength"),
            )
            .filter(
                pl.col("_home_strength")
                < pl.col("_total_strength").clip(lower_bound=1.0) * 0.50
            )
            .join(war_members, on="country_id", how="anti")
        )
        return (
            units.join(shares, on="country_id", how="inner")
            .join(home_regions, on="country_id", how="inner")
            .filter(pl.col("current_region_id") != pl.col("target_region_id"))
            .with_columns(
                pl.lit(self.id).alias("policy_id"),
                pl.lit("military_orders").alias("domain"),
                (
                    0.55
                    + (
                        0.50
                        - pl.col("_home_strength")
                        / pl.col("_total_strength").clip(lower_bound=1.0)
                    ).clip(0.0, 0.50)
                ).alias("utility"),
                pl.concat_str([pl.lit("unit-command:"), pl.col("unit_id")]).alias("conflict_key"),
                pl.lit("move_unit").alias("action_kind"),
                pl.lit("restore_home_posture").alias("reason_code"),
                pl.lit(4).alias("quota"),
                pl.lit(None, dtype=pl.Utf8).alias("target_unit_id"),
            )
        )

    def _regions(self, context: AITableContext) -> pl.LazyFrame:
        regions = context.table("regions")
        assert regions is not None
        defaults = {
            "owner": (pl.Utf8, ""),
            "controller": (pl.Utf8, ""),
            "latitude": (pl.Float64, 0.0),
            "longitude": (pl.Float64, 0.0),
            "area_km2": (pl.Float64, 0.0),
            "pop_14": (pl.Float64, 0.0),
            "pop_15_64": (pl.Float64, 0.0),
            "pop_65": (pl.Float64, 0.0),
        }
        regions = with_defaults(regions, defaults)
        return regions.select(
            pl.col("id").cast(pl.Int32).alias("target_region_id"),
            pl.col("owner").cast(pl.Utf8).str.to_uppercase().alias("owner_country"),
            pl.col("controller").cast(pl.Utf8).str.to_uppercase().alias("controller_country"),
            pl.col("latitude").alias("target_latitude"),
            pl.col("longitude").alias("target_longitude"),
            (
                (
                    pl.col("pop_14")
                    + pl.col("pop_15_64")
                    + pl.col("pop_65")
                    + pl.col("area_km2")
                ).log1p()
                / 25.0
            ).clip(0.0, 1.0).alias("_region_value"),
        )

    def _optional_float(self, value: Any) -> float | None:
        return None if value is None else float(value)
