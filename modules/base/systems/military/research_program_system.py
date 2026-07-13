"""Authoritative research tracks, unit designs, and production-order lifecycle."""

from __future__ import annotations

from typing import Any

import polars as pl

from src.engine.interfaces import ISystem
from src.shared.actions import (
    ActionCancelProductionOrder,
    ActionCreateUnitDesign,
    ActionQueueUnitProduction,
    ActionUpdateResearchFunding,
)
from src.shared.events import EventRealSecond
from src.shared.state import GameState


_SECONDS_PER_YEAR = 365.25 * 24 * 60 * 60


class ResearchProgramSystem(ISystem):
    """Keeps player research and procurement choices in authoritative state tables."""

    @property
    def id(self) -> str:
        return "base.military_programs"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.bootstrap", "base.diplomacy"]

    def update(self, state: GameState, delta_time: float) -> None:
        if not {"research_tracks", "unit_designs", "production_orders"}.issubset(state.tables):
            return
        self._apply_actions(state)
        for event in (item for item in state.events if isinstance(item, EventRealSecond)):
            if not event.is_paused and event.game_seconds_passed > 0:
                self._advance_research(state, event.game_seconds_passed / _SECONDS_PER_YEAR)
                self._advance_production(state, event.game_seconds_passed / _SECONDS_PER_YEAR)

    def _apply_actions(self, state: GameState) -> None:
        tracks = state.get_table("research_tracks").to_dicts()
        designs = state.get_table("unit_designs").to_dicts()
        orders = state.get_table("production_orders").to_dicts()
        countries = state.get_table("countries").to_dicts() if "countries" in state.tables else []
        for action in state.current_actions:
            if isinstance(action, ActionUpdateResearchFunding):
                self._set_research_funding(tracks, action)
            elif isinstance(action, ActionCreateUnitDesign):
                self._create_design(designs, action)
            elif isinstance(action, ActionQueueUnitProduction):
                self._queue_production(orders, designs, countries, action)
            elif isinstance(action, ActionCancelProductionOrder):
                self._cancel_production(orders, designs, countries, action)
        state.update_table("research_tracks", self._frame(state, "research_tracks", tracks))
        state.update_table("unit_designs", self._frame(state, "unit_designs", designs))
        state.update_table("production_orders", self._frame(state, "production_orders", orders))
        if "countries" in state.tables:
            state.update_table("countries", self._frame(state, "countries", countries))

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
        })

    def _create_design(self, designs: list[dict[str, Any]], action: ActionCreateUnitDesign) -> None:
        country = self._tag(action.country_tag)
        class_name = str(action.class_name or "unit").strip().lower().replace(" ", "_")
        existing = {str(row.get("id") or "") for row in designs}
        index = 1
        design_id = f"design-{country}-{class_name}-{index:03d}"
        while design_id in existing:
            index += 1
            design_id = f"design-{country}-{class_name}-{index:03d}"
        stats = action.stats or {}
        designs.append({
            "id": design_id,
            "country_id": country,
            "branch": str(action.branch or "general").strip().lower(),
            "class_name": class_name,
            "display_name": str(action.display_name or class_name.replace("_", " ").title()),
            "quality": self._number(stats.get("quality")),
            "cost": max(0.0, self._number(stats.get("cost"))),
            "speed": max(0.0, self._number(stats.get("speed"))),
            "firepower": max(0.0, self._number(stats.get("firepower"))),
        })

    def _queue_production(
        self,
        orders: list[dict[str, Any]],
        designs: list[dict[str, Any]],
        countries: list[dict[str, Any]],
        action: ActionQueueUnitProduction,
    ) -> None:
        country, design_id = self._tag(action.country_tag), str(action.design_id or "")
        quantity = int(action.quantity)
        design = next((
            row for row in designs
            if str(row.get("id") or "") == design_id and self._tag(row.get("country_id")) == country
        ), None)
        country_row = next((row for row in countries if self._tag(row.get("id")) == country), None)
        if quantity <= 0 or design is None or country_row is None:
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
        })
    def _cancel_production(
        self,
        orders: list[dict[str, Any]],
        designs: list[dict[str, Any]],
        countries: list[dict[str, Any]],
        action: ActionCancelProductionOrder,
    ) -> None:
        remaining_orders = []
        for order in orders:
            if (
                str(order.get("id") or "") != str(action.order_id)
                or str(order.get("status") or "").lower() != "queued"
            ):
                remaining_orders.append(order)
                continue
            country = self._tag(order.get("country_id"))
            design = next((row for row in designs if str(row.get("id") or "") == str(order.get("design_id") or "")), None)
            country_row = next((row for row in countries if self._tag(row.get("id")) == country), None)
            if design is not None and country_row is not None:
                refund = max(0.0, self._number(design.get("cost"))) * max(0, int(order.get("quantity") or 0))
                country_row["money_reserves"] = self._number(country_row.get("money_reserves")) + refund
        orders[:] = remaining_orders


    def _advance_research(self, state: GameState, fraction: float) -> None:
        tracks = state.get_table("research_tracks")
        countries = state.tables.get("countries")
        if tracks.is_empty() or countries is None or countries.is_empty():
            return
        capacities = {
            self._tag(row.get("id")): max(1.0, self._number(row.get("gdp")) * self._number(row.get("budget_research_ratio")))
            for row in countries.to_dicts()
        }
        bonuses: dict[str, float] = {}
        effects = state.tables.get("treaty_effects")
        if effects is not None:
            for effect in effects.filter(pl.col("effect") == "research_capacity_bonus").to_dicts():
                country = self._tag(effect.get("country_id"))
                bonuses[country] = bonuses.get(country, 0.0) + self._number(effect.get("value"))
        rows = tracks.to_dicts()
        for row in rows:
            country = self._tag(row.get("country_id"))
            baseline = capacities.get(country, 1.0)
            rate = (baseline + bonuses.get(country, 0.0)) / baseline
            row["progress"] = min(1.0, max(0.0, self._number(row.get("progress")) + rate * self._ratio(row.get("funding_ratio")) * fraction))
        state.update_table("research_tracks", self._frame(state, "research_tracks", rows))

    def _advance_production(self, state: GameState, fraction: float) -> None:
        orders = state.get_table("production_orders")
        if orders.is_empty():
            return
        rows = orders.to_dicts()
        for row in rows:
            if str(row.get("status") or "").lower() in {"completed", "delivered"}:
                continue
            progress = self._number(row.get("progress")) + fraction * max(1, int(row.get("priority") or 1)) * 12.0
            row["progress"] = min(1.0, progress)
            row["status"] = "completed" if progress >= 1.0 else "queued"
            row["eta_days"] = 0 if progress >= 1.0 else max(1, int((1.0 - progress) * 30))
        state.update_table("production_orders", self._frame(state, "production_orders", rows))

    def _frame(self, state: GameState, table_name: str, rows: list[dict[str, Any]]) -> pl.DataFrame:
        table = state.get_table(table_name)
        return pl.DataFrame(rows, schema=table.schema) if rows else pl.DataFrame(schema=table.schema)

    def _tag(self, value: Any) -> str:
        return str(value or "").strip().upper()

    def _ratio(self, value: Any) -> float:
        return min(1.0, max(0.0, self._number(value)))

    def _number(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
