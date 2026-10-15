from __future__ import annotations

import math
from typing import Any

import polars as pl

from modules.base.systems.world.infrastructure_policy import (
    InfrastructureCategoryPolicy,
    apply_infrastructure_damage,
    build_initial_profiles,
    calculate_infrastructure_capacity,
    configured_category_policies,
    depreciate_infrastructure_condition,
    quote_infrastructure_cost,
    quote_infrastructure_duration,
)
from modules.base.systems.military.authority_policy import player_controls_country
from src.shared.actions import (
    ActionCancelInfrastructureProject,
    ActionInvestRegionalInfrastructure,
)
from src.shared.events import EventRandomEventTriggered
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase


ACTIVE_PROJECT_STATUSES = frozenset({"in_progress", "paused"})
REGION_OUTPUT_COLUMNS = (
    "transport_access",
    "utilities_capacity",
    "industrial_access",
    "telecom_capacity",
    "infrastructure",
    "infrastructure_health",
    "communications",
    "health_capacity",
)
EVENT_INFRASTRUCTURE_CATEGORIES = {
    "infrastructure_transport": "transport",
    "infrastructure_utilities": "utilities",
    "infrastructure_industrial": "industrial",
    "infrastructure_telecom": "telecom",
}


class InfrastructureSystem(ISystem):
    """Owns regional infrastructure projects and publishes bounded read models."""

    access = SystemAccess(
        reads=frozenset(
            {
                "countries",
                "regions",
                "regional_infrastructure",
                "infrastructure_projects",
                "infrastructure_damage_records",
                "strategic_impacts",
                "occupations",
                "random_event_effects",
            }
        ),
        writes=frozenset(
            {
                "countries",
                "regions",
                "regional_infrastructure",
                "infrastructure_projects",
                "infrastructure_damage_records",
                "random_event_effects",
            }
        ),
        handles=frozenset(
            {ActionInvestRegionalInfrastructure, ActionCancelInfrastructureProject}
        ),
        phase=SystemPhase.POST_PROCESS,
    )

    @property
    def id(self) -> str:
        return "base.infrastructure"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.bootstrap", "base.strategic_warfare"]

    def update(self, state: GameState, delta_time: float) -> None:
        required = {
            "countries",
            "regions",
            "regional_infrastructure",
            "infrastructure_projects",
            "infrastructure_damage_records",
        }
        if not required.issubset(state.tables):
            return

        now = max(0, int(state.time.total_minutes))
        policies = configured_category_policies(
            state.globals.get("infrastructure_category_policies")
        )
        if self._can_refresh_read_models_without_mutable_rows(
            state, now, policies
        ):
            self._refresh_read_models_from_frames(state, policies)
            self._advance_projects_from_frames(state, now, policies)
            self._depreciate_profiles_from_frames(state, policies, now)
            self._materialize_read_models_from_frames(state, state.get_table("regional_infrastructure"))
            state.globals["infrastructure_last_update_minute"] = now
            return

        profile_rows = state.get_table("regional_infrastructure").to_dicts()
        project_rows = state.get_table("infrastructure_projects").to_dicts()
        damage_rows = state.get_table("infrastructure_damage_records").to_dicts()

        profile_rows = self._seed_profiles(state, profile_rows, policies, now)
        self._normalize_profiles(profile_rows, policies)
        self._advance_projects(
            state, profile_rows, project_rows, damage_rows, now, policies
        )
        self._process_actions(state, profile_rows, project_rows, now, policies)
        profile_rows, damage_rows = self._apply_damage(
            state, profile_rows, damage_rows, now, policies
        )
        self._apply_depreciation(state, profile_rows, policies, now)

        self._write_rows(state, "regional_infrastructure", profile_rows)
        self._write_rows(state, "infrastructure_projects", project_rows)
        self._write_rows(state, "infrastructure_damage_records", damage_rows)
        self._materialize_read_models(state, profile_rows)
        state.globals["infrastructure_last_update_minute"] = now

    def _advance_projects_from_frames(
        self,
        state: GameState,
        now: int,
        policies: dict[str, InfrastructureCategoryPolicy],
    ) -> None:
        profiles = state.get_table("regional_infrastructure")
        project_frame = state.get_table("infrastructure_projects")
        if (
            profiles.is_empty()
            or project_frame.is_empty()
            or "status" not in project_frame.columns
        ):
            return

        project_rows = project_frame.to_dicts()
        active_indexes = [
            index
            for index, project in enumerate(project_rows)
            if str(project.get("status") or "") in ACTIVE_PROJECT_STATUSES
        ]
        if not active_indexes:
            return

        active_projects = [project_rows[index] for index in active_indexes]
        # A project can only complete the profile for its own region and category.
        active_keys = pl.DataFrame(
            [
                {
                    "region_id": int(project.get("region_id") or 0),
                    "category": str(project.get("category") or ""),
                }
                for project in active_projects
            ]
        ).with_columns(
            pl.col("region_id").cast(profiles.schema["region_id"], strict=False),
            pl.col("category").cast(profiles.schema["category"], strict=False),
        ).unique()
        profile_rows = profiles.join(
            active_keys,
            on=["region_id", "category"],
            how="inner",
            maintain_order="left",
        ).to_dicts()

        damage_frame = state.tables.get("infrastructure_damage_records")
        repair_may_complete = any(
            str(project.get("status") or "") == "in_progress"
            and str(project.get("project_type") or "upgrade") == "repair"
            and self._project_progress_after_update(project, now) >= 1.0
            for project in active_projects
        )
        damage_rows = (
            damage_frame.to_dicts()
            if repair_may_complete and damage_frame is not None
            else []
        )

        damage_changed = self._advance_projects(
            state,
            profile_rows,
            project_rows,
            damage_rows,
            now,
            policies,
            regions_by_id=self._project_regions_by_id(state, active_projects),
        )

        completed_projects = [
            project_rows[index]
            for index in active_indexes
            if str(project_rows[index].get("status") or "") == "completed"
        ]
        completed_keys = {
            (
                int(project.get("region_id") or 0),
                str(project.get("category") or ""),
            )
            for project in completed_projects
        }
        changed_profiles = [
            profile
            for profile in profile_rows
            if (
                int(profile.get("region_id") or 0),
                str(profile.get("category") or ""),
            ) in completed_keys
        ]
        if changed_profiles:
            state.update_table(
                "regional_infrastructure",
                self._update_project_profiles(profiles, changed_profiles),
            )
        self._write_rows(state, "infrastructure_projects", project_rows)
        if damage_changed:
            self._write_rows(state, "infrastructure_damage_records", damage_rows)

    @staticmethod
    def _project_regions_by_id(
        state: GameState,
        projects: list[dict[str, Any]],
    ) -> dict[int, dict[str, Any]]:
        regions = state.tables.get("regions")
        if regions is None or "id" not in regions.columns:
            return {}

        region_ids = sorted({int(project.get("region_id") or 0) for project in projects})
        if not region_ids:
            return {}
        id_expression = pl.col("id").cast(pl.Int64, strict=False)
        columns = ["id"] + (["owner"] if "owner" in regions.columns else [])
        return {
            int(row.get("id") or 0): row
            for row in regions.filter(id_expression.is_in(region_ids))
            .select(columns)
            .iter_rows(named=True)
        }

    @staticmethod
    def _update_project_profiles(
        profiles: pl.DataFrame,
        rows: list[dict[str, Any]],
    ) -> pl.DataFrame:
        key_columns = ("region_id", "category")
        updated_columns = (
            "level",
            "condition",
            "capacity",
            "last_change_minute",
            "last_source_type",
            "last_source_id",
        )
        update_columns = [column for column in updated_columns if column in profiles.columns]
        updates = pl.DataFrame(rows, infer_schema_length=None)
        for column, dtype in profiles.schema.items():
            if column in updates.columns:
                updates = updates.with_columns(pl.col(column).cast(dtype, strict=False))
        updates = updates.select(*key_columns, *update_columns).unique(
            subset=list(key_columns),
            keep="last",
            maintain_order=True,
        ).with_columns(pl.lit(True).alias("__project_update_exists"))
        updates = updates.rename(
            {column: f"__project_{column}" for column in update_columns}
        )
        merged = profiles.join(
            updates,
            on=list(key_columns),
            how="left",
            maintain_order="left",
        ).with_columns(
            pl.when(pl.col("__project_update_exists").fill_null(False))
            .then(pl.col(f"__project_{column}"))
            .otherwise(pl.col(column))
            .alias(column)
            for column in update_columns
        )
        return merged.drop(
            ["__project_update_exists", *(f"__project_{column}" for column in update_columns)]
        )

    def _can_refresh_read_models_without_mutable_rows(
        self,
        state: GameState,
        now: int,
        policies: dict[str, InfrastructureCategoryPolicy],
    ) -> bool:
        profiles = state.tables.get("regional_infrastructure")
        regions = state.tables.get("regions")
        projects = state.tables.get("infrastructure_projects")
        impacts = state.tables.get("strategic_impacts")
        if (
            profiles is None
            or regions is None
            or projects is None
            or any(
                isinstance(action, (ActionInvestRegionalInfrastructure, ActionCancelInfrastructureProject))
                for action in state.current_actions
            )
            or (impacts is not None and not impacts.is_empty())
            or any(isinstance(event, EventRandomEventTriggered) for event in state.events)
            or self._has_due_random_event_effects(state, now)
        ):
            return False
        return self._has_complete_profile_coverage(profiles, regions, policies)

    @staticmethod
    def _has_due_random_event_effects(state: GameState, now: int) -> bool:
        effects = state.tables.get("random_event_effects")
        if effects is None or effects.is_empty():
            return False
        infrastructure_categories = [
            "infrastructure_transport",
            "infrastructure_utilities",
            "infrastructure_industrial",
            "infrastructure_telecom",
        ]
        return not effects.filter(
            pl.col("category").is_in(infrastructure_categories)
            & (
                pl.col("mitigation_pending")
                | (
                    (pl.col("status") == "pending")
                    & (pl.col("starts_at_minute") <= now)
                    & (pl.col("expires_at_minute") > now)
                )
            )
        ).is_empty()

    @staticmethod
    def _has_complete_profile_coverage(
        profiles: pl.DataFrame,
        regions: pl.DataFrame,
        policies: dict[str, InfrastructureCategoryPolicy],
    ) -> bool:
        if (
            profiles.is_empty()
            or regions.is_empty()
            or "region_id" not in profiles.columns
            or "category" not in profiles.columns
            or "id" not in regions.columns
            or profiles.height != regions.height * len(policies)
        ):
            return False

        profile_regions = profiles.select("region_id").unique()
        region_ids = regions.select(pl.col("id").alias("region_id")).unique()
        if (
            profile_regions.join(region_ids, on="region_id", how="anti").height
            or region_ids.join(profile_regions, on="region_id", how="anti").height
        ):
            return False

        coverage = {
            str(row["category"]): int(row["region_count"])
            for row in profiles.group_by("category").agg(
                pl.col("region_id").n_unique().alias("region_count")
            ).iter_rows(named=True)
        }
        return coverage == {category: regions.height for category in policies}

    @staticmethod
    def _policy_expression(
        policies: dict[str, InfrastructureCategoryPolicy],
        field_name: str,
        fallback: pl.Expr,
    ) -> pl.Expr:
        expression = fallback
        for category, policy in policies.items():
            expression = pl.when(pl.col("category") == category).then(
                pl.lit(float(getattr(policy, field_name)))
            ).otherwise(expression)
        return expression

    @staticmethod
    def _finite_column(name: str, default: float = 0.0) -> pl.Expr:
        value = pl.col(name).cast(pl.Float64, strict=False)
        return pl.when(value.is_finite()).then(value).otherwise(pl.lit(default))

    def _refresh_read_models_from_frames(
        self,
        state: GameState,
        policies: dict[str, InfrastructureCategoryPolicy],
    ) -> None:
        profiles = state.get_table("regional_infrastructure")
        known_category = pl.col("category").is_in(list(policies))
        current_maximum = self._finite_column("maximum", 1.0)
        maximum = self._policy_expression(policies, "maximum", current_maximum)
        current_baseline = self._finite_column("baseline", 0.0)
        baseline = self._policy_expression(policies, "baseline", current_baseline)
        current_maintenance_cost = self._finite_column(
            "maintenance_cost_per_level_month", 0.0
        )
        maintenance_cost = self._policy_expression(
            policies, "maintenance_cost_per_level_month", current_maintenance_cost
        )
        raw_level = self._finite_column("level")
        level = pl.when(raw_level < 0.0).then(pl.lit(0.0)).when(
            raw_level > maximum
        ).then(maximum).otherwise(raw_level)
        raw_condition = self._finite_column("condition")
        condition = pl.when(raw_condition < 0.0).then(pl.lit(0.0)).when(
            raw_condition > 1.0
        ).then(pl.lit(1.0)).otherwise(raw_condition)
        raw_maintenance = self._finite_column("maintenance_level")
        maintenance_level = pl.when(raw_maintenance < 0.0).then(pl.lit(0.0)).when(
            raw_maintenance > 1.0
        ).then(pl.lit(1.0)).otherwise(raw_maintenance)
        normalized = profiles.with_columns(
            pl.when(known_category).then(level).otherwise(pl.col("level")).alias("level"),
            pl.when(known_category).then(condition).otherwise(pl.col("condition")).alias("condition"),
            pl.when(known_category).then(
                pl.when(maximum > 0.0)
                .then((level / maximum) * condition)
                .otherwise(0.0)
            ).otherwise(pl.col("capacity")).alias("capacity"),
            pl.when(known_category).then(baseline).otherwise(pl.col("baseline")).alias("baseline"),
            pl.when(known_category).then(maximum).otherwise(pl.col("maximum")).alias("maximum"),
            pl.when(known_category).then(maintenance_cost).otherwise(
                pl.col("maintenance_cost_per_level_month")
            ).alias("maintenance_cost_per_level_month"),
            pl.when(known_category).then(maintenance_level).otherwise(
                pl.col("maintenance_level")
            ).alias("maintenance_level"),
            pl.when(known_category).then(
                pl.col("last_change_minute").cast(pl.Int64, strict=False).fill_null(0).clip(lower_bound=0)
            ).otherwise(pl.col("last_change_minute")).alias("last_change_minute"),
            pl.when(known_category).then(
                pl.col("last_source_type").cast(pl.String, strict=False).fill_null("baseline")
            ).otherwise(pl.col("last_source_type")).alias("last_source_type"),
            pl.when(known_category).then(
                pl.col("last_source_id").cast(pl.String, strict=False).fill_null("")
            ).otherwise(pl.col("last_source_id")).alias("last_source_id"),
        )
        state.update_table("regional_infrastructure", normalized)

    def _depreciate_profiles_from_frames(self, state, policies, now: int) -> None:
        previous = state.globals.get("infrastructure_last_update_minute")
        elapsed = max(0, now - int(previous)) if previous is not None else 0
        if not elapsed:
            return
        from modules.base.systems.world.infrastructure_policy import MINUTES_PER_YEAR

        profiles = state.get_table("regional_infrastructure")
        regions = state.get_table("regions")
        countries = state.get_table("countries")
        budget_fields = [name for name in ("budget_infra_ratio", "budget_telecom_ratio", "budget_health_ratio") if name in countries.columns]
        budgets = countries.select(pl.col("id").alias("_country"), *budget_fields)
        for name in ("budget_infra_ratio", "budget_telecom_ratio", "budget_health_ratio"):
            if name not in budgets.columns:
                fallback = "budget_infra_ratio" if name == "budget_health_ratio" else None
                budgets = budgets.with_columns((pl.col(fallback) if fallback else pl.lit(0.0)).alias(name))
        region_inputs = regions.select(
            pl.col("id").alias("region_id"), pl.col("owner").alias("_country"),
            (self._finite_column("infrastructure_use") if "infrastructure_use" in regions.columns else pl.lit(0.0)).clip(0.0, 2.0).alias("_use"),
        ).join(budgets, on="_country", how="left")
        occupations = state.tables.get("occupations")
        occupied = []
        if occupations is not None and not occupations.is_empty() and "region_id" in occupations.columns:
            if "occupation_status" in occupations.columns:
                occupations = occupations.filter(
                    pl.col("occupation_status").cast(pl.Utf8, strict=False).fill_null("").str.to_lowercase().is_in(["", "active"])
                )
            occupied = occupations.get_column("region_id").cast(pl.Int64, strict=False).fill_null(0).to_list()
        wear = max(0.0, min(2.0, self._finite(state.globals.get("infrastructure_occupation_use_multiplier", 0.5))))
        work = profiles.join(region_inputs, on="region_id", how="left", maintain_order="left")
        maintenance = pl.when(pl.col("category") == "telecom").then(
            self._finite_column("budget_telecom_ratio")
        ).when(pl.col("category") == "utilities").then(
            self._finite_column("budget_health_ratio")
        ).otherwise(self._finite_column("budget_infra_ratio")).clip(0.0, 1.0)
        use = (pl.col("_use").fill_null(0.0) + pl.when(pl.col("region_id").is_in(occupied)).then(wear).otherwise(0.0)).clip(0.0, 2.0)
        rate = self._policy_expression(policies, "annual_depreciation", pl.lit(0.0)).clip(0.0, 1.0)
        known = pl.col("category").is_in(list(policies))
        work = work.with_columns(
            pl.when(known).then(maintenance).otherwise(pl.col("maintenance_level")).alias("maintenance_level"),
            (pl.col("condition") - rate * (elapsed / MINUTES_PER_YEAR) * (1.0 + use) * (1.0 - maintenance)).clip(lower_bound=0.0).alias("_condition"),
        )
        changed = known & (pl.col("_condition") != pl.col("condition"))
        work = work.with_columns(
            pl.when(changed).then(now).otherwise(pl.col("last_change_minute")).alias("last_change_minute"),
            pl.when(changed).then(pl.lit("depreciation")).otherwise(pl.col("last_source_type")).alias("last_source_type"),
            pl.when(changed).then(pl.lit(f"game-minute:{now}")).otherwise(pl.col("last_source_id")).alias("last_source_id"),
            pl.when(changed).then(pl.col("_condition")).otherwise(pl.col("condition")).alias("condition"),
        ).with_columns(
            pl.when(known & (pl.col("maximum") > 0.0)).then((pl.col("level") / pl.col("maximum")) * pl.col("condition"))
            .when(known).then(0.0).otherwise(pl.col("capacity")).alias("capacity")
        ).select(profiles.columns)
        # Ordinary elapsed-time updates must not materialize every profile and
        # wide regional row in Python; project/damage ticks retain the row path.
        state.update_table("regional_infrastructure", work)

    def _materialize_read_models_from_frames(
        self,
        state: GameState,
        profiles: pl.DataFrame,
    ) -> None:
        regions = state.get_table("regions")
        category = pl.col("category")
        profile_projection = profiles.group_by("region_id").agg(
            pl.col("condition").mean().alias("infrastructure_health"),
            pl.col("capacity").filter(category == "transport").first().alias("_transport"),
            pl.col("capacity").filter(category == "utilities").first().alias("_utilities"),
            pl.col("capacity").filter(category == "industrial").first().alias("_industrial"),
            pl.col("capacity").filter(category == "telecom").first().alias("_telecom"),
        ).with_columns(
            pl.col("region_id").cast(regions.schema["id"], strict=False).alias("id")
        ).select(
            "id",
            pl.col("_transport").fill_null(0.0).alias("transport_access"),
            pl.col("_utilities").fill_null(0.0).alias("utilities_capacity"),
            pl.col("_industrial").fill_null(0.0).alias("industrial_access"),
            pl.col("_telecom").fill_null(0.0).alias("telecom_capacity"),
            pl.col("_transport").fill_null(0.0).alias("infrastructure"),
            pl.col("infrastructure_health").fill_null(0.0),
            pl.col("_telecom").fill_null(0.0).alias("communications"),
            pl.col("_utilities").fill_null(0.0).alias("health_capacity"),
        )
        dirty_region_ids = self._changed_row_ids(
            regions, profile_projection, "id", REGION_OUTPUT_COLUMNS
        )
        if not dirty_region_ids.is_empty():
            changed_projection = profile_projection.join(
                dirty_region_ids, on="id", how="semi"
            ).rename({column: f"_new_{column}" for column in REGION_OUTPUT_COLUMNS})
            updated_regions = regions
            for column in REGION_OUTPUT_COLUMNS:
                if column not in updated_regions.columns:
                    updated_regions = updated_regions.with_columns(pl.lit(0.0).alias(column))
            updated_regions = updated_regions.join(
                changed_projection, on="id", how="left", maintain_order="left"
            ).with_columns(
                pl.when(pl.col(f"_new_{column}").is_not_null())
                .then(pl.col(f"_new_{column}"))
                .otherwise(pl.col(column))
                .alias(column)
                for column in REGION_OUTPUT_COLUMNS
            ).drop([f"_new_{column}" for column in REGION_OUTPUT_COLUMNS])
            state.update_table("regions", updated_regions)

        countries = state.get_table("countries")
        if countries.is_empty() or "id" not in countries.columns:
            return
        region_columns = [
            pl.col("id").cast(profiles.schema["region_id"], strict=False).alias("region_id"),
            pl.col("owner").cast(pl.String, strict=False).str.strip_chars().str.to_uppercase().alias("_owner"),
        ]
        region_columns.append(self._regional_weight_expression(regions).alias("_weight"))
        regional_weights = regions.select(region_columns)
        weighted = profiles.select("region_id", "category", "capacity").join(
            regional_weights, on="region_id", how="inner"
        ).filter((pl.col("_owner") != "") & (pl.col("_weight") > 0.0))
        weighted_sums = []
        for name in ("transport", "telecom", "utilities", "industrial"):
            is_category = pl.col("category") == name
            weighted_sums.extend(
                [
                    pl.when(is_category).then(pl.col("capacity") * pl.col("_weight"))
                    .otherwise(0.0).sum().alias(f"_{name}_weighted"),
                    pl.when(is_category).then(pl.col("_weight"))
                    .otherwise(0.0).sum().alias(f"_{name}_weight"),
                ]
            )
        aggregates = weighted.group_by("_owner").agg(weighted_sums)
        aggregate_columns = [pl.col("_owner")]
        names = {
            "transport": "infrastructure_index",
            "telecom": "telecom_index",
            "utilities": "public_service_index",
            "industrial": "industrial_access_index",
        }
        for category_name, output_name in names.items():
            denominator = pl.col(f"_{category_name}_weight")
            aggregate_columns.append(
                pl.when(denominator > 0.0)
                .then(pl.col(f"_{category_name}_weighted") / denominator)
                .otherwise(0.0).alias(output_name)
            )
        aggregates = aggregates.select(aggregate_columns).rename({"_owner": "_infra_owner"})
        index_columns = list(names.values())
        country_base = countries.drop(
            [column for column in index_columns if column in countries.columns]
        ).with_columns(
            pl.col("id").cast(pl.String, strict=False).str.strip_chars().str.to_uppercase().alias("_infra_owner")
        )
        country_projection = country_base.join(
            aggregates, on="_infra_owner", how="left", maintain_order="left"
        ).with_columns(
            pl.col(column).fill_null(0.0).clip(0.0, 1.0).alias(column)
            for column in index_columns
        ).drop("_infra_owner")
        dirty_country_ids = self._changed_row_ids(
            countries, country_projection, "id", index_columns
        )
        if not dirty_country_ids.is_empty():
            changed_aggregates = country_projection.select("id", *index_columns).join(
                dirty_country_ids, on="id", how="semi"
            ).rename({column: f"_new_{column}" for column in index_columns})
            updated_countries = countries
            for column in index_columns:
                if column not in updated_countries.columns:
                    updated_countries = updated_countries.with_columns(pl.lit(0.0).alias(column))
            updated_countries = updated_countries.join(
                changed_aggregates, on="id", how="left", maintain_order="left"
            ).with_columns(
                pl.when(pl.col(f"_new_{column}").is_not_null())
                .then(pl.col(f"_new_{column}"))
                .otherwise(pl.col(column))
                .alias(column)
                for column in index_columns
            ).drop([f"_new_{column}" for column in index_columns])
            state.update_table("countries", updated_countries)

    @staticmethod
    def _changed_row_ids(
        current: pl.DataFrame,
        projected: pl.DataFrame,
        id_column: str,
        value_columns: tuple[str, ...] | list[str],
    ) -> pl.DataFrame:
        if current.is_empty() or projected.is_empty():
            return current.select(id_column).head(0)
        old_values = [
            (
                pl.col(column).cast(pl.Float64, strict=False)
                if column in current.columns
                else pl.lit(None, dtype=pl.Float64)
            ).alias(f"_old_{column}")
            for column in value_columns
        ]
        new_values = [
            pl.col(column).cast(pl.Float64, strict=False).fill_null(0.0).alias(f"_new_{column}")
            for column in value_columns
        ]
        comparison = current.select(pl.col(id_column), *old_values).join(
            projected.select(pl.col(id_column), *new_values),
            on=id_column,
            how="left",
        )
        differences = [
            (~pl.col(f"_old_{column}").is_finite())
            | (
                pl.col(f"_old_{column}") - pl.col(f"_new_{column}")
            ).abs().gt(1e-9)
            for column in value_columns
        ]
        return comparison.filter(
            pl.any_horizontal(differences).fill_null(True)
        ).select(id_column)

    def _seed_profiles(
        self,
        state: GameState,
        profiles: list[dict[str, Any]],
        policies: dict[str, InfrastructureCategoryPolicy],
        now: int,
    ) -> list[dict[str, Any]]:
        regions = state.tables.get("regions")
        if regions is None or regions.is_empty() or "id" not in regions.columns:
            return profiles

        existing = {
            (int(row.get("region_id") or 0), str(row.get("category") or ""))
            for row in profiles
        }
        missing_regions = [
            row
            for row in regions.iter_rows(named=True)
            if any(
                (int(row.get("id") or 0), category) not in existing
                for category in policies
            )
        ]
        if not missing_regions:
            return profiles

        candidates = build_initial_profiles(
            missing_regions,
            policies=policies,
            now_minute=now,
        )
        profiles.extend(
            row
            for row in candidates
            if (int(row["region_id"]), str(row["category"])) not in existing
        )
        profiles.sort(key=lambda row: (int(row["region_id"]), str(row["category"])))
        return profiles

    def _advance_projects(
        self,
        state: GameState,
        profiles: list[dict[str, Any]],
        projects: list[dict[str, Any]],
        damage_records: list[dict[str, Any]],
        now: int,
        policies: dict[str, InfrastructureCategoryPolicy],
        regions_by_id: dict[int, dict[str, Any]] | None = None,
    ) -> bool:
        regions = regions_by_id if regions_by_id is not None else self._region_rows(state)
        profiles_by_key = {
            (int(row.get("region_id") or 0), str(row.get("category") or "")): row
            for row in profiles
        }
        damage_records_changed = False
        for project in projects:
            if str(project.get("status") or "") not in ACTIVE_PROJECT_STATUSES:
                continue
            region_id = int(project.get("region_id") or 0)
            region = regions.get(region_id)
            owner = self._tag(project.get("country_id"))
            if region is None or self._tag(region.get("owner")) != owner:
                project.update(
                    status="paused",
                    updated_at_minute=now,
                    reason="Paused because the funding country no longer controls the region.",
                )
                continue

            previous_status = str(project.get("status") or "")
            if previous_status == "paused":
                project.update(
                    status="in_progress",
                    updated_at_minute=now,
                    reason="Resumed after the funding country regained control.",
                )
                continue

            progress = self._project_progress_after_update(project, now)
            project.update(progress=progress, updated_at_minute=now)
            if progress < 1.0:
                continue

            profile = profiles_by_key.get(
                (region_id, str(project.get("category") or ""))
            )
            if profile is None:
                project.update(
                    status="paused",
                    reason="Paused because its regional profile is unavailable.",
                )
                continue
            self._complete_project(profile, project)
            if str(project.get("project_type") or "upgrade") == "repair":
                capacity = self._finite(profile.get("capacity"))
                for record in damage_records:
                    if (
                        int(record.get("region_id") or 0) == region_id
                        and str(record.get("category") or "") == str(project.get("category") or "")
                        and capacity >= self._finite(record.get("restoration_ceiling")) - 1e-9
                    ):
                        if record.get("recovered") is not True:
                            record["recovered"] = True
                            damage_records_changed = True
            project.update(
                status="completed",
                progress=1.0,
                completed_at_minute=now,
                updated_at_minute=now,
                reason="Construction completed.",
            )
        return damage_records_changed

    @staticmethod
    def _project_progress_after_update(project: dict[str, Any], now: int) -> float:
        duration = max(1, int(project.get("duration_minutes") or 1))
        last_update = int(
            project.get("updated_at_minute") or project.get("started_at_minute") or 0
        )
        elapsed = max(0, now - last_update)
        return max(
            0.0,
            min(1.0, float(project.get("progress") or 0.0) + elapsed / duration),
        )

    @staticmethod
    def _normalize_profiles(
        profiles: list[dict[str, Any]],
        policies: dict[str, InfrastructureCategoryPolicy],
    ) -> None:
        for profile in profiles:
            category = str(profile.get("category") or "")
            policy = policies.get(category)
            if policy is None:
                continue
            maximum = policy.maximum
            level = max(0.0, min(maximum, InfrastructureSystem._finite(profile.get("level"))))
            condition = max(0.0, min(1.0, InfrastructureSystem._finite(profile.get("condition"))))
            profile.update(
                level=level,
                condition=condition,
                capacity=calculate_infrastructure_capacity(level, condition, maximum),
                baseline=policy.baseline,
                maximum=maximum,
                maintenance_cost_per_level_month=policy.maintenance_cost_per_level_month,
                maintenance_level=max(0.0, min(1.0, InfrastructureSystem._finite(profile.get("maintenance_level")))),
                last_change_minute=max(0, int(profile.get("last_change_minute") or 0)),
                last_source_type=str(profile.get("last_source_type") or "baseline"),
                last_source_id=str(profile.get("last_source_id") or ""),
            )

    @staticmethod
    def _complete_project(profile: dict[str, Any], project: dict[str, Any]) -> None:
        project_type = str(project.get("project_type") or "upgrade")
        maximum = max(0.000001, float(profile.get("maximum") or 1.0))
        if project_type == "repair":
            level = max(0.0, float(profile.get("level") or 0.0))
            if level <= 0.0:
                return
            target_capacity = min(
                float(project.get("target_level") or 0.0),
                float(project.get("restoration_ceiling") or level / maximum),
                level / maximum,
            )
            profile["condition"] = max(
                float(profile.get("condition") or 0.0),
                min(1.0, target_capacity * maximum / level),
            )
        else:
            profile["level"] = min(
                maximum,
                max(float(profile.get("level") or 0.0), float(project.get("target_level") or 0.0)),
            )
        profile["capacity"] = calculate_infrastructure_capacity(
            profile.get("level", 0.0), profile.get("condition", 1.0), maximum
        )
        profile["last_change_minute"] = int(project.get("updated_at_minute") or 0)
        profile["last_source_type"] = "project"
        profile["last_source_id"] = str(project.get("id") or "")

    def _process_actions(
        self,
        state: GameState,
        profiles: list[dict[str, Any]],
        projects: list[dict[str, Any]],
        now: int,
        policies: dict[str, InfrastructureCategoryPolicy],
    ) -> None:
        profiles_by_key = {
            (int(row.get("region_id") or 0), str(row.get("category") or "")): row
            for row in profiles
        }
        country_frame = state.tables.get("countries")
        country_rows = [] if country_frame is None else country_frame.to_dicts()
        country_by_id = {self._tag(row.get("id")): row for row in country_rows}
        original_countries = [dict(row) for row in country_rows]
        regions = self._region_rows(state)
        for action in state.current_actions:
            if isinstance(action, ActionInvestRegionalInfrastructure):
                self._invest(
                    state,
                    action,
                    profiles_by_key,
                    projects,
                    country_by_id,
                    regions,
                    now,
                    policies,
                )
            elif isinstance(action, ActionCancelInfrastructureProject):
                self._cancel(state, action, projects, country_by_id, now)

        if country_rows != original_countries:
            self._write_rows(state, "countries", country_rows)

    def _invest(
        self,
        state: GameState,
        action: ActionInvestRegionalInfrastructure,
        profiles: dict[tuple[int, str], dict[str, Any]],
        projects: list[dict[str, Any]],
        countries: dict[str, dict[str, Any]],
        regions: dict[int, dict[str, Any]],
        now: int,
        policies: dict[str, InfrastructureCategoryPolicy],
    ) -> None:
        country_id = self._tag(action.country_tag)
        category = str(action.category or "").strip().lower()
        region_id = int(action.region_id)
        profile = profiles.get((region_id, category))
        region = regions.get(region_id)
        country = countries.get(country_id)
        policy = policies.get(category)
        if profile is None or region is None or country is None or policy is None:
            self._reject(state, action, "The selected country, region, or category is unavailable.")
            return
        if not player_controls_country(state, action.player_id, country_id):
            self._reject(state, action, "The player cannot control the funding country.")
            return
        if self._tag(region.get("owner")) != country_id:
            self._reject(state, action, "Only the current regional owner may fund a domestic project.")
            return
        if any(
            int(project.get("region_id") or 0) == region_id
            and str(project.get("category") or "") == category
            and str(project.get("status") or "") in ACTIVE_PROJECT_STATUSES
            for project in projects
        ):
            self._reject(state, action, "An active project already targets this regional category.")
            return

        try:
            target = float(action.target_level)
            current_level = float(profile.get("level") or 0.0)
            current_capacity = float(profile.get("capacity") or 0.0)
            maximum = min(policy.maximum, float(profile.get("maximum") or policy.maximum))
            region_scale = self._regional_scale(region)
            if target > current_level:
                if target > maximum:
                    raise ValueError("Target level exceeds the stored regional category maximum.")
                project_type = "upgrade"
                start_level = current_level
                quote = quote_infrastructure_cost(
                    category, current_level, target, regional_scale=region_scale, policies=policies
                )
                duration = quote_infrastructure_duration(
                    category, current_level, target, regional_scale=region_scale, policies=policies
                )
                restoration_ceiling = 0.0
            else:
                project_type = "repair"
                ceiling = self._restoration_ceiling(
                    state, region_id, category, current_capacity, current_level, maximum
                )
                if not current_capacity < target <= min(ceiling, current_level / maximum):
                    raise ValueError("Repair target must exceed damaged capacity without crossing its restoration ceiling.")
                start_level = current_capacity
                quote = quote_infrastructure_cost(
                    category, current_capacity, target, regional_scale=region_scale, policies=policies
                )
                duration = quote_infrastructure_duration(
                    category, current_capacity, target, regional_scale=region_scale, policies=policies
                )
                restoration_ceiling = ceiling
        except (TypeError, ValueError, OverflowError) as exc:
            self._reject(state, action, str(exc) or "The target level is invalid.")
            return

        budget_ratio = self._budget_ratio(country, category)
        if budget_ratio <= 0.0:
            self._reject(state, action, "The country has no eligible infrastructure budget allocation.")
            return
        reserves = self._finite(country.get("money_reserves"))
        if quote <= 0.0 or reserves < quote:
            self._reject(state, action, "The country has insufficient available treasury reserves.")
            return

        project_id = self._next_project_id(projects, country_id, region_id, category, now)
        country["money_reserves"] = reserves - quote
        projects.append(
            {
                "id": project_id,
                "country_id": country_id,
                "player_id": str(action.player_id),
                "region_id": region_id,
                "category": category,
                "project_type": project_type,
                "funding_source": "treasury",
                "start_level": start_level,
                "target_level": target,
                "progress": 0.0,
                "cost_total": quote,
                "duration_minutes": duration,
                "started_at_minute": now,
                "updated_at_minute": now,
                "completed_at_minute": 0,
                "status": "in_progress",
                "reason": "Project funded and scheduled.",
                "restoration_ceiling": restoration_ceiling,
            }
        )
        self._record_result(state, action, "applied", "Project funded and scheduled.")

    def _cancel(
        self,
        state: GameState,
        action: ActionCancelInfrastructureProject,
        projects: list[dict[str, Any]],
        countries: dict[str, dict[str, Any]],
        now: int,
    ) -> None:
        project = next(
            (row for row in projects if str(row.get("id") or "") == str(action.project_id)),
            None,
        )
        if project is None or str(project.get("status") or "") not in ACTIVE_PROJECT_STATUSES:
            self._reject(state, action, "The infrastructure project is missing or no longer cancellable.")
            return
        if str(project.get("player_id") or "") != str(action.player_id):
            self._reject(state, action, "Only the player who owns the project may cancel it.")
            return

        progress = max(0.0, min(1.0, self._finite(project.get("progress"))))
        refund = max(0.0, self._finite(project.get("cost_total")) * (1.0 - progress))
        country = countries.get(self._tag(project.get("country_id")))
        if country is not None:
            country["money_reserves"] = self._finite(country.get("money_reserves")) + refund
        project.update(
            status="cancelled",
            updated_at_minute=now,
            reason=f"Cancelled by owner; uncompleted project value refunded ({refund:.2f}).",
        )
        self._record_result(state, action, "applied", project["reason"])

    def _apply_damage(
        self,
        state: GameState,
        profiles: list[dict[str, Any]],
        damage_records: list[dict[str, Any]],
        now: int,
        policies: dict[str, InfrastructureCategoryPolicy],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        profile_by_key = {
            (int(row.get("region_id") or 0), str(row.get("category") or "")): row
            for row in profiles
        }
        existing_ids = {str(row.get("id") or "") for row in damage_records}
        sources: list[tuple[str, str, int, str, float]] = []
        effect_id_by_source: dict[str, str] = {}
        consumed_effect_ids: set[str] = set()
        impacts = state.tables.get("strategic_impacts")
        if impacts is not None:
            for impact in impacts.iter_rows(named=True):
                region_id = int(impact.get("region_id") or 0)
                source_id = str(impact.get("id") or "")
                severity = max(0.0, min(1.0, self._finite(impact.get("severity"))))
                impact_category = str(impact.get("category") or "")
                target_category = {
                    "infrastructure": "transport",
                    "communications": "telecom",
                    "collateral_infrastructure": "transport",
                }.get(impact_category)
                target_categories = {target_category} if target_category else set()
                target_categories.update(
                    category
                    for category, policy in policies.items()
                    if impact_category in policy.damage_response
                    or "strategic" in policy.damage_response
                )
                for category in sorted(target_categories):
                    policy = policies.get(category)
                    if policy is None:
                        continue
                    response_factor = policy.damage_response.get(
                        impact_category,
                        policy.damage_response.get("strategic", 1.0),
                    )
                    sources.append(
                        (source_id, "strategic", region_id, category, severity * response_factor)
                    )

        event_effects = state.tables.get("random_event_effects")
        typed_event_ids: set[str] = set()
        mitigation_rows: list[dict[str, Any]] = []
        if event_effects is not None and not event_effects.is_empty():
            infrastructure_effects = event_effects.filter(
                pl.col("category").is_in(list(EVENT_INFRASTRUCTURE_CATEGORIES))
            )
            typed_event_ids = {
                str(value)
                for value in infrastructure_effects.get_column("event_id").to_list()
                if value
            }
            instances = state.tables.get("random_event_instances")
            event_types = {}
            if instances is not None and not instances.is_empty():
                event_types = {
                    str(row["id"]): str(row["event_type"])
                    for row in instances.select("id", "event_type").iter_rows(named=True)
                }
            due_effects = infrastructure_effects.filter(
                (pl.col("subject_type") == "region")
                & (pl.col("status") == "pending")
                & (pl.col("starts_at_minute") <= now)
                & (pl.col("expires_at_minute") > now)
            )
            for effect in due_effects.iter_rows(named=True):
                event_id = str(effect.get("event_id") or "")
                category = EVENT_INFRASTRUCTURE_CATEGORIES.get(str(effect.get("category") or ""))
                if not event_id or category is None:
                    continue
                region_id = self._integer(effect.get("subject_id"), 0)
                policy = policies.get(category)
                if policy is None:
                    continue
                event_type = event_types.get(event_id, "")
                response_factor = policy.damage_response.get(
                    event_type,
                    policy.damage_response.get("disaster", 1.0),
                )
                severity = max(
                    0.0,
                    min(1.0, self._finite(effect.get("magnitude")) * response_factor),
                )
                stable_id = f"disaster:{event_id}:{region_id}:{category}"
                effect_id_by_source[stable_id] = str(effect["id"])
                sources.append((event_id, "disaster", region_id, category, severity))
            mitigation_rows = infrastructure_effects.filter(
                pl.col("mitigation_pending")
                & pl.col("status").is_in(["pending", "active"])
            ).to_dicts()

        event_damage = {
            "earthquake": (("transport", 0.16), ("utilities", 0.18), ("industrial", 0.08), ("telecom", 0.10)),
            "flood": (("transport", 0.14), ("utilities", 0.16), ("industrial", 0.08)),
            "wildfire": (("utilities", 0.10), ("industrial", 0.14), ("telecom", 0.05)),
            "tornado": (("transport", 0.12), ("utilities", 0.12), ("telecom", 0.06)),
            "volcanic_eruption": (("transport", 0.12), ("utilities", 0.14), ("industrial", 0.10), ("telecom", 0.10)),
            "drought": (("utilities", 0.10), ("industrial", 0.06)),
            "epidemic": (("utilities", 0.06), ("telecom", 0.04)),
            "tsunami": (("transport", 0.16), ("utilities", 0.15), ("industrial", 0.06), ("telecom", 0.12)),
        }
        for event in state.events:
            if not isinstance(event, EventRandomEventTriggered):
                continue
            if str(event.event_id) in typed_event_ids:
                continue
            event_type = str(event.event_type)
            default_factors = dict(event_damage.get(event_type, ()))
            for category, policy in policies.items():
                damage_factor = policy.damage_response.get(
                    event_type,
                    policy.damage_response.get("disaster", default_factors.get(category, 0.0)),
                )
                if damage_factor <= 0.0:
                    continue
                sources.append(
                    (
                        str(event.event_id),
                        "disaster",
                        int(event.region_id),
                        category,
                        max(0.0, min(1.0, self._finite(event.severity) * damage_factor)),
                    )
                )

        # Stable order keeps attributed stacking reproducible across save/load and replay.
        sources.sort(key=lambda item: (item[0], item[2], item[3], item[1]))
        for source_id, source_type, region_id, category, severity in sources:
            profile = profile_by_key.get((region_id, category))
            if profile is None or severity <= 0.0:
                continue
            stable_id = f"{source_type}:{source_id}:{region_id}:{category}"
            if stable_id in existing_ids:
                effect_id = effect_id_by_source.get(stable_id)
                if effect_id:
                    consumed_effect_ids.add(effect_id)
                continue
            damaged, record = apply_infrastructure_damage(
                profile,
                source_id=stable_id,
                source_type=source_type,
                severity=severity,
                now_minute=now,
                existing_source_ids=existing_ids,
            )
            if record is None:
                continue
            record.update(
                id=stable_id,
                source_id=source_id,
                region_id=region_id,
                category=category,
                recovered=False,
            )
            profile.update(damaged)
            damage_records.append(record)
            existing_ids.add(stable_id)

            effect_id = effect_id_by_source.get(stable_id)
            if effect_id:
                consumed_effect_ids.add(effect_id)

        damage_by_id = {str(row.get("id") or ""): row for row in damage_records}
        for effect in mitigation_rows:
            event_id = str(effect.get("event_id") or "")
            category = EVENT_INFRASTRUCTURE_CATEGORIES.get(str(effect.get("category") or ""))
            if not event_id or category is None:
                continue
            region_id = self._integer(effect.get("subject_id"), 0)
            stable_id = f"disaster:{event_id}:{region_id}:{category}"
            record = damage_by_id.get(stable_id)
            profile = profile_by_key.get((region_id, category))
            if record is None or profile is None:
                continue
            old_severity = max(0.0, min(1.0, self._finite(record.get("severity"))))
            new_severity = max(0.0, min(1.0, self._finite(effect.get("magnitude"))))
            if new_severity < old_severity and old_severity < 1.0:
                remaining_damage_ratio = (1.0 - new_severity) / (1.0 - old_severity)
                condition = max(0.0, min(1.0, self._finite(profile.get("condition"))))
                condition = max(0.0, min(1.0, condition * remaining_damage_ratio))
                profile.update(
                    condition=condition,
                    capacity=calculate_infrastructure_capacity(
                        self._finite(profile.get("level")),
                        condition,
                        profile.get("maximum", 1.0),
                    ),
                    last_change_minute=now,
                    last_source_type="event_mitigation",
                    last_source_id=event_id,
                )
                record["severity"] = new_severity
            consumed_effect_ids.add(str(effect["id"]))

        if consumed_effect_ids and event_effects is not None:
            effect_ids = sorted(consumed_effect_ids)
            state.update_table(
                "random_event_effects",
                event_effects.with_columns(
                    pl.when(pl.col("id").is_in(effect_ids))
                    .then(pl.lit("active"))
                    .otherwise(pl.col("status"))
                    .alias("status"),
                    pl.when(pl.col("id").is_in(effect_ids))
                    .then(pl.lit(now, dtype=pl.Int64))
                    .otherwise(pl.col("last_applied_at_minute"))
                    .alias("last_applied_at_minute"),
                    pl.when(pl.col("id").is_in(effect_ids))
                    .then(pl.lit(False))
                    .otherwise(pl.col("mitigation_pending"))
                    .alias("mitigation_pending"),
                ),
            )
        damage_records.sort(key=lambda row: str(row.get("id") or ""))
        return profiles, damage_records

    def _apply_depreciation(
        self,
        state: GameState,
        profiles: list[dict[str, Any]],
        policies: dict[str, InfrastructureCategoryPolicy],
        now: int,
    ) -> None:
        previous = state.globals.get("infrastructure_last_update_minute")
        if previous is None:
            return
        elapsed = max(0, now - int(previous))
        if elapsed <= 0:
            return

        countries = {
            self._tag(row.get("id")): row
            for row in self._country_rows(state).values()
        }
        regions = self._region_rows(state)
        occupations = state.tables.get("occupations")
        occupied_regions = set()
        if occupations is not None and not occupations.is_empty():
            occupied_regions = {
                int(row.get("region_id") or 0)
                for row in occupations.iter_rows(named=True)
                if str(row.get("occupation_status") or "active").lower() == "active"
            }
        occupation_wear = max(
            0.0,
            min(2.0, self._finite(state.globals.get("infrastructure_occupation_use_multiplier", 0.5))),
        )
        for profile in profiles:
            category = str(profile.get("category") or "")
            policy = policies.get(category)
            region = regions.get(int(profile.get("region_id") or 0), {})
            if policy is None:
                continue
            country = countries.get(self._tag(region.get("owner")), {})
            maintenance = self._budget_ratio(country, category)
            use_factor = max(0.0, min(2.0, self._finite(region.get("infrastructure_use"))))
            if int(profile.get("region_id") or 0) in occupied_regions:
                use_factor = min(2.0, use_factor + occupation_wear)
            old_condition = float(profile.get("condition") or 0.0)
            new_condition = depreciate_infrastructure_condition(
                old_condition,
                elapsed,
                annual_rate=policy.annual_depreciation,
                maintenance_ratio=maintenance,
                use_factor=use_factor,
            )
            profile["maintenance_level"] = maintenance
            if new_condition == old_condition:
                continue
            profile["condition"] = new_condition
            profile["capacity"] = calculate_infrastructure_capacity(
                profile.get("level", 0.0), new_condition, profile.get("maximum", 1.0)
            )
            profile["last_change_minute"] = now
            profile["last_source_type"] = "depreciation"
            profile["last_source_id"] = f"game-minute:{now}"

    def _materialize_read_models(
        self,
        state: GameState,
        profiles: list[dict[str, Any]],
    ) -> None:
        regions = state.tables.get("regions")
        if regions is None or regions.is_empty() or "id" not in regions.columns:
            return
        by_region: dict[int, dict[str, dict[str, Any]]] = {}
        for profile in profiles:
            by_region.setdefault(int(profile.get("region_id") or 0), {})[
                str(profile.get("category") or "")
            ] = profile

        ids: list[Any] = []
        outputs: dict[str, list[float]] = {column: [] for column in REGION_OUTPUT_COLUMNS}
        region_aggregation_context: dict[int, tuple[str, float]] = {}
        for region in regions.iter_rows(named=True):
            region_id = int(region.get("id") or 0)
            region_aggregation_context[region_id] = (
                self._tag(region.get("owner")),
                self._regional_weight(region),
            )
            category_rows = by_region.get(region_id, {})
            transport = category_rows.get("transport", {})
            utilities = category_rows.get("utilities", {})
            industrial = category_rows.get("industrial", {})
            telecom = category_rows.get("telecom", {})
            conditions = [
                float(row.get("condition") or 0.0)
                for row in category_rows.values()
            ]
            capacity = {
                "transport_access": float(transport.get("capacity") or 0.0),
                "utilities_capacity": float(utilities.get("capacity") or 0.0),
                "industrial_access": float(industrial.get("capacity") or 0.0),
                "telecom_capacity": float(telecom.get("capacity") or 0.0),
                "infrastructure": float(transport.get("capacity") or 0.0),
                "infrastructure_health": sum(conditions) / len(conditions) if conditions else 0.0,
                "communications": float(telecom.get("capacity") or 0.0),
                "health_capacity": float(utilities.get("capacity") or 0.0),
            }
            ids.append(region["id"])
            for column, values in outputs.items():
                values.append(max(0.0, min(1.0, capacity[column])))

        projection = pl.DataFrame({"id": ids, **outputs}).with_columns(
            pl.col("id").cast(regions.schema["id"], strict=False)
        )
        # Legacy region tables can contain duplicate IDs; a duplicated projection
        # key would multiply those rows again on every read-model refresh.
        projection = projection.unique(subset=["id"], keep="first", maintain_order=True)
        base = regions.drop([column for column in REGION_OUTPUT_COLUMNS if column in regions.columns])
        state.update_table("regions", base.join(projection, on="id", how="left", maintain_order="left"))

        country_frame = state.tables.get("countries")
        if country_frame is None or country_frame.is_empty() or "id" not in country_frame.columns:
            return
        country_rows = country_frame.to_dicts()
        aggregate_totals: dict[str, dict[str, list[float]]] = {}
        for profile in profiles:
            context = region_aggregation_context.get(
                int(profile.get("region_id") or 0)
            )
            if context is None:
                continue
            owner, weight = context
            category = str(profile.get("category") or "")
            if not owner or weight <= 0.0:
                continue
            buckets = aggregate_totals.setdefault(owner, {})
            weighted_sum, total_weight = buckets.setdefault(category, [0.0, 0.0])
            buckets[category] = [
                weighted_sum + max(0.0, min(1.0, self._finite(profile.get("capacity")))) * weight,
                total_weight + weight,
            ]
        for country in country_rows:
            owner = self._tag(country.get("id"))
            aggregates = {
                category: weighted_sum / total_weight if total_weight > 0.0 else 0.0
                for category, (weighted_sum, total_weight) in aggregate_totals.get(owner, {}).items()
            }
            country.update(
                infrastructure_index=aggregates.get("transport", 0.0),
                telecom_index=aggregates.get("telecom", 0.0),
                public_service_index=aggregates.get("utilities", 0.0),
                industrial_access_index=aggregates.get("industrial", 0.0),
            )
        self._write_rows(state, "countries", country_rows)

    def _restoration_ceiling(
        self,
        state: GameState,
        region_id: int,
        category: str,
        current_capacity: float,
        current_level: float,
        maximum: float,
    ) -> float:
        records = state.tables.get("infrastructure_damage_records")
        ceilings = [
            float(row.get("restoration_ceiling") or 0.0)
            for row in ([] if records is None else records.iter_rows(named=True))
            if int(row.get("region_id") or 0) == region_id
            and str(row.get("category") or "") == category
        ]
        natural_ceiling = current_level / max(maximum, 0.000001)
        return max(current_capacity, min(natural_ceiling, max(ceilings, default=natural_ceiling)))

    @staticmethod
    def _regional_scale(region: dict[str, Any]) -> float:
        area = max(0.0, InfrastructureSystem._finite(region.get("area_km2")))
        if area <= 0.0:
            return 1.0
        return max(0.25, min(4.0, math.sqrt(area / 1_000.0)))

    @staticmethod
    def _regional_weight(region: dict[str, Any]) -> float:
        cohort_columns = ("pop_14", "pop_15_64", "pop_65")
        if all(column in region for column in cohort_columns):
            # Cohorts are authoritative; cached aggregate population can lag migration transfers.
            return sum(
                max(0.0, InfrastructureSystem._finite(region.get(column)))
                for column in cohort_columns
            )
        for column in ("population", "total_population"):
            population = max(0.0, InfrastructureSystem._finite(region.get(column)))
            if population > 0.0:
                return population
        ages = sum(
            max(0.0, InfrastructureSystem._finite(region.get(column)))
            for column in cohort_columns
            if column in region
        )
        if ages > 0.0:
            return ages
        return max(0.0, InfrastructureSystem._finite(region.get("area_km2")))

    @staticmethod
    def _regional_weight_expression(regions: pl.DataFrame) -> pl.Expr:
        cohort_columns = ("pop_14", "pop_15_64", "pop_65")
        if all(column in regions.columns for column in cohort_columns):
            return pl.sum_horizontal([
                InfrastructureSystem._finite_column(column).clip(lower_bound=0.0)
                for column in cohort_columns
            ])

        candidates = [
            InfrastructureSystem._finite_column(column)
            for column in ("population", "total_population")
            if column in regions.columns
        ]
        partial_cohorts = [column for column in cohort_columns if column in regions.columns]
        if partial_cohorts:
            candidates.append(pl.sum_horizontal([
                InfrastructureSystem._finite_column(column).clip(lower_bound=0.0)
                for column in partial_cohorts
            ]))
        weight = (
            InfrastructureSystem._finite_column("area_km2").clip(lower_bound=0.0)
            if "area_km2" in regions.columns
            else pl.lit(0.0)
        )
        for candidate in reversed(candidates):
            weight = pl.when(candidate > 0.0).then(candidate).otherwise(weight)
        return weight

    @staticmethod
    def _budget_ratio(country: dict[str, Any], category: str) -> float:
        column = "budget_telecom_ratio" if category == "telecom" else "budget_infra_ratio"
        if category == "utilities" and "budget_health_ratio" in country:
            column = "budget_health_ratio"
        value = InfrastructureSystem._finite(country.get(column))
        return max(0.0, min(1.0, value))

    @staticmethod
    def _next_project_id(
        projects: list[dict[str, Any]], country: str, region: int, category: str, now: int
    ) -> str:
        base = f"infrastructure-{country}-{region}-{category}-{now}"
        used = {str(project.get("id") or "") for project in projects}
        candidate = base
        suffix = 1
        while candidate in used:
            candidate = f"{base}-{suffix:03d}"
            suffix += 1
        return candidate

    @staticmethod
    def _region_rows(state: GameState) -> dict[int, dict[str, Any]]:
        regions = state.tables.get("regions")
        if regions is None or "id" not in regions.columns:
            return {}
        return {int(row.get("id") or 0): row for row in regions.iter_rows(named=True)}

    @staticmethod
    def _country_rows(state: GameState) -> dict[str, dict[str, Any]]:
        countries = state.tables.get("countries")
        if countries is None or "id" not in countries.columns:
            return {}
        return {
            InfrastructureSystem._tag(row.get("id")): row
            for row in countries.iter_rows(named=True)
        }

    @staticmethod
    def _tag(value: Any) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _integer(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return default

    @staticmethod
    def _finite(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        return number if math.isfinite(number) else 0.0

    @staticmethod
    def _write_rows(state: GameState, table_name: str, rows: list[dict[str, Any]]) -> None:
        original = state.tables.get(table_name)
        if original is None:
            return
        if not rows:
            state.update_table(table_name, original.head(0))
            return
        frame = pl.DataFrame(rows, infer_schema_length=None)
        for column, dtype in original.schema.items():
            if column in frame.columns:
                frame = frame.with_columns(pl.col(column).cast(dtype, strict=False))
        columns = [column for column in original.columns if column in frame.columns]
        columns.extend(column for column in frame.columns if column not in columns)
        state.update_table(table_name, frame.select(columns))

    @staticmethod
    def _record_result(state: GameState, action: Any, status: str, reason: str) -> None:
        state.journal.append_command_result(
            {
                "tick": int(state.globals.get("tick", 0)),
                "player_id": str(action.player_id),
                "action_type": type(action).__name__,
                "status": status,
                "reason": reason,
            }
        )

    @staticmethod
    def _reject(state: GameState, action: Any, reason: str) -> None:
        InfrastructureSystem._record_result(state, action, "rejected", reason)
