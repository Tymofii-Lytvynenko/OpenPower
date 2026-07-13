from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import polars as pl

from modules.base.systems.world.ai.common import (
    active_war_pairs,
    canonical_pair_key,
    country_frame,
    country_strength,
    relation_matrix,
    treaty_member_rows,
    with_defaults,
)
from src.core.ai_framework import AITableContext
from src.shared.actions import (
    ActionCreateTreaty,
    ActionJoinTreaty,
    ActionLeaveTreaty,
    ActionRespondTreaty,
    GameAction,
)
from src.shared.treaties import treaty_definition


TREATY_PROFILES = (
    ("request_war_declaration", -1, 65.0, 60.0, 0.0),
    ("alliance", 1, 70.0, 62.0, 48.0),
    ("military_trespassing_right", 1, 45.0, 38.0, 20.0),
    ("request_military_presence_removal", -1, 20.0, 10.0, 0.0),
    ("annexation", -1, 55.0, 45.0, 0.0),
    ("free_region", -1, 20.0, 10.0, 0.0),
    ("cultural_exchanges", 1, 45.0, 38.0, 20.0),
    ("noble_cause", 1, 60.0, 52.0, 35.0),
    ("research_partnership", 1, 55.0, 48.0, 30.0),
    ("human_development_collaboration", 1, 55.0, 48.0, 30.0),
    ("economic_partnership", 1, 50.0, 43.0, 25.0),
    ("common_market", 1, 65.0, 57.0, 40.0),
    ("economic_aid", 1, 65.0, 58.0, 35.0),
    ("assume_foreign_debt", 1, 75.0, 68.0, 50.0),
    ("economic_embargo", -1, 65.0, 58.0, 45.0),
    ("weapons_trade", 1, 45.0, 38.0, 20.0),
    ("weapons_trade_embargo", -1, 70.0, 63.0, 50.0),
)


