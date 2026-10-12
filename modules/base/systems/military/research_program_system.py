"""Authoritative research tracks, unit designs, and production-order lifecycle."""

from __future__ import annotations

import json
from typing import Any

import polars as pl

from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.actions import (
    ActionCancelProductionOrder,
    ActionCreateUnitDesign,
    ActionQueueUnitProduction,
    ActionSetProductionPaused,
    ActionSetProductionPriority,
    ActionUpdateResearchFunding,
)
from src.shared.events import EventRealSecond
from src.shared.state import GameState
from src.shared.system_state import SYSTEM_STATE_HELPER
from modules.base.systems.military.production_policy import (
    DEFAULT_PRODUCTION_COEFFICIENT,
    allocate_production_capacity_frame,
    annual_production_capacity_frame,
    initialize_production_order_work,
)
from modules.base.systems.military.capability_catalog import get_role_profile, project_capabilities
from modules.base.systems.military.research_eligibility_policy import research_requirements_met
from modules.base.systems.military.authority_policy import player_controls_country
from modules.base.systems.world.demilitarization_policy import DemilitarizationPolicy


_SECONDS_PER_YEAR = 365.25 * 24 * 60 * 60
_RESEARCH_ACTION_TYPES = (
    ActionCancelProductionOrder,
    ActionCreateUnitDesign,
    ActionQueueUnitProduction,
    ActionSetProductionPaused,
    ActionSetProductionPriority,
    ActionUpdateResearchFunding,
)
_TRACK_ACTION_TYPES = (ActionCreateUnitDesign, ActionQueueUnitProduction, ActionUpdateResearchFunding)
_DESIGN_ACTION_TYPES = (ActionCreateUnitDesign, ActionQueueUnitProduction)
_ORDER_ACTION_TYPES = (
    ActionCancelProductionOrder,
    ActionQueueUnitProduction,
    ActionSetProductionPaused,
    ActionSetProductionPriority,
)


