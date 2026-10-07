from __future__ import annotations

from collections.abc import Mapping
import math
from typing import Any

import polars as pl

from modules.base.systems.world.ai.common import country_frame, with_defaults
from src.core.ai_framework import AITableContext, empty_candidates
from src.shared.actions import ActionUpdateMigrationPolicy, GameAction


class MigrationPolicy:
    """Adapts non-player migration controls to observed service and mobility pressure."""

    id = "migration"
    required_tables = frozenset({"countries", "migration_policies"})
    cadence_days = 30

    def build_candidates(self, context: AITableContext) -> pl.LazyFrame:
        raw_policies = context.table("migration_policies")
        if raw_policies is None:
            return empty_candidates()

        countries = with_defaults(country_frame(context, self.cadence_days), {
            "migration_pressure": (pl.Float64, 0.0),
            "unemployment_rate": (pl.Float64, 0.0),
        }).select(
            pl.col("id").cast(pl.Utf8).str.strip_chars().str.to_uppercase().alias("country_id"),
            pl.col("migration_pressure").cast(pl.Float64, strict=False).fill_null(0.0)
            .clip(0.0, 1.0).alias("migration_pressure"),
            pl.col("unemployment_rate").cast(pl.Float64, strict=False).fill_null(0.0)
            .clip(0.0, 1.0).alias("unemployment_rate"),
        )
        policy_columns = {
            "country_id": pl.Utf8,
            "migration_policy": pl.Utf8,
            "border_policy": pl.Utf8,
            "entry_rate": pl.Float64,
            "exit_rate": pl.Float64,
            "asylum_rate": pl.Float64,
            "family_reunification_rate": pl.Float64,
            "skilled_worker_preference": pl.Float64,
            "enforcement_strength": pl.Float64,
        }
        policy_schema = set(raw_policies.collect_schema().names())
        if not {"country_id", "migration_policy", "border_policy"}.issubset(policy_schema):
            return empty_candidates()
        policy_expressions = [
            pl.col("country_id").cast(pl.Utf8).str.strip_chars().str.to_uppercase().alias("country_id"),
            pl.col("migration_policy").cast(pl.Utf8).str.to_lowercase(),
            pl.col("border_policy").cast(pl.Utf8).str.to_lowercase(),
        ]
        defaults = {
            "entry_rate": 0.5,
            "exit_rate": 0.5,
            "asylum_rate": 0.25,
            "family_reunification_rate": 0.5,
            "skilled_worker_preference": 0.0,
            "enforcement_strength": 0.5,
        }
        for column, dtype in policy_columns.items():
            if column not in {"country_id", "migration_policy", "border_policy"}:
                if column in policy_schema:
                    policy_expressions.append(
                        pl.col(column).cast(dtype, strict=False).fill_null(defaults[column]).alias(column)
                    )
                else:
                    policy_expressions.append(pl.lit(defaults[column], dtype=dtype).alias(column))
        policies = raw_policies.select(policy_expressions)

        signals = context.table("migration_signals")
        if signals is None:
            signal_frame = pl.DataFrame(schema={
                "country_id": pl.Utf8,
                "service_pressure": pl.Float64,
                "political_pressure": pl.Float64,
            }).lazy()
        else:
            signal_schema = set(signals.collect_schema().names())
            if "country_id" not in signal_schema:
                signal_frame = pl.DataFrame(schema={
                    "country_id": pl.Utf8,
                    "service_pressure": pl.Float64,
                    "political_pressure": pl.Float64,
                }).lazy()
            else:
                signal_frame = signals.select(
                    pl.col("country_id").cast(pl.Utf8).str.strip_chars().str.to_uppercase().alias("country_id"),
                    *[
                        pl.col(column).cast(pl.Float64, strict=False).fill_null(0.0)
                        .clip(0.0, 1.0).alias(column)
                        if column in signal_schema
                        else pl.lit(0.0, dtype=pl.Float64).alias(column)
                        for column in ("service_pressure", "political_pressure")
                    ],
                )

        joined = countries.join(policies, on="country_id", how="inner").join(
            signal_frame, on="country_id", how="left"
        ).with_columns(
            pl.col("service_pressure").fill_null(0.0),
            pl.col("political_pressure").fill_null(0.0),
        )
        terms = context.globals.get("migration_ai_terms", {})
        terms = terms if isinstance(terms, Mapping) else {}
        service_threshold = self._bounded(terms.get("service_pressure_threshold"), 0.0, 1.0, 0.7)
        migration_threshold = self._bounded(terms.get("migration_pressure_threshold"), 0.0, 1.0, 0.6)
        service_stress = pl.col("service_pressure") >= service_threshold
        mobility_stress = (
            (pl.col("migration_pressure") >= migration_threshold)
            & (pl.col("service_pressure") < service_threshold)
        )
        target_migration = (
            pl.when(service_stress).then(pl.lit("restricted"))
            .when(mobility_stress).then(pl.lit("open"))
            .otherwise(pl.lit("managed"))
        )
        target_border = (
            pl.when(service_stress).then(pl.lit("managed"))
            .when(mobility_stress).then(pl.lit("open"))
            .otherwise(pl.lit("managed"))
        )
        entry_rate = (
            pl.when(service_stress)
            .then((1.0 - pl.col("service_pressure") * 0.75).clip(0.1, 1.0))
            .when(mobility_stress)
            .then(pl.lit(0.7))
            .otherwise(pl.lit(0.5))
        )
        exit_rate = (
            pl.when(mobility_stress)
            .then((0.6 + pl.col("unemployment_rate") * 0.4).clip(0.0, 1.0))
            .otherwise(pl.lit(0.5))
        )
        candidates = joined.with_columns(
            target_migration.alias("_target_migration_policy"),
            target_border.alias("_target_border_policy"),
            entry_rate.alias("_target_entry_rate"),
            exit_rate.alias("_target_exit_rate"),
        ).filter(
            (service_stress | mobility_stress)
            & (
                (pl.col("migration_policy") != pl.col("_target_migration_policy"))
                | (pl.col("border_policy") != pl.col("_target_border_policy"))
                | ((pl.col("entry_rate") - pl.col("_target_entry_rate")).abs() > 0.01)
                | ((pl.col("exit_rate") - pl.col("_target_exit_rate")).abs() > 0.01)
            )
        ).with_columns(
            pl.lit(self.id).alias("policy_id"),
            pl.lit("migration").alias("domain"),
            (0.7 + pl.max_horizontal("service_pressure", "political_pressure") * 0.3).alias("utility"),
            pl.concat_str([pl.lit("migration-policy:"), pl.col("country_id")]).alias("conflict_key"),
            pl.lit("update_migration_policy").alias("action_kind"),
            pl.when(service_stress).then(pl.lit("service_capacity_pressure"))
            .otherwise(pl.lit("mobility_pressure")).alias("reason_code"),
            pl.lit(1).alias("quota"),
            pl.col("_target_migration_policy").alias("migration_policy"),
            pl.col("_target_border_policy").alias("border_policy"),
            pl.col("_target_entry_rate").alias("entry_rate"),
            pl.col("_target_exit_rate").alias("exit_rate"),
            pl.lit(max(0, int(context.total_minutes))).alias("effective_at_minute"),
        ).drop(
            "_target_migration_policy", "_target_border_policy", "_target_entry_rate", "_target_exit_rate"
        )

        transitions = context.table("migration_policy_transitions")
        if transitions is not None and {"country_id", "status"}.issubset(transitions.collect_schema().names()):
            scheduled = transitions.filter(pl.col("status") == "scheduled").select(
                pl.col("country_id").cast(pl.Utf8).str.strip_chars().str.to_uppercase().alias("country_id")
            ).unique()
            candidates = candidates.join(scheduled, on="country_id", how="anti")
        return candidates

    def resolve_action(self, row: Mapping[str, Any]) -> GameAction | None:
        if str(row.get("action_kind") or "") != "update_migration_policy":
            return None
        country_id = str(row.get("country_id") or "").strip().upper()
        if not country_id:
            return None
        return ActionUpdateMigrationPolicy(
            player_id="ai_system",
            country_tag=country_id,
            migration_policy=str(row.get("migration_policy") or "managed"),
            border_policy=str(row.get("border_policy") or "managed"),
            entry_rate=self._bounded(row.get("entry_rate"), 0.0, 1.0, 0.5),
            exit_rate=self._bounded(row.get("exit_rate"), 0.0, 1.0, 0.5),
            effective_at_minute=max(0, int(self._bounded(row.get("effective_at_minute"), 0.0, 2**62, 0.0))),
        )

    @staticmethod
    def _bounded(value: Any, minimum: float, maximum: float, default: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        if not math.isfinite(number):
            return default
        return min(max(number, minimum), maximum)