class DiplomacyPolicy:
    id = "diplomacy"
    required_tables = frozenset({"countries"})
    cadence_days = 1

    def build_candidates(self, context: AITableContext) -> pl.LazyFrame:
        return pl.concat(
            [
                self._response_candidates(context),
                self._proposal_candidates(context),
                self._join_candidates(context),
                self._leave_candidates(context),
            ],
            how="diagonal_relaxed",
        )

    def resolve_action(self, row: Mapping[str, Any]) -> GameAction | None:
        kind = str(row.get("action_kind") or "")
        country = str(row.get("country_id") or "")
        if kind == "respond_treaty":
            return ActionRespondTreaty(
                "ai_system",
                str(row.get("treaty_id") or ""),
                country,
                bool(row.get("accept")),
            )
        if kind == "join_treaty":
            return ActionJoinTreaty(
                "ai_system",
                str(row.get("treaty_id") or ""),
                country,
            )
        if kind == "leave_treaty":
            return ActionLeaveTreaty(
                "ai_system",
                str(row.get("treaty_id") or ""),
                country,
            )
        if kind != "create_treaty":
            return None

        target = str(row.get("target_country") or "")
        treaty_type = str(row.get("treaty_type") or "")
        definition = treaty_definition(treaty_type)
        if definition is None or not target:
            return None
        minimum_relation = float(row.get("proposal_relation") or -100.0)
        conditions = {
            "minimum_relation": minimum_relation if int(row.get("orientation") or 1) > 0 else -100.0,
            "allow_members_at_war": treaty_type in {
                "free_region",
                "annexation",
                "request_war_declaration",
                "request_military_presence_removal",
            },
        }
        return ActionCreateTreaty(
            "ai_system",
            country,
            target,
            treaty_type,
            definition.label,
            definition.description,
            side_a_country_tags=[country] if definition.two_sided else [],
            side_b_country_tags=[target] if definition.two_sided else [],
            member_country_tags=[country, target] if not definition.two_sided else [],
            conditions=conditions,
            open_to_new_members=definition.multi_member and definition.long_term,
        )

    def _response_candidates(self, context: AITableContext) -> pl.LazyFrame:
        pending = context.table("pending_treaties")
        controlled = country_frame(context, 1).select(
            "country_id",
            "money_reserves",
            "total_annual_revenue",
            "total_annual_expense",
            "human_dev",
            "stability",
        )
        if pending is None:
            return controlled.filter(pl.lit(False))

        schema = set(pending.collect_schema().names())
        required = {"id", "source_country_id", "treaty_type", "required_responses"}
        if not required.issubset(schema):
            return controlled.filter(pl.lit(False))

        profiles = self._profile_frame()
        relations = relation_matrix(context)
        responses = (
            pending.filter(
                pl.col("status").fill_null("pending").str.to_lowercase() == "pending"
                if "status" in schema
                else pl.lit(True)
            )
            .select(
                pl.col("id").cast(pl.Utf8).alias("treaty_id"),
                pl.col("source_country_id").cast(pl.Utf8).str.to_uppercase().alias("source_country"),
                pl.col("treaty_type").cast(pl.Utf8).str.to_lowercase().alias("treaty_type"),
                pl.col("required_responses"),
            )
            .explode("required_responses")
            .with_columns(
                pl.col("required_responses")
                .cast(pl.Utf8)
                .str.to_uppercase()
                .alias("country_id")
            )
            .join(controlled, on="country_id", how="inner")
            .join(profiles, on="treaty_type", how="left")
            .join(
                relations,
                left_on=["country_id", "source_country"],
                right_on=["source_country", "target_country"],
                how="left",
            )
            .with_columns(pl.col("relation").fill_null(0.0))
        )
        scored = self._score_treaty(responses, "response_relation")
        return scored.with_columns(
            pl.lit(self.id).alias("policy_id"),
            pl.concat_str([pl.lit("treaty-response:"), pl.col("treaty_id")]).alias("domain"),
            (1.0 + pl.col("_score").abs() * 0.01).alias("utility"),
            pl.concat_str(
                [pl.lit("treaty-response:"), pl.col("treaty_id"), pl.lit(":"), pl.col("country_id")]
            ).alias("conflict_key"),
            pl.lit("respond_treaty").alias("action_kind"),
            pl.when(pl.col("_accepted"))
            .then(pl.lit("proposal_accepted"))
            .otherwise(pl.lit("proposal_rejected"))
            .alias("reason_code"),
            pl.lit(1).alias("quota"),
            pl.col("_accepted").alias("accept"),
        )

    def _proposal_candidates(self, context: AITableContext) -> pl.LazyFrame:
        sources = country_frame(context, 30)
        relations = relation_matrix(context)
        profiles = self._profile_frame()
        countries = context.table("countries")
        if countries is None:
            return sources.filter(pl.lit(False))

        targets = with_defaults(
            countries,
            {
                "gdp": (pl.Float64, 0.0),
                "money_reserves": (pl.Float64, 0.0),
                "total_annual_revenue": (pl.Float64, 0.0),
                "total_annual_expense": (pl.Float64, 0.0),
                "human_dev": (pl.Float64, 0.5),
                "stability": (pl.Float64, 0.5),
                "research_capacity": (pl.Float64, 0.0),
                "budget_research_ratio": (pl.Float64, 0.0),
                "foreign_debt": (pl.Float64, 0.0),
            },
        ).select(
            pl.col("id").cast(pl.Utf8).str.to_uppercase().alias("target_country"),
            pl.col("gdp").alias("target_gdp"),
            pl.col("money_reserves").alias("target_reserves"),
            pl.col("total_annual_revenue").alias("target_revenue"),
            pl.col("total_annual_expense").alias("target_expense"),
            pl.col("human_dev").alias("target_human_dev"),
            pl.col("stability").alias("target_stability"),
            pl.max_horizontal(
                pl.col("research_capacity"),
                pl.col("gdp") * pl.col("budget_research_ratio"),
            ).alias("target_research"),
            pl.col("foreign_debt").alias("target_debt"),
        )
        strengths = country_strength(context)
        territory = self._territory_signals(context)
        duplicates = self._existing_pair_types(context)
        active_wars = active_war_pairs(context).select(
            canonical_pair_key().alias("_pair"),
            pl.lit(True).alias("_at_war"),
        ).unique()

        base = (
            sources.join(
                relations,
                left_on="country_id",
                right_on="source_country",
                how="inner",
            )
            .join(targets, on="target_country", how="inner")
            .join(
                strengths.rename({"military_strength": "source_strength"}),
                on="country_id",
                how="left",
            )
            .join(
                strengths.rename(
                    {"country_id": "target_country", "military_strength": "target_strength"}
                ),
                on="target_country",
                how="left",
            )
            .join(territory, on=["country_id", "target_country"], how="left")
            .join(profiles, how="cross")
            .with_columns(
                canonical_pair_key("country_id", "target_country").alias("_pair"),
                pl.col("source_controls_target").fill_null(0),
                pl.col("target_controls_source").fill_null(0),
                pl.col("target_units_in_source").fill_null(0),
                (
                    pl.col("source_strength").fill_null(0.0)
                    / pl.col("target_strength").fill_null(0.0).clip(lower_bound=1.0)
                ).alias("_strength_ratio"),
                (
                    (pl.col("total_annual_revenue") - pl.col("total_annual_expense"))
                    / pl.col("total_annual_revenue").abs().clip(lower_bound=1.0)
                ).alias("_financial_margin"),
                (
                    (pl.col("target_gdp") - pl.col("gdp")).abs()
                    / pl.max_horizontal(pl.col("target_gdp"), pl.col("gdp"), pl.lit(1.0))
                ).alias("_economic_complement"),
                (
                    (pl.col("target_human_dev") - pl.col("human_dev")).abs()
                ).alias("_development_gap"),
                (
                    (pl.col("target_research") - pl.col("research_capacity")).abs()
                    / pl.max_horizontal(
                        pl.col("target_research"),
                        pl.col("research_capacity"),
                        pl.lit(1.0),
                    )
                ).alias("_research_complement"),
            )
            .join(duplicates, on=["treaty_type", "_pair"], how="anti")
            .join(active_wars, on="_pair", how="left")
            .with_columns(pl.col("_at_war").fill_null(False))
        )
        scored = self._score_treaty(base, "proposal_relation")
        return (
            scored.filter(pl.col("_accepted") & self._proposal_gate())
            .with_columns(
                pl.lit(self.id).alias("policy_id"),
                pl.lit("diplomacy").alias("domain"),
                (
                    0.50
                    + (pl.col("_score").abs() / 100.0).clip(0.0, 0.35)
                    + pl.when(pl.col("orientation") > 0)
                    .then(
                        pl.max_horizontal(
                            pl.col("_economic_complement"),
                            pl.col("_development_gap"),
                            pl.col("_research_complement"),
                        )
                    )
                    .otherwise((pl.col("_strength_ratio") - 1.0).clip(0.0, 1.0))
                    * 0.15
                ).alias("utility"),
                pl.concat_str(
                    [pl.lit("treaty:"), pl.col("treaty_type"), pl.lit(":"), pl.col("_pair")]
                ).alias("conflict_key"),
                pl.lit("create_treaty").alias("action_kind"),
                pl.concat_str([pl.lit("propose_"), pl.col("treaty_type")]).alias("reason_code"),
                pl.lit(1).alias("quota"),
            )
        )

    def _join_candidates(self, context: AITableContext) -> pl.LazyFrame:
        treaties = context.table("countries_treaties")
        controlled = country_frame(context, 30)
        if treaties is None:
            return controlled.filter(pl.lit(False))
        schema = set(treaties.collect_schema().names())
        needed = {"id", "type", "open_to_new_members", "source_country_id"}
        if not needed.issubset(schema):
            return controlled.filter(pl.lit(False))

        existing_members = treaty_member_rows(context).select("treaty_id", "country_id")
        open_treaties = treaties.filter(
            pl.col("open_to_new_members").fill_null(False)
            & (pl.col("status").fill_null("active").str.to_lowercase() == "active")
        ).select(
            pl.col("id").cast(pl.Utf8).alias("treaty_id"),
            pl.col("type").cast(pl.Utf8).str.to_lowercase().alias("treaty_type"),
            pl.col("source_country_id").cast(pl.Utf8).str.to_uppercase().alias("sponsor_country"),
        )
        relations = relation_matrix(context)
        candidates = (
            controlled.join(open_treaties, how="cross")
            .join(existing_members, on=["treaty_id", "country_id"], how="anti")
            .join(
                self._profile_frame(),
                on="treaty_type",
                how="left",
            )
            .join(
                relations,
                left_on=["country_id", "sponsor_country"],
                right_on=["source_country", "target_country"],
                how="left",
            )
            .with_columns(pl.col("relation").fill_null(0.0))
        )
        scored = self._score_treaty(candidates, "response_relation")
        return scored.filter(
            pl.col("_accepted") & (pl.col("orientation") > 0)
        ).with_columns(
            pl.lit(self.id).alias("policy_id"),
            pl.lit("diplomacy").alias("domain"),
            (0.40 + pl.col("_score").clip(0.0, 100.0) / 200.0).alias("utility"),
            pl.concat_str(
                [pl.lit("treaty-join:"), pl.col("treaty_id"), pl.lit(":"), pl.col("country_id")]
            ).alias("conflict_key"),
            pl.lit("join_treaty").alias("action_kind"),
            pl.lit("join_beneficial_treaty").alias("reason_code"),
            pl.lit(1).alias("quota"),
        )

    def _leave_candidates(self, context: AITableContext) -> pl.LazyFrame:
        members = treaty_member_rows(context).filter(
            pl.col("status").str.to_lowercase() == "active"
        )
        controlled = country_frame(context, 30).select("country_id")
        peers = (
            members.rename({"country_id": "peer_country"})
            .join(members, on=["treaty_id", "treaty_type", "status", "open_to_new_members"])
            .filter(pl.col("country_id") != pl.col("peer_country"))
        )
        relations = relation_matrix(context)
        relationship = (
            peers.join(controlled, on="country_id", how="inner")
            .join(
                relations,
                left_on=["country_id", "peer_country"],
                right_on=["source_country", "target_country"],
                how="left",
            )
            .group_by(["treaty_id", "treaty_type", "country_id"])
            .agg(pl.col("relation").fill_null(0.0).mean().alias("relation"))
            .join(self._profile_frame(), on="treaty_type", how="left")
        )
        return relationship.filter(
            ((pl.col("orientation") > 0) & (pl.col("relation") < pl.col("stay_relation")))
            | ((pl.col("orientation") < 0) & (pl.col("relation") > -pl.col("stay_relation")))
        ).with_columns(
            pl.lit(self.id).alias("policy_id"),
            pl.lit("diplomacy").alias("domain"),
            (
                0.45
                + pl.when(pl.col("orientation") > 0)
                .then((pl.col("stay_relation") - pl.col("relation")) / 100.0)
                .otherwise((pl.col("relation") + pl.col("stay_relation")) / 100.0)
                .clip(0.0, 0.50)
            ).alias("utility"),
            pl.concat_str(
                [pl.lit("treaty-leave:"), pl.col("treaty_id"), pl.lit(":"), pl.col("country_id")]
            ).alias("conflict_key"),
            pl.lit("leave_treaty").alias("action_kind"),
            pl.lit("treaty_no_longer_useful").alias("reason_code"),
            pl.lit(1).alias("quota"),
        )

    def _score_treaty(self, frame: pl.LazyFrame, threshold_column: str) -> pl.LazyFrame:
        return frame.with_columns(
            pl.when(pl.col("orientation") > 0)
            .then(pl.col("relation"))
            .otherwise(-pl.col("relation"))
            .alias("_score")
        ).with_columns(
            (pl.col("_score") >= pl.col(threshold_column)).alias("_accepted")
        )

    def _proposal_gate(self) -> pl.Expr:
        treaty_type = pl.col("treaty_type")
        affordable = (
            (pl.col("money_reserves") > 0.0)
            & (pl.col("total_annual_revenue") >= pl.col("total_annual_expense") * 0.90)
        )
        return (
            pl.when(treaty_type == "request_war_declaration")
            .then((pl.col("_strength_ratio") > 1.25) & ~pl.col("_at_war"))
            .when(treaty_type == "request_military_presence_removal")
            .then(pl.col("target_units_in_source") > 0)
            .when(treaty_type == "annexation")
            .then(
                (pl.col("source_controls_target") > 0)
                & (pl.col("_strength_ratio") > 1.25)
            )
            .when(treaty_type == "free_region")
            .then(pl.col("target_controls_source") > 0)
            .when(treaty_type.is_in(["cultural_exchanges", "noble_cause"]))
            .then(affordable & ~pl.col("_at_war"))
            .when(treaty_type == "research_partnership")
            .then((pl.col("_research_complement") > 0.05) & ~pl.col("_at_war"))
            .when(treaty_type == "human_development_collaboration")
            .then((pl.col("_development_gap") > 0.03) & ~pl.col("_at_war"))
            .when(treaty_type.is_in(["economic_partnership", "common_market"]))
            .then((pl.col("_economic_complement") > 0.05) & ~pl.col("_at_war"))
            .when(treaty_type == "economic_aid")
            .then(
                affordable
                & ~pl.col("_at_war")
                & (pl.col("target_expense") > pl.col("target_revenue"))
            )
            .when(treaty_type == "assume_foreign_debt")
            .then(
                affordable
                & ~pl.col("_at_war")
                & (pl.col("target_debt") > 0.0)
                & (pl.col("money_reserves") > pl.col("target_debt"))
            )
            .when(treaty_type.is_in(["economic_embargo", "weapons_trade_embargo"]))
            .then(
                (pl.col("_financial_margin") > -0.10)
                & (pl.col("_strength_ratio") >= 0.80)
            )
            .otherwise(~pl.col("_at_war"))
        )

    def _territory_signals(self, context: AITableContext) -> pl.LazyFrame:
        regions = context.table("regions")
        units = context.table("units")
        empty = pl.DataFrame(
            schema={
                "country_id": pl.Utf8,
                "target_country": pl.Utf8,
                "source_controls_target": pl.UInt32,
                "target_controls_source": pl.UInt32,
                "target_units_in_source": pl.UInt32,
            }
        ).lazy()
        territory_frames: list[pl.LazyFrame] = []
        if regions is not None:
            schema = set(regions.collect_schema().names())
            if {"owner", "controller"}.issubset(schema):
                controlled = regions.filter(
                    pl.col("owner").is_not_null()
                    & pl.col("controller").is_not_null()
                    & (pl.col("owner") != pl.col("controller"))
                )
                source_controls = controlled.group_by(
                    pl.col("controller").cast(pl.Utf8).str.to_uppercase().alias("country_id"),
                    pl.col("owner").cast(pl.Utf8).str.to_uppercase().alias("target_country"),
                ).agg(
                    pl.len().cast(pl.UInt32).alias("source_controls_target")
                )
                target_controls = source_controls.select(
                    pl.col("target_country").alias("country_id"),
                    pl.col("country_id").alias("target_country"),
                    pl.col("source_controls_target").alias("target_controls_source"),
                )
                territory_frames.extend((source_controls, target_controls))
        if units is not None and regions is not None:
            unit_schema = set(units.collect_schema().names())
            region_schema = set(regions.collect_schema().names())
            if {"owner", "current_region_id"}.issubset(unit_schema) and {"id", "owner"}.issubset(region_schema):
                presence = (
                    units.join(
                        regions.select(
                            pl.col("id").alias("current_region_id"),
                            pl.col("owner").cast(pl.Utf8).str.to_uppercase().alias("country_id"),
                        ),
                        on="current_region_id",
                        how="inner",
                    )
                    .with_columns(
                        pl.col("owner").cast(pl.Utf8).str.to_uppercase().alias("target_country")
                    )
                    .filter(pl.col("country_id") != pl.col("target_country"))
                    .group_by(["country_id", "target_country"])
                    .agg(pl.len().cast(pl.UInt32).alias("target_units_in_source"))
                )
                territory_frames.append(presence)
        if not territory_frames:
            return empty
        return (
            pl.concat(territory_frames, how="diagonal_relaxed")
            .group_by(["country_id", "target_country"])
            .agg(
                pl.col("source_controls_target").fill_null(0).sum(),
                pl.col("target_controls_source").fill_null(0).sum(),
                pl.col("target_units_in_source").fill_null(0).sum(),
            )
        )

    def _existing_pair_types(self, context: AITableContext) -> pl.LazyFrame:
        active = self._membership_pair_types(treaty_member_rows(context))
        pending = self._membership_pair_types(treaty_member_rows(context, include_pending=True))
        return pl.concat([active, pending], how="vertical_relaxed").unique()

    def _membership_pair_types(self, members: pl.LazyFrame) -> pl.LazyFrame:
        return (
            members.select("treaty_id", "treaty_type", "country_id")
            .join(
                members.select(
                    "treaty_id",
                    "treaty_type",
                    pl.col("country_id").alias("_peer"),
                ),
                on=["treaty_id", "treaty_type"],
                how="inner",
            )
            .filter(pl.col("country_id") < pl.col("_peer"))
            .select(
                "treaty_type",
                canonical_pair_key("country_id", "_peer").alias("_pair"),
            )
            .unique()
        )

    def _profile_frame(self) -> pl.LazyFrame:
        return pl.DataFrame(
            TREATY_PROFILES,
            schema=[
                "treaty_type",
                "orientation",
                "proposal_relation",
                "response_relation",
                "stay_relation",
            ],
            orient="row",
        ).lazy()
