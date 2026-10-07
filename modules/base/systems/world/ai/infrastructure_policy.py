from __future__ import annotations

from collections.abc import Mapping

import polars as pl

from modules.base.systems.world.ai.common import country_frame, with_defaults
from modules.base.systems.world.infrastructure_policy import configured_category_policies
from src.core.ai_framework import AITableContext, empty_candidates
from src.shared.actions import ActionInvestRegionalInfrastructure, GameAction


class InfrastructurePolicy:
    """Selects affordable, high-impact regional upgrades using server policies."""

    id = "infrastructure"
    required_tables = frozenset(
        {
            "countries",
            "regions",
            "regional_infrastructure",
            "infrastructure_projects",
            "infrastructure_damage_records",
        }
    )
    cadence_days = 14

    @staticmethod
    def _category_policy_value(
        policies: Mapping[str, Any], field_name: str, fallback: pl.Expr
    ) -> pl.Expr:
        expression = fallback
        for category_name, policy in policies.items():
            expression = pl.when(pl.col("category") == category_name).then(
                pl.lit(float(getattr(policy, field_name)))
            ).otherwise(expression)
        return expression

    def build_candidates(self, context: AITableContext) -> pl.LazyFrame:
        regions = context.table("regions")
        profiles = context.table("regional_infrastructure")
        projects = context.table("infrastructure_projects")
        damage = context.table("infrastructure_damage_records")
        if regions is None or profiles is None or projects is None or damage is None:
            return empty_candidates(
                {
                    "region_id": pl.Int64,
                    "category": pl.Utf8,
                    "target_level": pl.Float64,
                }
            )

        policy_config = context.globals.get("infrastructure_category_policies", {})
        policies = configured_category_policies(policy_config)
        category_names = tuple(policies)

        countries = with_defaults(
            country_frame(context, self.cadence_days),
            {
                "money_reserves": (pl.Float64, 0.0),
                "budget_infra_ratio": (pl.Float64, 0.0),
                "budget_telecom_ratio": (pl.Float64, 0.0),
                "budget_health_ratio": (pl.Float64, 0.0),
            },
        ).select(
            "country_id",
            pl.col("money_reserves").cast(pl.Float64, strict=False).fill_null(0.0).alias("money_reserves"),
            pl.col("budget_infra_ratio").cast(pl.Float64, strict=False).fill_null(0.0).alias("budget_infra_ratio"),
            pl.col("budget_telecom_ratio").cast(pl.Float64, strict=False).fill_null(0.0).alias("budget_telecom_ratio"),
            pl.col("budget_health_ratio").cast(pl.Float64, strict=False).fill_null(0.0).alias("budget_health_ratio"),
        )

        region_schema = regions.collect_schema()
        if not {"id", "owner"}.issubset(region_schema.names()):
            return empty_candidates(
                {
                    "region_id": pl.Int64,
                    "category": pl.Utf8,
                    "target_level": pl.Float64,
                }
            )
        region_columns = [
            pl.col("id").cast(pl.Int64, strict=False).alias("region_id"),
            pl.col("owner").cast(pl.Utf8, strict=False).str.strip_chars().str.to_uppercase().alias("country_id"),
        ]
        if "area_km2" in region_schema:
            area = pl.col("area_km2").cast(pl.Float64, strict=False).fill_null(0.0)
            scale = pl.when(area > 0.0).then((area / 1_000.0).sqrt()).otherwise(1.0).clip(0.25, 4.0)
        else:
            scale = pl.lit(1.0)
        region_columns.append(scale.alias("region_scale"))
        owned_regions = regions.select(region_columns).filter(pl.col("country_id") != "")

        active_projects = projects.filter(
            pl.col("status").cast(pl.Utf8, strict=False).str.to_lowercase().is_in(
                ["in_progress", "paused"]
            )
        ).select("region_id", "category").unique()
        profile_defaults = {
            "level": (pl.Float64, 0.0),
            "condition": (pl.Float64, 1.0),
            "capacity": (pl.Float64, 0.0),
            "maximum": (pl.Float64, 1.0),
        }
        profiles = with_defaults(profiles, profile_defaults).select(
            pl.col("region_id").cast(pl.Int64, strict=False).alias("region_id"),
            pl.col("category").cast(pl.Utf8, strict=False).str.to_lowercase().alias("category"),
            pl.col("level").cast(pl.Float64, strict=False).fill_null(0.0).alias("level"),
            pl.col("condition").cast(pl.Float64, strict=False).fill_null(1.0).alias("condition"),
            pl.col("capacity").cast(pl.Float64, strict=False).fill_null(0.0).alias("capacity"),
            pl.col("maximum").cast(pl.Float64, strict=False).fill_null(1.0).alias("maximum"),
        ).filter(pl.col("category").is_in(category_names))

        damage_schema = damage.collect_schema()
        if {"region_id", "category", "restoration_ceiling"}.issubset(damage_schema.names()):
            ceilings = (
                damage.group_by(
                    pl.col("region_id").cast(pl.Int64, strict=False).alias("region_id"),
                    pl.col("category").cast(pl.Utf8, strict=False).str.to_lowercase().alias("category"),
                )
                .agg(
                    pl.col("restoration_ceiling").cast(pl.Float64, strict=False)
                    .fill_null(0.0).max().alias("damage_ceiling")
                )
            )
            profiles = profiles.join(ceilings, on=["region_id", "category"], how="left")
        else:
            profiles = profiles.with_columns(pl.lit(None, dtype=pl.Float64).alias("damage_ceiling"))

        base = (
            profiles.join(owned_regions, on="region_id", how="inner")
            .join(countries, on="country_id", how="inner")
            .join(active_projects, on=["region_id", "category"], how="anti")
            .with_columns(
                pl.when(pl.col("category") == "telecom")
                .then(pl.col("budget_telecom_ratio"))
                .when(pl.col("category") == "utilities")
                .then(pl.col("budget_health_ratio"))
                .otherwise(pl.col("budget_infra_ratio"))
                .clip(0.0, 1.0).alias("_budget_ratio"),
                self._category_policy_value(
                    policies, "construction_cost_per_level", pl.lit(0.0)
                ).alias("_cost_per_level"),
                self._category_policy_value(
                    policies, "maximum", pl.col("maximum")
                ).alias("_policy_maximum"),
            )
            .filter((pl.col("_budget_ratio") > 0.0) & (pl.col("money_reserves") > 0.0))
            .with_columns(
                pl.min_horizontal(pl.col("_policy_maximum"), pl.col("level") + 0.05).alias("_upgrade_target"),
                (pl.col("level") / pl.col("_policy_maximum").clip(lower_bound=0.000001)).alias("_natural_ceiling"),
            )
            .with_columns(
                pl.when(pl.col("damage_ceiling").is_null())
                .then(pl.col("_natural_ceiling"))
                .otherwise(pl.min_horizontal(pl.col("_natural_ceiling"), pl.col("damage_ceiling")))
                .alias("_repair_ceiling")
            )
        )

        upgrade_cost = (
            (pl.col("_upgrade_target") - pl.col("level"))
            * pl.col("_cost_per_level")
            * pl.col("region_scale")
        )
        upgrade = (
            base.filter(
                (pl.col("capacity") < 0.85)
                & (pl.col("_upgrade_target") > pl.col("level"))
            )
            .with_columns(
                pl.col("_upgrade_target").alias("target_level"),
                upgrade_cost.alias("_quoted_cost"),
                pl.lit("upgrade").alias("action_kind"),
                (0.40 + (1.0 - pl.col("capacity")).clip(0.0, 1.0) * 0.45).alias("utility"),
            )
        )
        repair_cost = (
            (pl.col("_repair_ceiling") - pl.col("capacity"))
            * pl.col("_cost_per_level")
            * pl.col("region_scale")
        )
        repair = (
            base.filter(
                (pl.col("capacity") < pl.col("_repair_ceiling"))
                & (pl.col("level") > 0.0)
            )
            .with_columns(
                pl.col("_repair_ceiling").alias("target_level"),
                repair_cost.alias("_quoted_cost"),
                pl.lit("repair").alias("action_kind"),
                (0.55 + (pl.col("_repair_ceiling") - pl.col("capacity")).clip(0.0, 1.0) * 0.40).alias("utility"),
            )
        )
        return pl.concat([upgrade, repair], how="diagonal_relaxed").filter(
            (pl.col("_quoted_cost") > 0.0)
            & (pl.col("_quoted_cost") <= pl.col("money_reserves") * 0.20)
        ).with_columns(
            pl.lit(self.id).alias("policy_id"),
            pl.lit("infrastructure").alias("domain"),
            pl.concat_str([pl.lit("infrastructure:"), pl.col("country_id")]).alias("conflict_key"),
            pl.lit("invest_regional_infrastructure").alias("action_kind"),
            pl.lit("regional_capacity_gap").alias("reason_code"),
            pl.lit(1).alias("quota"),
        ).select(
            "country_id",
            "policy_id",
            "domain",
            "utility",
            "conflict_key",
            "action_kind",
            "reason_code",
            "quota",
            "region_id",
            "category",
            "target_level",
            "_quoted_cost",
        )

    def resolve_action(self, row: Mapping[str, Any]) -> GameAction | None:
        try:
            return ActionInvestRegionalInfrastructure(
                "ai_system",
                str(row["country_id"]),
                int(row["region_id"]),
                str(row["category"]),
                float(row["target_level"]),
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            return None