class ResearchProgramSystem(ISystem):
    """Keeps player research and procurement choices in authoritative state tables."""

    runtime_state_contract = {"_demilitarization_policy": SYSTEM_STATE_HELPER}

    access = SystemAccess(
        reads=frozenset({'countries', 'research_tracks', 'unit_designs', 'production_orders'}),
        writes=frozenset({'countries', 'research_tracks', 'unit_designs', 'production_orders'}),
        handles=frozenset(
            {
                ActionCancelProductionOrder,
                ActionCreateUnitDesign,
                ActionQueueUnitProduction,
                ActionSetProductionPaused,
                ActionSetProductionPriority,
                ActionUpdateResearchFunding,
            }
        ),
        phase=SystemPhase.RESEARCH,
    )

    def __init__(self) -> None:
        self._demilitarization_policy = DemilitarizationPolicy()

    @property
    def id(self) -> str:
        return "base.military_programs"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.bootstrap", "base.diplomacy"]

    def update(self, state: GameState, delta_time: float) -> None:
        if not {"research_tracks", "unit_designs", "production_orders"}.issubset(state.tables):
            return
        if any(isinstance(action, _RESEARCH_ACTION_TYPES) for action in state.current_actions):
            self._apply_actions(state)
        for event in (item for item in state.events if isinstance(item, EventRealSecond)):
            if not event.is_paused and event.game_seconds_passed > 0:
                self._advance_research(state, event.game_seconds_passed / _SECONDS_PER_YEAR)
                self._advance_production(state, event.game_seconds_passed / _SECONDS_PER_YEAR)

    def _apply_actions(self, state: GameState) -> None:
        actions = [action for action in state.current_actions if isinstance(action, _RESEARCH_ACTION_TYPES)]
        if not actions:
            return

        needs_tracks = any(isinstance(action, _TRACK_ACTION_TYPES) for action in actions)
        needs_designs = any(isinstance(action, _DESIGN_ACTION_TYPES) for action in actions)
        needs_orders = any(isinstance(action, _ORDER_ACTION_TYPES) for action in actions)
        needs_countries = any(isinstance(action, ActionQueueUnitProduction) for action in actions)
        tracks_frame = state.get_table("research_tracks") if needs_tracks else None
        designs_frame = state.get_table("unit_designs") if needs_designs else None
        orders_frame = state.get_table("production_orders") if needs_orders else None
        countries_frame = state.tables.get("countries") if needs_countries else None
        tracks = [] if tracks_frame is None else tracks_frame.to_dicts()
        designs = [] if designs_frame is None else designs_frame.to_dicts()
        orders = [] if orders_frame is None else orders_frame.to_dicts()
        countries = [] if countries_frame is None else countries_frame.to_dicts()
        for action in actions:
            if isinstance(action, ActionUpdateResearchFunding):
                if self._authorized(state, action.player_id, self._tag(action.country_tag)):
                    self._set_research_funding(tracks, action)
                else:
                    self._reject(state, action, "The issuer does not control this research program.")
            elif isinstance(action, ActionCreateUnitDesign):
                self._create_design(state, designs, tracks, action)
            elif isinstance(action, ActionQueueUnitProduction):
                self._queue_production(state, orders, designs, tracks, countries, action)
            elif isinstance(action, ActionCancelProductionOrder):
                target = next((row for row in orders if str(row.get("id") or "") == str(action.order_id)), None)
                if target is not None and self._authorized(state, action.player_id, self._tag(target.get("country_id"))):
                    self._cancel_production(orders, action)
                elif target is not None:
                    self._reject(state, action, "The issuer does not control this production order.")
            elif isinstance(action, ActionSetProductionPaused):
                target = next((row for row in orders if str(row.get("id") or "") == str(action.order_id)), None)
                if target is not None and self._authorized(state, action.player_id, self._tag(target.get("country_id"))):
                    self._set_production_paused(orders, action)
                elif target is not None:
                    self._reject(state, action, "The issuer does not control this production order.")
            elif isinstance(action, ActionSetProductionPriority):
                target = next((row for row in orders if str(row.get("id") or "") == str(action.order_id)), None)
                if target is not None and self._authorized(state, action.player_id, self._tag(target.get("country_id"))):
                    self._set_production_priority(orders, action)
                elif target is not None:
                    self._reject(state, action, "The issuer does not control this production order.")
        if tracks_frame is not None:
            self._write_if_changed(state, "research_tracks", tracks, tracks_frame)
        if designs_frame is not None:
            self._write_if_changed(state, "unit_designs", designs, designs_frame)
        if orders_frame is not None:
            self._write_if_changed(state, "production_orders", orders, orders_frame)
        if countries_frame is not None:
            self._write_if_changed(state, "countries", countries, countries_frame)

    def _set_research_funding(self, tracks: list[dict[str, Any]], action: ActionUpdateResearchFunding) -> None:
        country, branch = self._tag(action.country_tag), str(action.branch or "").strip().lower()
        for row in tracks:
            if self._tag(row.get("country_id")) == country and str(row.get("branch") or "").lower() == branch:
                row["funding_ratio"] = self._ratio(action.funding_ratio)
                row["priority"] = max(1, int(action.priority))
                return
        tracks.append({
            "id": f"research-{country}-{branch or 'general'}",
            "country_id": country,
            "branch": branch or "general",
            "funding_ratio": self._ratio(action.funding_ratio),
            "progress": 0.0,
            "priority": max(1, int(action.priority)),
            "focus": "",
            "research_level": 0,
            "unlocks_json": "[]",
            "blocking_reason": "",
        })

    def _create_design(
        self,
        state: GameState,
        designs: list[dict[str, Any]],
        tracks: list[dict[str, Any]],
        action: ActionCreateUnitDesign,
    ) -> None:
        country = self._tag(action.country_tag)
        if not self._authorized(state, action.player_id, country):
            self._reject(state, action, "The issuer does not control this country's design program.")
            return
        if "countries" in state.tables and country not in {
            self._tag(row.get("id")) for row in state.get_table("countries").to_dicts()
        }:
            self._reject(state, action, "The design owner does not exist.")
            return
        class_name = str(action.class_name or "unit").strip().lower().replace(" ", "_")
        branch = str(action.branch or "general").strip().lower()
        stats = action.stats or {}
        requirements = stats.get("research_requirements", {})
        if not isinstance(requirements, dict):
            requirements = {}
        required_level = max(0, int(self._number(stats.get("required_research_level"))))
        requirements = {
            str(key).strip().lower(): max(required_level, int(self._number(value)))
            for key, value in requirements.items()
            if str(key).strip()
        }
        profile = get_role_profile(class_name, branch)
        canonical = str(profile.role or "").strip().lower()
        strategic_role = canonical in {"strategic_missiles", "ballistic_missile_submarines"}
        defense_role = canonical == "missile_defense"
        gate_level = max(1, int(self._number(state.globals.get("strategic_design_research_level", 1))))
        if strategic_role or defense_role:
            requirements["strategic_program"] = max(gate_level, requirements.get("strategic_program", 0))
            gate_branch = "strategic_defense" if defense_role else "strategic_weapons"
            requirements[gate_branch] = max(gate_level, requirements.get(gate_branch, 0))
        if required_level:
            requirements.setdefault(branch, required_level)
        research_levels = {
            str(row.get("branch") or "").strip().lower(): max(0, int(row.get("research_level") or 0))
            for row in tracks
            if self._tag(row.get("country_id")) == country
        }
        if not research_requirements_met(requirements, research_levels):
            return
        capabilities = project_capabilities(profile, stats)
        research_level = research_levels.get(branch, 0)
        existing = {str(row.get("id") or "") for row in designs}
        index = 1
        design_id = f"design-{country}-{class_name}-{index:03d}"
        while design_id in existing:
            index += 1
            design_id = f"design-{country}-{class_name}-{index:03d}"
        designs.append({
            "id": design_id,
            "country_id": country,
            "branch": branch,
            "class_name": class_name,
            "display_name": str(action.display_name or class_name.replace("_", " ").title()),
            "quality": self._number(stats.get("quality")),
            "cost": max(0.0, self._number(stats.get("cost"))),
            "maintenance_cost": max(0.0, min(1_000_000_000_000.0, self._number(stats.get("maintenance_cost")))),
            "speed": max(0.0, self._number(stats.get("speed"))),
            "firepower": max(0.0, self._number(stats.get("firepower"))),
            "domain": profile.domain,
            "capabilities_json": json.dumps(capabilities, sort_keys=True, separators=(",", ":")),
            "valid_targets_json": json.dumps(list(profile.valid_targets), separators=(",", ":")),
            "vulnerabilities_json": json.dumps(list(profile.vulnerabilities), separators=(",", ":")),
            "research_level": research_level,
            "research_requirements_json": json.dumps(requirements, sort_keys=True, separators=(",", ":")),
        })

    def _queue_production(
        self,
        state: GameState,
        orders: list[dict[str, Any]],
        designs: list[dict[str, Any]],
        tracks: list[dict[str, Any]],
        countries: list[dict[str, Any]],
        action: ActionQueueUnitProduction,
    ) -> None:
        country, design_id = self._tag(action.country_tag), str(action.design_id or "")
        if not self._authorized(state, action.player_id, country):
            self._reject(state, action, "The issuer does not control this country's production queue.")
            return
        quantity = int(action.quantity)
        design = next((
            row for row in designs
            if str(row.get("id") or "") == design_id and self._tag(row.get("country_id")) == country
        ), None)
        country_row = next((row for row in countries if self._tag(row.get("id")) == country), None)
        if quantity <= 0 or design is None or country_row is None:
            return
        levels = {
            str(row.get("branch") or "").strip().lower(): max(0, int(row.get("research_level") or 0))
            for row in tracks
            if self._tag(row.get("country_id")) == country
        }
        if not research_requirements_met(design.get("research_requirements_json"), levels):
            return
        if str(design.get("domain") or "land").strip().lower() not in {"land", "air", "naval", "strategic"}:
            return
        if not self._demilitarization_policy.can_add(
            state,
            country,
            quantity,
            production_orders=orders,
            include_production=True,
        ):
            self._reject(state, action, "The order would exceed an active demilitarization limit.")
            return
        total_cost = max(0.0, self._number(design.get("cost"))) * quantity
        available_funds = self._number(country_row.get("money_reserves"))
        if available_funds < total_cost:
            return
        country_row["money_reserves"] = available_funds - total_cost
        orders.append({
            "id": f"order-{country}-{len(orders) + 1:04d}",
            "country_id": country,
            "design_id": design_id,
            "quantity": quantity,
            "progress": 0.0,
            "priority": max(1, int(action.priority)),
            "status": "queued",
            "eta_days": max(1, int(30 / max(1, int(action.priority)))),
            "unit_cost": max(0.0, self._number(design.get("cost"))),
            "work_required": total_cost,
            "remaining_work": total_cost,
            "assigned_capacity": 0.0,
            "requested_training_level": self._training_level(action.training_level),
            "blocking_reason": "",
            "source": "domestic",
            "updated_at_minute": 0,
        })
    def _cancel_production(
        self,
        orders: list[dict[str, Any]],
        action: ActionCancelProductionOrder,
    ) -> None:
        for order in orders:
            if (
                str(order.get("id") or "") != str(action.order_id)
                or str(order.get("status") or "").lower() not in {"queued", "paused"}
            ):
                continue
            order["status"] = "cancelled"
            order["assigned_capacity"] = 0.0
            order["blocking_reason"] = "Cancelled; incurred production costs are not refunded."

    def _set_production_paused(
        self,
        orders: list[dict[str, Any]],
        action: ActionSetProductionPaused,
    ) -> None:
        target_status = "paused" if action.is_paused else "queued"
        for order in orders:
            if str(order.get("id") or "") != str(action.order_id):
                continue
            status = str(order.get("status") or "").strip().lower()
            if action.is_paused and status == "queued":
                order["status"] = target_status
                order["blocking_reason"] = "Order is paused."
            elif not action.is_paused and status == "paused":
                order["status"] = target_status
                order["blocking_reason"] = ""
            return

    def _set_production_priority(
        self,
        orders: list[dict[str, Any]],
        action: ActionSetProductionPriority,
    ) -> None:
        for order in orders:
            if str(order.get("id") or "") == str(action.order_id) and str(order.get("status") or "").lower() in {"queued", "paused"}:
                order["priority"] = min(100, max(1, int(action.priority)))
                return

    def _authorized(self, state: GameState, player_id: Any, country: str) -> bool:
        return player_controls_country(state, player_id, country)

    def _reject(self, state: GameState, action: Any, reason: str) -> None:
        state.journal.append_command_result({
            "tick": int(state.globals.get("tick", 0)),
            "player_id": str(action.player_id or ""),
            "action_type": type(action).__name__,
            "status": "rejected",
            "reason": reason,
        })


    def _advance_research(self, state: GameState, fraction: float) -> None:
        tracks = state.get_table("research_tracks")
        countries = state.tables.get("countries")
        if tracks.is_empty() or countries is None or countries.is_empty():
            return

        country_columns = set(countries.columns)
        gdp = (
            pl.col("gdp").cast(pl.Float64, strict=False).fill_null(0.0)
            if "gdp" in country_columns
            else pl.lit(0.0)
        )
        ratio = (
            pl.col("budget_research_ratio").cast(pl.Float64, strict=False).fill_null(0.0)
            if "budget_research_ratio" in country_columns
            else pl.lit(0.0)
        )
        capacities = countries.select(
            pl.col("id").cast(pl.Utf8).fill_null("").str.strip_chars().str.to_uppercase().alias("_country"),
            pl.when((gdp * ratio).is_finite())
            .then(gdp * ratio)
            .otherwise(0.0)
            .clip(lower_bound=1.0)
            .alias("_baseline_capacity"),
        )
        bonuses = pl.DataFrame(schema={"_country": pl.Utf8, "_capacity_bonus": pl.Float64})
        effects = state.tables.get("treaty_effects")
        if effects is not None and {"effect", "country_id", "value"}.issubset(effects.columns):
            bonuses = (
                effects.filter(pl.col("effect") == "research_capacity_bonus")
                .select(
                    pl.col("country_id").cast(pl.Utf8).fill_null("").str.strip_chars().str.to_uppercase().alias("_country"),
                    pl.when(pl.col("value").cast(pl.Float64, strict=False).is_finite())
                    .then(pl.col("value").cast(pl.Float64, strict=False))
                    .otherwise(0.0)
                    .alias("_capacity_bonus"),
                )
                .group_by("_country")
                .agg(pl.col("_capacity_bonus").sum())
            )

        configured_prerequisites = state.globals.get("research_prerequisites", {})
        prerequisites = {
            "strategic_weapons": {"strategic_program": 1},
            "strategic_defense": {"strategic_program": 1},
        }
        if isinstance(configured_prerequisites, dict):
            for branch, requirements in configured_prerequisites.items():
                if isinstance(requirements, dict):
                    prerequisites[str(branch).strip().lower()] = {
                        str(required_branch).strip().lower(): max(0, int(self._number(level)))
                        for required_branch, level in requirements.items()
                    }

        prerequisite_rows = [
            (branch, required_branch, level, requirement_order)
            for branch, requirements in prerequisites.items()
            for requirement_order, (required_branch, level) in enumerate(requirements.items())
        ]
        prerequisite_frame = pl.DataFrame(
            prerequisite_rows,
            schema={
                "_branch": pl.Utf8,
                "_required_branch": pl.Utf8,
                "_required_level": pl.Int64,
                "_requirement_order": pl.Int64,
            },
            orient="row",
        )
        working = tracks.with_row_index("_track_order").with_columns(
            pl.col("country_id").cast(pl.Utf8).fill_null("").str.strip_chars().str.to_uppercase().alias("_country"),
            pl.col("branch").cast(pl.Utf8).fill_null("").str.strip_chars().str.to_lowercase().alias("_branch"),
            pl.col("research_level").cast(pl.Int64, strict=False).fill_null(0).clip(lower_bound=0).alias("_current_level"),
            pl.col("progress").cast(pl.Float64, strict=False).fill_null(0.0).alias("_current_progress"),
            pl.col("funding_ratio").cast(pl.Float64, strict=False).fill_null(0.0).clip(lower_bound=0.0, upper_bound=1.0).alias("_funding_ratio"),
        )
        levels = (
            working.group_by(["_country", "_branch"])
            .agg(pl.col("_current_level").max().alias("_completed_level"))
        )
        unmet = pl.DataFrame(
            schema={"_track_order": pl.UInt32, "_blocking_reason": pl.Utf8}
        )
        if not prerequisite_frame.is_empty():
            unmet = (
                working.select("_track_order", "_country", "_branch")
                .join(prerequisite_frame, left_on="_branch", right_on="_branch", how="inner")
                .join(
                    levels,
                    left_on=["_country", "_required_branch"],
                    right_on=["_country", "_branch"],
                    how="left",
                )
                .filter(pl.col("_completed_level").fill_null(0) < pl.col("_required_level"))
                .sort(["_track_order", "_requirement_order"])
                .unique(subset="_track_order", keep="first", maintain_order=True)
                .with_columns(
                    pl.concat_str(
                        [
                            pl.lit("Requires "),
                            pl.col("_required_branch"),
                            pl.lit(" research level "),
                            pl.col("_required_level").cast(pl.Utf8),
                            pl.lit("."),
                        ]
                    ).alias("_blocking_reason")
                )
                .select("_track_order", "_blocking_reason")
            )
        updated = (
            working.join(capacities, on="_country", how="left")
            .join(bonuses, on="_country", how="left")
            .join(unmet, on="_track_order", how="left")
            .with_columns(
                pl.col("_baseline_capacity").fill_null(1.0).alias("_baseline_capacity"),
                pl.col("_capacity_bonus").fill_null(0.0).alias("_capacity_bonus"),
                pl.when(pl.col("_current_progress").is_finite())
                .then(pl.col("_current_progress").clip(lower_bound=0.0))
                .otherwise(0.0)
                .alias("_safe_progress"),
            )
            .with_columns(
                (
                    pl.col("_safe_progress")
                    + ((pl.col("_baseline_capacity") + pl.col("_capacity_bonus")) / pl.col("_baseline_capacity"))
                    * pl.col("_funding_ratio")
                    * float(fraction)
                ).alias("_advanced_progress")
            )
            .with_columns(
                pl.when(pl.col("_blocking_reason").is_not_null())
                .then(pl.col("research_level"))
                .otherwise(pl.col("_current_level") + pl.col("_advanced_progress").cast(pl.Int64))
                .alias("research_level"),
                pl.when(pl.col("_blocking_reason").is_not_null())
                .then(pl.col("progress"))
                .otherwise(pl.col("_advanced_progress") - pl.col("_advanced_progress").cast(pl.Int64))
                .alias("progress"),
                pl.col("_blocking_reason").fill_null("").alias("blocking_reason"),
            )
            .select(list(tracks.columns))
        )
        if not tracks.equals(updated):
            state.update_table("research_tracks", updated)

    def _advance_production(self, state: GameState, fraction: float) -> None:
        orders = state.get_table("production_orders")
        if orders.is_empty():
            return
        orders = initialize_production_order_work(
            orders,
            state.tables.get("unit_designs"),
        )

        configured_coefficient = state.globals.get("production_capacity_coefficient")
        coefficient = (
            DEFAULT_PRODUCTION_COEFFICIENT
            if configured_coefficient is None
            else max(0.0, _finite(configured_coefficient))
        )
        capacities = annual_production_capacity_frame(
            state.tables.get("countries"), coefficient
        )
        allocation_policy = str(state.globals.get("production_allocation_policy") or "priority")
        updated = allocate_production_capacity_frame(
            orders,
            capacities,
            fraction,
            allocation_policy,
        )
        if "updated_at_minute" in updated.columns:
            terminal = ["cancelled", "completed", "delivered"]
            updated = updated.with_columns(
                pl.when(
                    ~pl.col("status").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_lowercase().is_in(terminal)
                )
                .then(pl.lit(int(state.time.total_minutes)))
                .otherwise(pl.col("updated_at_minute"))
                .cast(state.get_table("production_orders").schema["updated_at_minute"])
                .alias("updated_at_minute")
            )
        state.update_table("production_orders", updated)

    def _training_level(self, value: Any) -> str:
        levels = {"recruit", "regular"}
        normalized = str(value or "Recruit").strip().lower()
        return normalized.title() if normalized in levels else "Recruit"

    def _frame(self, state: GameState, table_name: str, rows: list[dict[str, Any]]) -> pl.DataFrame:
        table = state.get_table(table_name)
        return pl.DataFrame(rows, schema=table.schema) if rows else pl.DataFrame(schema=table.schema)

    def _write_if_changed(
        self,
        state: GameState,
        table_name: str,
        rows: list[dict[str, Any]],
        current: pl.DataFrame,
    ) -> None:
        result = pl.DataFrame(rows, schema=current.schema) if rows else pl.DataFrame(schema=current.schema)
        if not current.equals(result):
            state.update_table(table_name, result)

    def _tag(self, value: Any) -> str:
        return str(value or "").strip().upper()

    def _ratio(self, value: Any) -> float:
        return min(1.0, max(0.0, self._number(value)))

    def _number(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0


def _finite(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return result if result == result and abs(result) != float("inf") else 0.0
