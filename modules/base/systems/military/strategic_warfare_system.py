"""Deterministic strategic launch, layered defense, and bounded impact lifecycle."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

import polars as pl

from src.shared.actions import ActionLaunchStrategicStrike, ActionProduceStrategicWeapon
from src.shared.events import DomainGameEvent, EventMessageCreated, EventNewDay
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.strategic_profiles import DEFAULT_DEFENSE, PAYLOAD_PROFILES
from modules.base.systems.military.authority_policy import player_controls_country
from modules.base.systems.military.readiness_policy import (
    READINESS_FORTIFIED,
    READINESS_PARKED,
    READINESS_READY,
    ReadinessPolicy,
)


@dataclass
class EventStrategicStrikeTransition(DomainGameEvent):
    order_id: str
    status: str
    target_country_id: str
    target_region_id: int
    at_minute: int


@dataclass
class EventStrategicWeaponProductionTransition(DomainGameEvent):
    order_id: str
    status: str
    country_id: str
    weapon_id: str
    at_minute: int


@dataclass(frozen=True)
class StrategicUpdateIndexes:
    """Immutable table lookups shared by all strikes resolved in one update."""

    regions_by_id: dict[int, dict[str, Any]]
    regions_by_country: dict[str, tuple[dict[str, Any], ...]]
    home_region_by_country: dict[str, dict[str, Any]]
    research_levels_by_country: dict[str, dict[str, int]]
    units_in_readiness_transition: frozenset[str]

    @classmethod
    def build(cls, state: GameState) -> StrategicUpdateIndexes:
        region_table = state.tables.get("regions")
        regions = [] if region_table is None else region_table.to_dicts()
        regions_by_id = {
            int(row.get("id") or 0): row
            for row in regions
            if int(row.get("id") or 0) > 0
        }
        by_country: dict[str, list[dict[str, Any]]] = {}
        for row in regions:
            country = str(row.get("owner") or "").strip().upper()
            if country:
                by_country.setdefault(country, []).append(row)
        home_region_by_country = {
            country: min(rows, key=lambda row: int(row.get("id") or 0))
            for country, rows in by_country.items()
        }
        governments = state.tables.get("country_governments")
        if governments is not None:
            for row in governments.to_dicts():
                country = str(row.get("country_id") or "").strip().upper()
                capital_id = int(row.get("capital_region_id") or 0)
                capital = regions_by_id.get(capital_id)
                if country and capital is not None and str(capital.get("owner") or "").strip().upper() == country:
                    home_region_by_country[country] = capital

        research_levels: dict[str, dict[str, int]] = {}
        tracks = state.tables.get("research_tracks")
        if tracks is not None:
            for row in tracks.to_dicts():
                country = str(row.get("country_id") or "").strip().upper()
                branch = str(row.get("branch") or "").strip().lower()
                if not country or not branch:
                    continue
                levels = research_levels.setdefault(country, {})
                levels[branch] = max(levels.get(branch, 0), max(0, int(row.get("research_level") or 0)))

        transitions = state.tables.get("unit_readiness_transitions")
        transitioning_units = frozenset(
            str(row.get("unit_id") or "")
            for row in (transitions.to_dicts() if transitions is not None else [])
            if str(row.get("unit_id") or "")
        )

        return cls(
            regions_by_id=regions_by_id,
            regions_by_country={country: tuple(rows) for country, rows in by_country.items()},
            home_region_by_country=home_region_by_country,
            research_levels_by_country=research_levels,
            units_in_readiness_transition=transitioning_units,
        )


@dataclass
class StrategicEventBuffer:
    """Collects per-strike notifications and relation changes for one atomic flush."""

    messages: pl.DataFrame | None
    message_schema: Any
    message_dirty: bool = False
    message_additions: list[dict[str, Any]] | None = None
    relation_deltas: dict[tuple[str, str], float] | None = None

    @classmethod
    def from_state(cls, state: GameState) -> StrategicEventBuffer:
        table = state.tables.get("messages")
        return cls(
            messages=table,
            message_schema=None if table is None else table.schema,
            relation_deltas={},
            message_additions=[],
        )

    def add_message(self, state: GameState, recipient: str, status: str, body: str) -> None:
        if self.messages is None:
            return
        additions = self.message_additions
        if additions is None:
            additions = []
            self.message_additions = additions
        message_id = f"strategic-message-{self.messages.height + len(additions) + 1:08d}"
        additions.append({
            "id": message_id,
            "country_id": recipient,
            "category": "strategic",
            "subject": f"Strategic strike {status}",
            "body": body,
            "is_read": False,
            "created_at": str(int(state.time.total_minutes)),
        })
        self.message_dirty = True
        state.events.append(EventMessageCreated(message_id, recipient, "strategic"))

    def add_escalation(self, owner: str, target: str, status: str, detected: bool) -> None:
        delta = -8.0 if status == "impact" else -3.0 if status == "intercepted" else -1.0
        if detected:
            delta -= 2.0
        assert self.relation_deltas is not None
        for pair in ((owner, target), (target, owner)):
            self.relation_deltas[pair] = self.relation_deltas.get(pair, 0.0) + delta

    def flush(self, state: GameState) -> None:
        if self.message_dirty and self.messages is not None and self.message_additions:
            additions = pl.DataFrame(self.message_additions, schema=self.message_schema)
            state.update_table("messages", pl.concat([self.messages, additions], how="vertical"))
        if not self.relation_deltas:
            return
        table = state.tables.get("countries_relations")
        if table is None or not {"source", "target", "value"}.issubset(table.columns):
            return
        deltas = pl.DataFrame(
            [
                (source, target, delta)
                for (source, target), delta in sorted(self.relation_deltas.items())
            ],
            schema={"_source_key": pl.Utf8, "_target_key": pl.Utf8, "_delta": pl.Float64},
            orient="row",
        )
        keyed = table.with_columns(
            pl.col("source").cast(pl.Utf8).fill_null("").str.strip_chars().str.to_uppercase().alias("_source_key"),
            pl.col("target").cast(pl.Utf8).fill_null("").str.strip_chars().str.to_uppercase().alias("_target_key"),
        )
        updated = (
            keyed.join(deltas, on=["_source_key", "_target_key"], how="left")
            .with_columns(
                pl.when(pl.col("_delta").is_not_null())
                .then(
                    (pl.col("value").cast(pl.Float64, strict=False).fill_null(0.0) + pl.col("_delta"))
                    .clip(lower_bound=-100.0, upper_bound=100.0)
                )
                .otherwise(pl.col("value"))
                .alias("value")
            )
        )
        missing = deltas.join(
            keyed.select("_source_key", "_target_key").unique(),
            on=["_source_key", "_target_key"],
            how="anti",
        )
        updated = updated.select(list(table.columns))
        if not missing.is_empty():
            additions = missing.select(
                pl.col("_source_key").alias("source"),
                pl.col("_target_key").alias("target"),
                pl.col("_delta").clip(lower_bound=-100.0, upper_bound=100.0).alias("value"),
            )
            for name, dtype in table.schema.items():
                if name not in additions.columns:
                    additions = additions.with_columns(pl.lit(None, dtype=dtype).alias(name))
                else:
                    additions = additions.with_columns(pl.col(name).cast(dtype, strict=False))
            additions = additions.select(list(table.columns))
            updated = pl.concat([updated, additions], how="vertical")
        if not updated.equals(table):
            state.update_table("countries_relations", updated)


class StrategicWarfareSystem(ISystem):
    access = SystemAccess(
        reads=frozenset({"countries", "regions", "country_governments", "countries_relations", "units", "unit_readiness_transitions", "research_tracks", "strategic_weapons", "strategic_production_orders", "strategic_launch_orders", "missile_defense_layers", "strategic_impacts", "messages", "countries_wars"}),
        writes=frozenset({"countries", "countries_relations", "units", "regions", "strategic_weapons", "strategic_production_orders", "strategic_launch_orders", "missile_defense_layers", "strategic_impacts", "messages"}),
        handles=frozenset({ActionLaunchStrategicStrike, ActionProduceStrategicWeapon}),
        phase=SystemPhase.MILITARY + 4,
    )

    @property
    def id(self) -> str:
        return "base.strategic_warfare"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.diplomacy", "base.military_programs"]

    def update(self, state: GameState, delta_time: float) -> None:
        required = {"strategic_weapons", "strategic_launch_orders", "missile_defense_layers", "strategic_impacts"}
        if not required.issubset(state.tables):
            return
        now = int(state.time.total_minutes)
        has_launch_actions = any(isinstance(action, ActionLaunchStrategicStrike) for action in state.current_actions)
        has_production_actions = any(isinstance(action, ActionProduceStrategicWeapon) for action in state.current_actions)
        production_table = state.tables.get("strategic_production_orders")
        order_table = state.get_table("strategic_launch_orders")
        defense_table = state.get_table("missile_defense_layers")
        has_due_production_orders = self._has_due_production_orders(production_table, now)
        has_due_orders = self._has_due_launch_orders(order_table, now)
        maintainable_defenses = (
            not state.time.is_paused
            and any(isinstance(event, EventNewDay) for event in state.events)
            and self._has_maintainable_defenses(defense_table)
        )
        if not (has_launch_actions or has_production_actions or has_due_production_orders or has_due_orders or maintainable_defenses):
            return

        weapons = state.get_table("strategic_weapons").to_dicts()
        production_orders = [] if production_table is None else production_table.to_dicts()
        orders = order_table.to_dicts()
        defenses = defense_table.to_dicts()
        impacts = state.get_table("strategic_impacts").to_dicts()
        countries_frame = state.tables.get("countries")
        country_rows = [] if countries_frame is None else countries_frame.to_dicts()
        original_countries = [dict(row) for row in country_rows]
        production_orders_changed = False
        if has_due_production_orders:
            production_orders_changed = self._complete_production_orders(
                state, weapons, production_orders, country_rows, now,
            )
        indexes = StrategicUpdateIndexes.build(state) if has_launch_actions or has_due_orders or maintainable_defenses else None
        event_buffer = StrategicEventBuffer.from_state(state) if has_launch_actions or has_due_orders else None
        if maintainable_defenses:
            self._maintain_defenses(state, defenses, country_rows, indexes)
        for action in state.current_actions:
            if isinstance(action, ActionProduceStrategicWeapon):
                production_order = self._prepare_weapon_production(
                    state, weapons, production_orders, action, country_rows, now,
                )
                if production_order:
                    production_orders.append(production_order)
                    production_orders_changed = True
                    state.events.append(EventStrategicWeaponProductionTransition(
                        production_order["id"], "pending", production_order["country_id"],
                        production_order["weapon_id"], now,
                    ))
            elif isinstance(action, ActionLaunchStrategicStrike):
                order = self._prepare_launch(state, weapons, orders, action, country_rows, indexes)
                if order:
                    orders.append(order)
                    self._publish_transition(state, order, event_buffer)
        for order in orders:
            if order.get("status") != "pending" or now < int(order.get("resolves_at_minute") or 0):
                continue
            region = self._region_by_id(state, int(order.get("target_region_id") or 0), indexes)
            if region is None or self._tag(region.get("owner")) != self._tag(order.get("target_country_id")):
                order.update(status="cancelled", reason="Target ownership changed before impact.", updated_at_minute=now)
                self._publish_transition(state, order, event_buffer)
                continue
            intercepted, results = self._resolve_defense(state, order, region, defenses, indexes)
            order["defense_result_json"] = json.dumps(results, sort_keys=True, separators=(",", ":"))
            if intercepted:
                order.update(status="intercepted", reason="The incoming payload was intercepted.", updated_at_minute=now)
                self._record_impact(impacts, order, "interception", 1.0, False, now)
            else:
                self._apply_impact(state, order, region, impacts, country_rows, now, indexes)
                order.update(status="impact", reason="The payload reached its target.", updated_at_minute=now)
            self._publish_transition(state, order, event_buffer)
        if event_buffer is not None:
            event_buffer.flush(state)
        if countries_frame is not None and country_rows != original_countries:
            state.update_table("countries", pl.DataFrame(country_rows, schema=countries_frame.schema))
        self._write(state, "strategic_weapons", weapons)
        if production_orders_changed and production_table is not None:
            state.update_table("strategic_production_orders", pl.DataFrame(production_orders, schema=production_table.schema))
        self._write(state, "strategic_launch_orders", orders)
        self._write(state, "missile_defense_layers", defenses)
        self._write(state, "strategic_impacts", impacts)

    @staticmethod
    def _has_due_production_orders(orders: pl.DataFrame | None, now: int) -> bool:
        if orders is None or orders.is_empty() or not {"status", "completes_at_minute", "ready_at_minute"}.issubset(orders.columns):
            return False
        status = pl.col("status").cast(pl.Utf8).fill_null("")
        due = orders.filter(
            ((status == "pending") & (pl.col("completes_at_minute").fill_null(0) <= now))
            | ((status == "readying") & (pl.col("ready_at_minute").fill_null(0) <= now))
        )
        return not due.is_empty()

    @staticmethod
    def _has_due_launch_orders(orders: pl.DataFrame, now: int) -> bool:
        if orders.is_empty() or not {"status", "resolves_at_minute"}.issubset(orders.columns):
            return False
        due = orders.filter(
            (pl.col("status").cast(pl.Utf8).fill_null("") == "pending")
            & (pl.col("resolves_at_minute").fill_null(0) <= now)
        )
        return not due.is_empty()

    @staticmethod
    def _has_maintainable_defenses(defenses: pl.DataFrame) -> bool:
        if defenses.is_empty() or not {"researched", "operational"}.issubset(defenses.columns):
            return False
        maintainable = defenses.filter(
            pl.col("researched").cast(pl.Boolean, strict=False).fill_null(False)
            & pl.col("operational").cast(pl.Boolean, strict=False).fill_null(False)
        )
        return not maintainable.is_empty()

    def _prepare_weapon_production(self, state, weapons, production_orders, action, countries, now):
        if "strategic_production_orders" not in state.tables:
            return self._reject(state, action, "Strategic weapon production is unavailable in this scenario.")
        owner = self._tag(action.country_tag)
        if not owner or not self._authorized(state, action.player_id, owner):
            return self._reject(state, action, "The player cannot authorize this country's production order.")
        authorized_countries = state.globals.get("strategic_production_authorized_countries")
        if isinstance(authorized_countries, (list, tuple, set)) and owner not in {
            self._tag(country) for country in authorized_countries
        }:
            return self._reject(state, action, "This country lacks policy authority to produce strategic weapons.")
        weapon_id = str(action.weapon_id or "").strip()
        weapon = next(
            (row for row in weapons if self._tag(row.get("country_id")) == owner and str(row.get("id") or "") == weapon_id),
            None,
        )
        if weapon is None:
            return self._reject(state, action, "No matching strategic weapon design is owned by the producing country.")
        if not self._research_permits(state, owner, weapon):
            return self._reject(state, action, "Required strategic program and weapon research are incomplete.")
        payload_level = max(1, int(self._finite(weapon.get("payload_level"))))
        if payload_level > self._researched_payload_cap(state, owner, weapon):
            return self._reject(state, action, "The weapon design payload exceeds completed research.")
        quantity = int(self._finite(action.quantity))
        max_batch = max(1, int(self._finite(state.globals.get("strategic_production_max_batch", 100))))
        if quantity < 1 or quantity > max_batch:
            return self._reject(state, action, f"Production quantity must be between 1 and {max_batch}.")
        unit_cost = max(0.0, self._finite(weapon.get("production_cost")))
        production_minutes = int(self._finite(weapon.get("production_minutes")))
        if unit_cost <= 0.0 or production_minutes <= 0:
            return self._reject(state, action, "This weapon design has no configured production cost and duration.")
        country = next((row for row in countries if self._tag(row.get("id")) == owner), None)
        cost_total = unit_cost * quantity
        if country is None or self._finite(country.get("money_reserves")) < cost_total:
            return self._reject(state, action, "The producing country cannot fund this order.")
        country["money_reserves"] = self._finite(country.get("money_reserves")) - cost_total
        order = {
            "id": self._next_id("weapon-production", production_orders),
            "country_id": owner,
            "weapon_id": weapon_id,
            "quantity": quantity,
            "cost_total": cost_total,
            "ordered_at_minute": now,
            "completes_at_minute": now + max(1, production_minutes),
            "status": "pending",
            "reason": "Production is in progress.",
            "completed_at_minute": 0,
        }
        return order

    def _complete_production_orders(self, state, weapons, production_orders, countries, now):
        country_by_id = {self._tag(row.get("id")): row for row in countries}
        changed = False
        for order in production_orders:
            owner = self._tag(order.get("country_id"))
            weapon_id = str(order.get("weapon_id") or "")
            quantity = max(0, int(order.get("quantity") or 0))
            if order.get("status") == "pending":
                if now < int(order.get("completes_at_minute") or 0):
                    continue
                weapon = next(
                    (row for row in weapons if self._tag(row.get("country_id")) == owner and str(row.get("id") or "") == weapon_id),
                    None,
                )
                country = country_by_id.get(owner)
                if weapon is None or country is None or quantity <= 0 or not self._research_permits(state, owner, weapon):
                    if country is not None:
                        country["money_reserves"] = self._finite(country.get("money_reserves")) + max(0.0, self._finite(order.get("cost_total")))
                    order.update(status="cancelled", reason="Production prerequisites changed before completion.", completed_at_minute=now)
                else:
                    weapon["quantity"] = max(0, int(weapon.get("quantity") or 0)) + quantity
                    readiness_minutes = max(0, int(self._finite(weapon.get("readiness_minutes"))))
                    if readiness_minutes > 0:
                        order.update(
                            status="readying",
                            ready_at_minute=now + readiness_minutes,
                            reason="Production is complete; weapons are completing their readiness period.",
                        )
                    else:
                        weapon["ready"] = max(0, int(weapon.get("ready") or 0)) + quantity
                        order.update(status="completed", reason="Strategic weapons are ready for use.", completed_at_minute=now)
            elif order.get("status") == "readying":
                if now < int(order.get("ready_at_minute") or 0):
                    continue
                weapon = next(
                    (row for row in weapons if self._tag(row.get("country_id")) == owner and str(row.get("id") or "") == weapon_id),
                    None,
                )
                if weapon is None or quantity <= 0:
                    order.update(status="cancelled", reason="The weapon design disappeared during readiness.", completed_at_minute=now)
                else:
                    weapon["ready"] = max(0, int(weapon.get("ready") or 0)) + quantity
                    order.update(status="completed", reason="Strategic weapons are ready for use.", completed_at_minute=now)
            else:
                continue
            state.events.append(EventStrategicWeaponProductionTransition(
                str(order.get("id") or ""), str(order.get("status") or ""), owner, weapon_id, now,
            ))
            changed = True
        return changed

    def _prepare_launch(self, state, weapons, orders, action, countries, indexes=None):
        owner = self._tag(action.country_tag)
        target_id = self._tag(action.target_country_tag)
        region = self._region_by_id(state, int(action.target_region_id), indexes)
        if region is None:
            return self._reject(state, action, "The target region does not exist.")
        target_id = target_id or self._tag(region.get("owner"))
        if not owner or target_id != self._tag(region.get("owner")) or target_id == owner:
            return self._reject(state, action, "The target country or region is invalid.")
        if not self._authorized(state, action.player_id, owner):
            return self._reject(state, action, "The player cannot authorize this country's launch.")
        weapon = next((row for row in weapons if self._tag(row.get("country_id")) == owner and (str(row.get("id")) == str(action.weapon_id) if action.weapon_id else self._weapon_matches(row, action.weapon_type))), None)
        if weapon is None:
            return self._reject(state, action, "No matching strategic weapon is owned by the launching country.")
        if not bool(weapon.get("operational", True)) or int(weapon.get("ready") or 0) < 1 or int(weapon.get("quantity") or 0) < 1:
            return self._reject(state, action, "The selected weapon is destroyed, unavailable, or not ready.")
        if not self._research_permits(state, owner, weapon, indexes):
            return self._reject(state, action, "Required strategic program and weapon research are incomplete.")
        if any(row.get("status") == "pending" and row.get("weapon_id") == weapon.get("id") for row in orders):
            return self._reject(state, action, "This weapon already has a pending launch order.")
        target_mode = str(action.target_mode or "military").strip().lower()
        if target_mode not in {"military", "civilian"}:
            return self._reject(state, action, "The selected target mode is unsupported.")
        target_object_id = str(action.target_object_id or "").strip()
        if target_object_id:
            units = state.tables.get("units")
            target_unit = None if units is None else next(
                (row for row in units.to_dicts() if str(row.get("id") or "") == target_object_id),
                None,
            )
            if (
                target_mode != "military"
                or target_unit is None
                or self._tag(target_unit.get("owner")) != target_id
                or int(target_unit.get("current_region_id") or 0) != int(region.get("id") or 0)
            ):
                return self._reject(state, action, "The selected strategic target object is not a military unit in the target region.")
        level = int(action.payload_level or weapon.get("payload_level") or 1)
        max_payload = self._researched_payload_cap(state, owner, weapon, indexes)
        if level not in PAYLOAD_PROFILES or level > max_payload:
            return self._reject(state, action, "The payload level exceeds the weapon's researched design.")
        asset_origin_id = int(weapon.get("origin_region_id") or 0)
        requested_origin_id = int(action.origin_region_id or 0)
        if requested_origin_id and asset_origin_id and requested_origin_id != asset_origin_id:
            return self._reject(state, action, "The requested origin does not match the selected weapon's registered origin.")
        origin_id = requested_origin_id or asset_origin_id
        origin = self._region_by_id(state, origin_id, indexes)
        if requested_origin_id and origin is None:
            return self._reject(state, action, "The requested weapon origin region does not exist.")
        if origin is not None and self._tag(origin.get("owner")) != owner:
            return self._reject(state, action, "The weapon's origin region is not controlled by its owner.")
        if origin is None:
            origin = self._home_region(state, owner, indexes)
        if origin is None:
            return self._reject(state, action, "The weapon has no valid origin region.")
        distance = self._distance_km(origin, region)
        if distance > max(0.0, self._finite(weapon.get("range_km"))):
            return self._reject(state, action, "The target is outside this weapon's operational range.")
        if not self._launch_authorized(state, owner, target_id, action.authorization_context):
            return self._reject(state, action, "Political launch authorization is missing.")
        cost = max(0.0, self._finite(weapon.get("launch_cost")))
        country = next((row for row in countries if self._tag(row.get("id")) == owner), None)
        if country is None or self._finite(country.get("money_reserves")) < cost:
            return self._reject(state, action, "The launching country is unknown or cannot fund the launch cost.")
        country["money_reserves"] = self._finite(country.get("money_reserves")) - cost
        weapon["ready"] = int(weapon.get("ready") or 0) - 1
        weapon["quantity"] = int(weapon.get("quantity") or 0) - 1
        level = min(level, max_payload)
        yield_kt, radius = self._payload_profile(state, level)
        order_id = self._next_id("strike", orders)
        now = int(state.time.total_minutes)
        flight_minutes = int(self._finite(weapon.get("flight_minutes")))
        if flight_minutes <= 0:
            flight_minutes = int(self._finite(state.globals.get("strategic_flight_minutes", 60)))
        launch_order = {
            "id": order_id, "country_id": owner, "weapon_id": str(weapon.get("id")),
            "weapon_type": str(weapon.get("weapon_type") or action.weapon_type),
            "origin_region_id": int(origin.get("id") or 0),
            "target_country_id": target_id, "target_region_id": int(action.target_region_id),
            "target_object_id": target_object_id, "target_mode": target_mode,
            "payload_level": level, "yield_kt": yield_kt, "blast_radius_km": radius,
            "launched_at_minute": now,
            "resolves_at_minute": now + max(1, flight_minutes),
            "status": "pending", "authorization_context": str(action.authorization_context or ""),
            "launch_detected": False, "launch_attributed": False, "defense_result_json": "[]",
            "reason": "Awaiting impact resolution.", "updated_at_minute": now,
        }
        probability = max(0.0, min(1.0, self._finite(state.globals.get("strategic_launch_detection_probability", 0.2))))
        defense_table = state.tables.get("missile_defense_layers")
        sensors = [] if defense_table is None else [
            row for row in defense_table.to_dicts()
            if self._tag(row.get("country_id")) == target_id and self._defense_is_researched(state, row)
            and bool(row.get("operational")) and self._coverage_matches(state, row, region)
        ]
        if sensors:
            probability = max(probability, max(self._finite(row.get("readiness")) for row in sensors) * 0.75)
        launch_order["launch_detected"] = self._roll(state, launch_order, "launch_detection") < probability
        attribution_probability = max(0.0, min(1.0, self._finite(state.globals.get("strategic_launch_attribution_probability", 0.5))))
        launch_order["launch_attributed"] = launch_order["launch_detected"] and self._roll(state, launch_order, "launch_attribution") < attribution_probability
        return launch_order

    def _resolve_defense(self, state, order, region, defenses, indexes=None):
        target = self._tag(order.get("target_country_id"))
        covered = [row for row in defenses if self._tag(row.get("country_id")) == target and self._defense_is_researched(state, row, indexes) and bool(row.get("operational")) and self._coverage_matches(state, row, region, indexes)]
        layer_order = state.globals.get("missile_defense_layer_order", ["long_range", "short_range"])
        order_index = {str(layer): index for index, layer in enumerate(layer_order)} if isinstance(layer_order, (list, tuple)) else {}
        covered.sort(key=lambda row: (order_index.get(str(row.get("layer")), 99), str(row.get("id"))))
        results = []
        for defense in covered:
            layer = str(defense.get("layer") or "")
            defaults = DEFAULT_DEFENSE.get(layer)
            layer_readiness = min(1.0, max(0.0, self._finite(defense.get("readiness"))))
            if defaults is None or layer_readiness <= 0.0:
                continue
            first_p = self._probability(defense.get("first_attempt_probability"), defaults[0]) * layer_readiness
            first = self._roll(state, order, layer + ":1") < first_p
            self._consume_defense_readiness(state, defense)
            results.append({"layer": layer, "attempt": 1, "probability": first_p, "intercepted": first})
            if first:
                return True, results
            second_p = self._probability(defense.get("second_attempt_probability"), defaults[1])
            if second_p > 0.0:
                second_p *= layer_readiness
                second = self._roll(state, order, layer + ":2") < second_p
                self._consume_defense_readiness(state, defense)
                results.append({"layer": layer, "attempt": 2, "probability": second_p, "intercepted": second})
                if second:
                    return True, results
        return False, results

    def _apply_impact(self, state, order, region, impacts, countries, now, indexes=None):
        level = int(order.get("payload_level") or 1)
        bounded_scale = min(0.3, max(0.01, math.log10(max(1.0, self._finite(order.get("yield_kt")))) / 25.0))
        mode = str(order.get("target_mode") or "military")
        if mode == "military":
            self._record_impact(impacts, order, "military_capability", bounded_scale, False, now)
            if "units" in state.tables:
                units = state.get_table("units")
                rows = units.to_dicts()
                object_id = str(order.get("target_object_id") or "")
                readiness_policy = ReadinessPolicy()
                readiness_affected = 0
                for unit in rows:
                    if (
                        int(unit.get("current_region_id") or 0) == int(region.get("id") or 0)
                        and self._tag(unit.get("owner")) == self._tag(order.get("target_country_id"))
                        and (not object_id or str(unit.get("id") or "") == object_id)
                        and int(unit.get("strength") or 0) > 0
                    ):
                        loss = max(0, int(round(int(unit.get("strength") or 0) * min(0.25, bounded_scale))))
                        unit["strength"] = max(0, int(unit.get("strength") or 0) - loss)
                        unit_id = str(unit.get("id") or "")
                        transitioning = unit_id in (indexes.units_in_readiness_transition if indexes is not None else ())
                        transitioning = transitioning or bool(unit.get("readiness_transition_id"))
                        if "readiness_status" in units.columns and not transitioning:
                            current = readiness_policy.normalize(unit.get("readiness_status"))
                            target = (
                                READINESS_READY if current == READINESS_FORTIFIED
                                else READINESS_PARKED if current == READINESS_READY
                                else current
                            )
                            if target != current:
                                unit["readiness_status"] = target
                                for column, value in (
                                    ("readiness_progress", 0.0),
                                    ("readiness_transition_id", ""),
                                    ("readiness_eta_minute", 0),
                                ):
                                    if column in units.columns:
                                        unit[column] = value
                                readiness_affected += 1
                state.update_table("units", pl.DataFrame(rows, schema=units.schema))
                if readiness_affected:
                    self._record_impact(impacts, order, "unit_readiness", bounded_scale, False, now)
            self._record_impact(impacts, order, "infrastructure", bounded_scale * 0.5, False, now)
            self._record_impact(impacts, order, "communications", bounded_scale * 0.25, False, now)
        else:
            self._record_impact(impacts, order, "population_health", bounded_scale, False, now)
            self._record_impact(impacts, order, "economic_disruption", bounded_scale * 0.65, False, now)
            self._record_impact(impacts, order, "infrastructure", bounded_scale, False, now)
            self._record_impact(impacts, order, "migration_pressure", min(0.25, bounded_scale * 0.2), False, now)
            self._record_impact(impacts, order, "environmental_damage", min(0.25, bounded_scale * 0.15), False, now)
        collateral = min(0.15, bounded_scale * 0.2)
        if collateral:
            self._record_impact(impacts, order, "collateral_infrastructure", collateral, True, now)
        self._apply_supported_region_effects(state, region, order, bounded_scale, impacts, now)
        if mode == "civilian":
            self._apply_supported_country_effects(countries, order, bounded_scale)

    def _apply_supported_region_effects(self, state, region, order, severity, impacts, now):
        regions = state.get_table("regions")
        rows = regions.to_dicts()
        target_id = int(region.get("id") or 0)
        originals = regions.to_dicts()
        for row in rows:
            if int(row.get("id") or 0) != target_id:
                continue
            for column in ("infrastructure", "infrastructure_health", "communications", "health_capacity"):
                if column in regions.columns and row.get(column) is not None:
                    row[column] = max(0.0, self._finite(row.get(column)) * (1.0 - min(0.3, severity)))
            if str(order.get("target_mode")) == "civilian":
                population_loss = min(0.1, severity * 0.2)
                for column in ("population", "total_population"):
                    if column in regions.columns and row.get(column) is not None:
                        row[column] = max(0.0, self._finite(row.get(column)) * (1.0 - population_loss))
                # Standard region schemas keep population in age bands, not a single total column.
                for column in ("pop_14", "pop_15_64", "pop_65"):
                    if column in regions.columns and row.get(column) is not None:
                        population = max(0.0, self._finite(row.get(column)))
                        row[column] = max(0, int(round(population * (1.0 - population_loss))))
                if "migration_pressure" in regions.columns and row.get("migration_pressure") is not None:
                    row["migration_pressure"] = min(1.0, max(0.0, self._finite(row.get("migration_pressure")) + min(0.25, severity * 0.2)))
                for column in ("environmental_health", "environment_health"):
                    if column in regions.columns and row.get(column) is not None:
                        row[column] = max(0.0, min(1.0, self._finite(row.get(column)) * (1.0 - min(0.25, severity * 0.15))))
        if rows != originals:
            state.update_table("regions", pl.DataFrame(rows, schema=regions.schema))

        collateral_radius = max(0.0, self._finite(order.get("blast_radius_km")))
        collateral_scale = min(0.05, max(0.0, severity * 0.1))
        if collateral_radius <= 0.0 or collateral_scale <= 0.0:
            return
        affected = sorted(
            (candidate for candidate in originals if int(candidate.get("id") or 0) != target_id
             and self._distance_km(region, candidate) <= collateral_radius),
            key=lambda candidate: (self._distance_km(region, candidate), int(candidate.get("id") or 0)),
        )[:10]
        for collateral_region in affected:
            self._record_impact(
                impacts, order, "collateral_infrastructure", collateral_scale, True, now,
                region_id=int(collateral_region.get("id") or 0),
                country_id=self._tag(collateral_region.get("owner")),
            )
            row = next((candidate for candidate in rows if int(candidate.get("id") or 0) == int(collateral_region.get("id") or 0)), None)
            if row is None:
                continue
            for column in ("infrastructure", "infrastructure_health", "communications", "health_capacity"):
                if column in regions.columns and row.get(column) is not None:
                    row[column] = max(0.0, self._finite(row.get(column)) * (1.0 - collateral_scale))
        if affected:
            state.update_table("regions", pl.DataFrame(rows, schema=regions.schema))

    def _apply_supported_country_effects(self, countries, order, severity):
        target = self._tag(order.get("target_country_id"))
        country = next((row for row in countries if self._tag(row.get("id")) == target), None)
        if country is None:
            return
        if "gdp" in country:
            country["gdp"] = max(0.0, self._finite(country.get("gdp")) * (1.0 - min(0.15, severity * 0.5)))
        if "economic_health" in country:
            country["economic_health"] = max(0.0, min(1.0, self._finite(country.get("economic_health")) - min(0.1, severity * 0.2)))
        # OpenPower's country contract uses gvt_approval; retain the legacy alias only for custom tables.
        if "gvt_approval" in country:
            country["gvt_approval"] = max(0.0, min(100.0, self._finite(country.get("gvt_approval")) - min(10.0, severity * 30.0)))
        elif "approval_rating" in country:
            country["approval_rating"] = max(0.0, min(100.0, self._finite(country.get("approval_rating")) - min(10.0, severity * 30.0)))

    def _record_impact(self, rows, order, category, severity, collateral, now, *, region_id=None, country_id=None):
        rows.append({
            "id": self._next_id("impact", rows), "launch_order_id": order["id"],
            "target_country_id": country_id or order["target_country_id"], "region_id": int(region_id if region_id is not None else order["target_region_id"]),
            "target_mode": order["target_mode"], "category": category,
            "severity": min(1.0, max(0.0, self._finite(severity))), "collateral": bool(collateral),
            "created_at_minute": now,
        })

    def _research_permits(self, state, owner, weapon, indexes=None):
        if not bool(state.globals.get("strategic_research_gate_enabled", True)):
            return True
        if "research_tracks" not in state.tables:
            return False
        required_program = max(1, int(self._finite(state.globals.get("strategic_program_research_level", 1))))
        required_weapon = max(
            1,
            int(self._finite(state.globals.get("strategic_weapon_research_level", 1))),
            int(self._finite(weapon.get("required_research_level"))),
        )
        levels = (
            indexes.research_levels_by_country.get(owner, {})
            if indexes is not None
            else self._research_levels(state, owner)
        )
        return (
            levels.get("strategic_program", 0) >= required_program
            and levels.get("strategic_weapons", 0) >= required_weapon
        )

    def _defense_is_researched(self, state, defense, indexes=None):
        if not bool(defense.get("researched")):
            return False
        if not bool(state.globals.get("strategic_research_gate_enabled", True)):
            return True
        if "research_tracks" not in state.tables:
            return False
        owner = self._tag(defense.get("country_id"))
        levels = (
            indexes.research_levels_by_country.get(owner, {})
            if indexes is not None
            else self._research_levels(state, owner)
        )
        required = max(1, int(self._finite(state.globals.get("strategic_defense_research_level", 1))))
        return levels.get("strategic_program", 0) >= required and levels.get("strategic_defense", 0) >= required

    def _researched_payload_cap(self, state, owner, weapon, indexes=None):
        design_cap = min(10, max(1, int(weapon.get("max_payload_level") or 1)))
        if "research_tracks" not in state.tables:
            return design_cap
        levels = (
            indexes.research_levels_by_country.get(owner, {})
            if indexes is not None
            else self._research_levels(state, owner)
        )
        level = levels.get("strategic_weapons", 0)
        return min(design_cap, max(0, level))

    def _launch_authorized(self, state, owner, target, context):
        policy = str(state.globals.get("strategic_authorization_policy", "war_or_explicit"))
        if policy == "open":
            return True
        approved = state.globals.get("strategic_authorized_countries", [])
        if isinstance(approved, (list, tuple, set)) and owner in {self._tag(item) for item in approved}:
            return True
        if context and context in set(state.globals.get("strategic_authorization_contexts", [])):
            return True
        if policy in {"explicit", "war_or_explicit"} and context:
            return False
        wars = state.tables.get("countries_wars")
        if wars is None:
            return False
        for row in wars.to_dicts():
            if str(row.get("status") or "active").lower() in {"ended", "inactive", "peace"}:
                continue
            participants = {self._tag(item) for side in (row.get("side_a") or [], row.get("side_b") or []) for item in side}
            participants.update(self._tag(row.get(key)) for key in ("attacker", "defender", "source_country", "target_country", "country_a", "country_b"))
            if owner in participants and target in participants:
                return True
        return False

    def _payload_profile(self, state, level):
        override = state.globals.get("strategic_payload_profiles", {})
        configured = override.get(str(level), override.get(level)) if isinstance(override, dict) else None
        if isinstance(configured, dict):
            return max(0.0, self._finite(configured.get("yield_kt"))), max(0.0, self._finite(configured.get("blast_radius_km")))
        return PAYLOAD_PROFILES[level]

    def _coverage_matches(self, state, defense, region, indexes=None):
        listed = defense.get("coverage_region_ids") or []
        explicit_match = int(region.get("id") or 0) in {int(item) for item in listed}
        center_lat = defense.get("center_latitude")
        center_lon = defense.get("center_longitude")
        if center_lat is None or center_lon is None:
            center = self._home_region(state, self._tag(defense.get("country_id")), indexes)
            center_lat = None if center is None else center.get("latitude")
            center_lon = None if center is None else center.get("longitude")
        has_center = center_lat is not None and center_lon is not None
        if not has_center:
            return explicit_match
        defense_center = {"latitude": center_lat, "longitude": center_lon}
        distance = self._distance_km(defense_center, region)
        range_km = max(0.0, self._finite(defense.get("range_km")))
        if range_km > 0.0 and distance > range_km:
            return False
        radius = max(0.0, self._finite(defense.get("coverage_radius_km")))
        if radius > 0.0 and distance > radius:
            return explicit_match and (range_km <= 0.0 or distance <= range_km)
        return explicit_match or radius > 0.0 or range_km > 0.0

    def _consume_defense_readiness(self, state, defense):
        cost = max(0.0, min(1.0, self._finite(state.globals.get("missile_defense_readiness_cost", 0.05))))
        defense["readiness"] = max(0.0, min(1.0, self._finite(defense.get("readiness")) - cost))

    def _maintain_defenses(self, state, defenses, countries, indexes=None):
        country_by_id = {self._tag(row.get("id")): row for row in countries}
        reference_area = max(1.0, self._finite(state.globals.get("missile_defense_maintenance_reference_area_km2", 1_000_000.0)))
        region_area = max(1.0, self._finite(state.globals.get("missile_defense_region_area_km2", 10_000.0)))
        for defense in defenses:
            if not self._defense_is_researched(state, defense, indexes) or not bool(defense.get("operational")):
                continue
            country = country_by_id.get(self._tag(defense.get("country_id")))
            if country is None:
                defense["operational"] = False
                continue
            listed_regions = defense.get("coverage_region_ids") or []
            radius = max(0.0, self._finite(defense.get("coverage_radius_km")))
            area = math.pi * radius * radius if radius > 0.0 else len(listed_regions) * region_area
            scale = max(0.0, area / reference_area)
            cost = max(0.0, self._finite(defense.get("maintenance_cost"))) * scale
            balance = self._finite(country.get("money_reserves"))
            if balance < cost:
                defense["operational"] = False
                continue
            country["money_reserves"] = balance - cost

    def _roll(self, state, order, salt):
        key = f"{state.determinism.seed}:{order['id']}:{salt}"
        value = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:16], 16)
        return value / float(0xFFFFFFFFFFFFFFFF)

    def _region_by_id(self, state, region_id, indexes=None):
        if indexes is not None:
            return indexes.regions_by_id.get(region_id)
        regions = state.tables.get("regions")
        if regions is None:
            return None
        return next((row for row in regions.to_dicts() if int(row.get("id") or 0) == region_id), None)

    def _home_region(self, state, country, indexes=None):
        if indexes is not None:
            return indexes.home_region_by_country.get(country)
        regions = state.tables.get("regions")
        if regions is None:
            return None
        candidates = [row for row in regions.to_dicts() if self._tag(row.get("owner")) == country]
        governments = state.tables.get("country_governments")
        if governments is not None:
            government = next((row for row in governments.to_dicts() if self._tag(row.get("country_id")) == country), None)
            if government:
                capital = int(government.get("capital_region_id") or 0)
                match = next((row for row in candidates if int(row.get("id") or 0) == capital), None)
                if match:
                    return match
        return min(candidates, key=lambda row: int(row.get("id") or 0)) if candidates else None

    def _research_levels(self, state, country):
        tracks = state.tables.get("research_tracks")
        if tracks is None:
            return {}
        levels = {}
        for row in tracks.to_dicts():
            if self._tag(row.get("country_id")) == country:
                branch = str(row.get("branch") or "").strip().lower()
                levels[branch] = max(levels.get(branch, 0), max(0, int(row.get("research_level") or 0)))
        return levels

    def _distance_km(self, left, right):
        lat1, lon1 = math.radians(self._finite(left.get("latitude"))), math.radians(self._finite(left.get("longitude")))
        lat2, lon2 = math.radians(self._finite(right.get("latitude"))), math.radians(self._finite(right.get("longitude")))
        delta_lat, delta_lon = lat2 - lat1, lon2 - lon1
        value = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
        return 6371.0 * 2.0 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1.0 - value)))

    def _publish_transition(self, state, order, event_buffer=None):
        state.events.append(EventStrategicStrikeTransition(str(order["id"]), str(order["status"]), str(order["target_country_id"]), int(order["target_region_id"]), int(state.time.total_minutes)))
        if (event_buffer is not None and event_buffer.messages is None) or (
            event_buffer is None and "messages" not in state.tables
        ):
            return
        owner = self._tag(order.get("country_id"))
        target = self._tag(order.get("target_country_id"))
        status = str(order.get("status") or "")
        if status == "pending":
            recipients = [(owner, f"Launch order {order['id']} is active. Target alert: {'detected' if order.get('launch_detected') else 'not detected'}.")]
            if bool(order.get("launch_detected")):
                attribution = f" The launching country is estimated as {owner}." if bool(order.get("launch_attributed")) else " The launch source is unknown."
                recipients.append((target, f"Early-warning systems detected an incoming strategic launch. Impact details remain unconfirmed.{attribution}"))
                observers = state.globals.get("strategic_observer_country_ids", [])
                if isinstance(observers, (list, tuple, set)):
                    recipients.extend((self._tag(observer), "An incoming strategic launch was detected; target and impact remain unconfirmed.") for observer in sorted(observers, key=str) if self._tag(observer) not in {owner, target})
        else:
            recipients = [(owner, f"Launch order {order['id']} resolved as {status}: {order.get('reason', '')}")]
            recipients.append((target, f"Strategic impact alert: order {order['id']} resolved as {status}. {order.get('reason', '')}"))
            if event_buffer is None:
                self._apply_escalation_relations(state, owner, target, status, bool(order.get("launch_detected")))
            else:
                event_buffer.add_escalation(owner, target, status, bool(order.get("launch_detected")))
        for recipient, body in recipients:
            if not recipient:
                continue
            if event_buffer is not None:
                event_buffer.add_message(state, recipient, status, body)
            elif "messages" in state.tables:
                table = state.get_table("messages")
                rows = table.to_dicts()
                message_id = self._next_id("strategic-message", rows)
                rows.append({
                    "id": message_id, "country_id": recipient,
                    "category": "strategic", "subject": f"Strategic strike {status}",
                    "body": body,
                    "is_read": False, "created_at": str(int(state.time.total_minutes)),
                })
                state.events.append(EventMessageCreated(message_id, recipient, "strategic"))
                state.update_table("messages", pl.DataFrame(rows, schema=table.schema))

    def _apply_escalation_relations(self, state, owner, target, status, detected):
        table = state.tables.get("countries_relations")
        if table is None:
            return
        delta = -8.0 if status == "impact" else -3.0 if status == "intercepted" else -1.0
        if detected:
            delta -= 2.0
        rows = table.to_dicts()
        pairs = {(owner, target), (target, owner)}
        matched = set()
        for row in rows:
            pair = (self._tag(row.get("source")), self._tag(row.get("target")))
            if pair in pairs:
                row["value"] = max(-100.0, min(100.0, self._finite(row.get("value")) + delta))
                matched.add(pair)
        for source, destination in sorted(pairs - matched):
            rows.append({"source": source, "target": destination, "value": delta})
        frame = pl.DataFrame(rows, schema=table.schema) if rows else pl.DataFrame(schema=table.schema)
        if not frame.equals(table):
            state.update_table("countries_relations", frame)

    def _reject(self, state, action, reason):
        state.journal.append_command_result({
            "tick": int(state.globals.get("tick", 0)), "player_id": str(action.player_id),
            "action_type": type(action).__name__, "status": "rejected", "reason": reason,
        })
        return None

    def _authorized(self, state, player_id, country):
        return player_controls_country(state, player_id, country)

    def _weapon_matches(self, row, requested):
        requested = str(requested or "").strip().lower()
        return requested in {str(row.get("weapon_type") or "").strip().lower(), str(row.get("weapon_class") or "").strip().lower()}

    def _probability(self, value, default):
        if value is None:
            return default
        return max(0.0, min(1.0, self._finite(value)))

    def _write(self, state, name, rows):
        frame = state.get_table(name)
        updated = pl.DataFrame(rows, schema=frame.schema) if rows else pl.DataFrame(schema=frame.schema)
        if not updated.equals(frame):
            state.update_table(name, updated)

    def _next_id(self, prefix, rows):
        return f"{prefix}-{len(rows) + 1:08d}"

    def _tag(self, value):
        return str(value or "").strip().upper()

    def _finite(self, value):
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        return result if result == result and abs(result) != float("inf") else 0.0
