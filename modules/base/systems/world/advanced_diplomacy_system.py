from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import polars as pl

from modules.base.systems.world.authority_policy import player_controls_country
from modules.base.systems.world.peace_deal_policy import PeaceDealPolicy
from src.shared.actions import ActionOfferPeace, ActionRespondPeaceDeal, ActionSubmitPeaceDeal
from src.shared.events import (
    EventPeaceDealProposed,
    EventPeaceDealResolved,
    EventTerritoryOwnershipChanged,
)
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_HELPER


class AdvancedDiplomacySystem(ISystem):
    """Owns structured peace packages while reusing the treaty system to close wars."""

    access = SystemAccess(
        reads=frozenset(
            {
                "countries",
                "countries_wars",
                "countries_treaties",
                "regions",
                "units",
                "unit_deployment_orders",
                "peace_deals",
                "debt_contracts",
                "demilitarization_limits",
            }
        ),
        writes=frozenset(
            {
                "countries",
                "countries_wars",
                "countries_treaties",
                "regions",
                "units",
                "unit_deployment_orders",
                "peace_deals",
                "debt_contracts",
                "demilitarization_limits",
            }
        ),
        handles=frozenset({ActionOfferPeace, ActionSubmitPeaceDeal, ActionRespondPeaceDeal}),
        phase=SystemPhase.DIPLOMACY,
    )
    runtime_state_contract = {"_policy": SYSTEM_STATE_HELPER}

    def __init__(self) -> None:
        self._policy = PeaceDealPolicy()

    @property
    def id(self) -> str:
        return "base.advanced_diplomacy"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.bootstrap"]

    def update(self, state: GameState, delta_time: float) -> None:
        actions = tuple(state.current_actions)
        has_action = any(
            isinstance(action, (ActionSubmitPeaceDeal, ActionRespondPeaceDeal))
            for action in actions
        )
        deals = state.tables.get("peace_deals")
        has_pending = deals is not None and not deals.is_empty() and bool(
            deals.filter(pl.col("status") == "pending").height
        )
        if not has_action and not has_pending:
            return

        deals = self._deals(deals)
        for action in actions:
            if isinstance(action, ActionSubmitPeaceDeal):
                deals = self._submit(state, action, deals)
            elif isinstance(action, ActionRespondPeaceDeal):
                deals = self._respond(state, action, deals)
            elif (
                isinstance(action, ActionOfferPeace)
                and str(action.player_id or "").strip().upper() in {"AI", "AI_SYSTEM"}
                and str(action.terms or "").strip().lower() != "war"
            ):
                deals = self._submit(
                    state,
                    ActionSubmitPeaceDeal(
                        action.player_id,
                        action.war_id,
                        action.source_country_tag,
                    ),
                    deals,
                )
        deals = self._evaluate_ai_responses(state, deals)
        deals = self._expire_pending(state, deals)
        state.update_table("peace_deals", deals)

    def _submit(
        self,
        state: GameState,
        action: ActionSubmitPeaceDeal,
        deals: pl.DataFrame,
    ) -> pl.DataFrame:
        war = self._war(state, action.war_id)
        proposer = self._tag(action.proposer_country_id)
        if war is None or str(war.get("status") or "active").lower() != "active":
            return deals
        side_a, side_b = self._tags(war.get("side_a")), self._tags(war.get("side_b"))
        leader_a = self._tag(war.get("leader_a")) or (min(side_a) if side_a else "")
        leader_b = self._tag(war.get("leader_b")) or (min(side_b) if side_b else "")
        if proposer not in {leader_a, leader_b} or not player_controls_country(
            state, action.player_id, proposer
        ):
            return deals

        if not deals.filter(
            (pl.col("war_id") == str(action.war_id)) & (pl.col("status") == "pending")
        ).is_empty():
            return deals
        offered, error = self._policy.normalize_clauses(action.offered_clauses)
        if error:
            return deals
        requested, error = self._policy.normalize_clauses(action.requested_clauses)
        if error:
            return deals
        clauses = offered + requested
        if len(clauses) > self._policy.MAX_CLAUSES:
            return deals
        error = self._policy.validate_clauses(state, war, proposer, clauses)
        if error:
            return deals

        try:
            expiry_days = int(action.expires_after_days)
        except (TypeError, ValueError, OverflowError):
            return deals
        if expiry_days < 1 or expiry_days > 365:
            return deals
        responding_side = sorted(side_b if proposer in side_a else side_a)
        if not responding_side:
            return deals

        now = max(0, int(state.time.total_minutes))
        signature = json.dumps(
            {
                "war_id": str(action.war_id),
                "proposer": proposer,
                "created_at": now,
                "offered": offered,
                "requested": requested,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        deal_id = "peace-" + hashlib.sha256(signature.encode("utf-8")).hexdigest()[:20]
        if deal_id in set(deals.get_column("id").to_list()):
            return deals

        row = {
            "id": deal_id,
            "war_id": str(action.war_id),
            "proposer_country_id": proposer,
            "responding_side": responding_side,
            "accepted_responses": [],
            "offered_clauses_json": json.dumps(offered, sort_keys=True, separators=(",", ":")),
            "requested_clauses_json": json.dumps(requested, sort_keys=True, separators=(",", ":")),
            "status": "pending",
            "created_at_minute": now,
            "expires_at_minute": now + expiry_days * 1440,
            "resolved_at_minute": 0,
            "acceptance_utility": 0.0,
            "reason": "Awaiting responses from every participant on the opposing war side.",
        }
        result = self._append(deals, row)
        state.events.append(
            EventPeaceDealProposed(
                deal_id,
                str(action.war_id),
                proposer,
                tuple(responding_side),
                now,
            )
        )
        return result

    def _respond(
        self,
        state: GameState,
        action: ActionRespondPeaceDeal,
        deals: pl.DataFrame,
    ) -> pl.DataFrame:
        matches = deals.filter(
            (pl.col("id") == str(action.deal_id)) & (pl.col("status") == "pending")
        )
        if matches.is_empty():
            return deals
        row = matches.row(0, named=True)
        responder = self._tag(action.responder_country_id)
        required = self._tags(row.get("responding_side"))
        accepted = self._tags(row.get("accepted_responses"))
        if (
            responder not in required
            or responder in accepted
            or not player_controls_country(state, action.player_id, responder)
        ):
            return deals

        now = max(0, int(state.time.total_minutes))
        if int(row.get("expires_at_minute") or 0) <= now:
            return self._resolve_row(state, deals, row, "expired", "The response deadline passed.")
        if not action.accept:
            return self._resolve_row(
                state,
                deals,
                row,
                "rejected",
                f"{responder} rejected the peace package.",
            )

        accepted.add(responder)
        row["accepted_responses"] = sorted(accepted)
        if not required.issubset(accepted):
            return self._replace(deals, row)

        war = self._war(state, row["war_id"])
        if war is None or str(war.get("status") or "active").lower() != "active":
            return self._resolve_row(state, deals, row, "rejected", "The war is no longer active.")
        clauses = self._decode_clauses(row.get("offered_clauses_json")) + self._decode_clauses(
            row.get("requested_clauses_json")
        )
        error = self._policy.validate_clauses(
            state,
            war,
            self._tag(row.get("proposer_country_id")),
            clauses,
        )
        if error:
            return self._resolve_row(state, deals, row, "rejected", error)

        regions = state.tables.get("regions")
        region_owners = (
            {
                int(region.get("id") or 0): self._tag(region.get("owner"))
                for region in regions.to_dicts()
            }
            if regions is not None
            else {}
        )
        ownership_transfers = [
            (
                int(clause["region_id"]),
                region_owners.get(int(clause["region_id"]), ""),
                self._tag(clause["new_owner_country_id"]),
            )
            for clause in clauses
            if clause["type"] == "territory_transfer"
            and region_owners.get(int(clause["region_id"]), "")
            != self._tag(clause["new_owner_country_id"])
        ]

        updates = self._apply_clauses(state, row, clauses)
        for table_name, frame in updates.items():
            state.update_table(table_name, frame)
        # Peace packages bypass TerritorySystem, so publish the ownership fact after commit.
        for region_id, previous_owner, owner in ownership_transfers:
            state.events.append(
                EventTerritoryOwnershipChanged(
                    region_id=region_id,
                    previous_owner=previous_owner,
                    owner=owner,
                    source="peace_deal",
                    at_minute=now,
                )
            )
        row["status"] = "accepted"
        row["resolved_at_minute"] = now
        row["reason"] = "All invited participants accepted; package clauses were applied."
        deals = self._replace(deals, row)
        state.events.append(
            EventPeaceDealResolved(
                str(row["id"]),
                str(row["war_id"]),
                "accepted",
                tuple(sorted(required)),
                now,
                str(row["reason"]),
            )
        )

        leader_a = self._tag(war.get("leader_a")) or min(self._tags(war.get("side_a")))
        leader_b = self._tag(war.get("leader_b")) or min(self._tags(war.get("side_b")))
        for leader in (leader_a, leader_b):
            state.current_actions.append(
                ActionOfferPeace("server", str(row["war_id"]), leader, "peace")
            )
        return deals

    def _apply_clauses(
        self,
        state: GameState,
        deal: dict[str, Any],
        clauses: list[dict[str, Any]],
    ) -> dict[str, pl.DataFrame]:
        countries = state.get_table("countries")
        country_rows = countries.to_dicts()
        country_by_id = {self._tag(row.get("id")): row for row in country_rows}
        regions = state.tables.get("regions")
        region_rows = regions.to_dicts() if regions is not None else []
        units = state.tables.get("units")
        unit_rows = units.to_dicts() if units is not None else []
        deployments = state.tables.get("unit_deployment_orders")
        deployment_rows = deployments.to_dicts() if deployments is not None else []
        treaties = state.tables.get("countries_treaties")
        treaty_rows = treaties.to_dicts() if treaties is not None else []
        contracts = state.tables.get("debt_contracts")
        contract_rows = contracts.to_dicts() if contracts is not None else []
        limits = state.tables.get("demilitarization_limits")
        limit_rows = limits.to_dicts() if limits is not None else []
        now = max(0, int(state.time.total_minutes))

        for index, clause in enumerate(clauses):
            clause_type = clause["type"]
            if clause_type == "war_reparations":
                duration = int(clause["duration_months"])
                amount = float(clause["amount"])
                contract_rows.append(
                    {
                        "id": f"peace-reparations-{deal['id']}-{index:02d}",
                        "debtor_country_id": clause["payer_country_id"],
                        "creditor_country_id": clause["recipient_country_id"],
                        "debt_type": "reparations",
                        "principal_original": amount,
                        "principal_remaining": amount,
                        "annual_interest_rate": 0.0,
                        "payment_frequency_months": 1,
                        "principal_payment": amount / duration,
                        "currency_code": "USD",
                        "conditions": f"peace_deal_id={deal['id']}",
                        "created_at_minute": now,
                        "next_payment_at_minute": now + 30 * 1440,
                        "maturity_at_minute": now + duration * 30 * 1440,
                        "maturity_months": duration,
                        "arrears_amount": 0.0,
                        "status": "current",
                        "reason": "Ratified peace-package reparations.",
                        "last_payment_at_minute": 0,
                    }
                )
            elif clause_type == "territory_transfer":
                region_id = int(clause["region_id"])
                new_owner = clause["new_owner_country_id"]
                for region in region_rows:
                    if int(region.get("id") or 0) == region_id:
                        region["owner"] = new_owner
                        if "controller" in region:
                            region["controller"] = new_owner
                        break
            elif clause_type == "treaty_annulment":
                for treaty in treaty_rows:
                    if str(treaty.get("id") or "") == clause["treaty_id"]:
                        treaty["status"] = "terminated"
                        if "expires_at_minute" in treaty:
                            treaty["expires_at_minute"] = now
                        break
            else:
                duration = int(clause["duration_days"])
                country_id = clause["country_id"]
                maximum_strength = int(clause["maximum_strength"])
                force_rows = sorted(
                    (
                        row
                        for row in unit_rows
                        if self._tag(row.get("owner")) == country_id
                    ),
                    key=lambda row: str(row.get("id") or ""),
                )
                excess = max(
                    0,
                    sum(max(0, int(row.get("strength") or 0)) for row in force_rows)
                    - maximum_strength,
                )
                for unit in force_rows:
                    reduction = min(excess, max(0, int(unit.get("strength") or 0)))
                    if reduction <= 0:
                        continue
                    unit["strength"] = max(0, int(unit.get("strength") or 0) - reduction)
                    excess -= reduction
                if country_id in country_by_id:
                    country = country_by_id[country_id]
                    current_count = max(0, int(country.get("military_count") or 0))
                    country["military_count"] = min(current_count, maximum_strength)
                limit_rows.append(
                    {
                        "id": f"peace-limit-{deal['id']}-{index:02d}",
                        "country_id": country_id,
                        "maximum_strength": int(clause["maximum_strength"]),
                        "source_deal_id": str(deal["id"]),
                        "effective_at_minute": now,
                        "expires_at_minute": now + duration * 1440,
                        "status": "active",
                    }
                )

        updates = {
            "countries": pl.DataFrame(country_rows, schema=countries.schema, strict=False),
            "debt_contracts": pl.DataFrame(
                contract_rows,
                schema=contracts.schema if contracts is not None else None,
                strict=False,
            ),
            "demilitarization_limits": pl.DataFrame(
                limit_rows,
                schema=limits.schema if limits is not None else None,
                strict=False,
            ),
        }
        if regions is not None:
            updates["regions"] = pl.DataFrame(region_rows, schema=regions.schema, strict=False)
        if units is not None:
            updates["units"] = pl.DataFrame(unit_rows, schema=units.schema, strict=False)
            if deployments is not None:
                live_strength = {
                    str(row.get("id") or ""): max(0, int(row.get("strength") or 0))
                    for row in unit_rows
                }
                for deployment in deployment_rows:
                    unit_id = str(deployment.get("unit_id") or "")
                    if unit_id in live_strength:
                        deployment["quantity"] = min(
                            max(0, int(deployment.get("quantity") or 0)),
                            live_strength[unit_id],
                        )
                updates["unit_deployment_orders"] = pl.DataFrame(
                    deployment_rows,
                    schema=deployments.schema,
                    strict=False,
                )
        if treaties is not None:
            updates["countries_treaties"] = pl.DataFrame(
                treaty_rows,
                schema=treaties.schema,
                strict=False,
            )
        return updates

    def _expire_pending(self, state: GameState, deals: pl.DataFrame) -> pl.DataFrame:
        now = max(0, int(state.time.total_minutes))
        rows = deals.to_dicts()
        updated = False
        for row in rows:
            if row.get("status") != "pending" or int(row.get("expires_at_minute") or 0) > now:
                continue
            row["status"] = "expired"
            row["resolved_at_minute"] = now
            row["reason"] = "The response deadline passed."
            self._emit_resolved(state, row)
            updated = True
        return self._frame(deals, rows) if updated else deals

    def _evaluate_ai_responses(
        self,
        state: GameState,
        deals: pl.DataFrame,
    ) -> pl.DataFrame:
        if deals.is_empty():
            return deals
        for deal in sorted(deals.to_dicts(), key=lambda row: str(row.get("id") or "")):
            if str(deal.get("status") or "") != "pending":
                continue
            war = self._war(state, str(deal.get("war_id") or ""))
            if war is None:
                continue
            accepted = self._tags(deal.get("accepted_responses"))
            offered = self._decode_clauses(deal.get("offered_clauses_json"))
            requested = self._decode_clauses(deal.get("requested_clauses_json"))
            for country in sorted(self._tags(deal.get("responding_side")) - accepted):
                if not self._is_ai_country(state, country):
                    continue
                utility = self._policy.evaluate_ai_acceptance(
                    state,
                    war,
                    country,
                    offered + requested,
                )
                live = deals.filter(
                    (pl.col("id") == str(deal.get("id") or ""))
                    & (pl.col("status") == "pending")
                )
                if live.is_empty():
                    break
                latest = live.row(0, named=True)
                previous_utility = float(latest.get("acceptance_utility") or 0.0)
                latest["acceptance_utility"] = min(
                    previous_utility if previous_utility > 0.0 else utility,
                    utility,
                )
                deals = self._replace(deals, latest)
                deals = self._respond(
                    state,
                    ActionRespondPeaceDeal(
                        "AI_SYSTEM",
                        str(deal.get("id") or ""),
                        country,
                        utility >= 0.55,
                    ),
                    deals,
                )
        return deals

    def _is_ai_country(self, state: GameState, country_id: str) -> bool:
        country = self._tag(country_id)
        controlled = state.globals.get("ai_controlled_countries")
        if isinstance(controlled, (list, tuple, set, frozenset)):
            return country in self._tags(controlled)
        player_map = state.globals.get("player_country_map", {})
        player_countries = (
            {self._tag(value) for value in player_map.values()}
            if isinstance(player_map, dict)
            else set()
        )
        player_country = self._tag(state.globals.get("player_tag"))
        if country in player_countries or country == player_country:
            return False
        return bool(player_countries or player_country)

    def _resolve_row(
        self,
        state: GameState,
        deals: pl.DataFrame,
        row: dict[str, Any],
        status: str,
        reason: str,
    ) -> pl.DataFrame:
        row["status"] = status
        row["resolved_at_minute"] = max(0, int(state.time.total_minutes))
        row["reason"] = reason
        self._emit_resolved(state, row)
        return self._replace(deals, row)

    def _emit_resolved(self, state: GameState, row: dict[str, Any]) -> None:
        state.events.append(
            EventPeaceDealResolved(
                str(row.get("id") or ""),
                str(row.get("war_id") or ""),
                str(row.get("status") or ""),
                tuple(sorted(self._tags(row.get("responding_side")))),
                max(0, int(state.time.total_minutes)),
                str(row.get("reason") or ""),
            )
        )

    def _war(self, state: GameState, war_id: str) -> dict[str, Any] | None:
        wars = state.tables.get("countries_wars")
        if wars is None or "id" not in wars.columns:
            return None
        matches = wars.filter(pl.col("id") == str(war_id))
        return None if matches.is_empty() else matches.row(0, named=True)

    def _deals(self, deals: pl.DataFrame | None) -> pl.DataFrame:
        if deals is not None:
            return deals
        return pl.DataFrame(
            schema={
                "id": pl.Utf8,
                "war_id": pl.Utf8,
                "proposer_country_id": pl.Utf8,
                "responding_side": pl.List(pl.Utf8),
                "accepted_responses": pl.List(pl.Utf8),
                "offered_clauses_json": pl.Utf8,
                "requested_clauses_json": pl.Utf8,
                "status": pl.Utf8,
                "created_at_minute": pl.Int64,
                "expires_at_minute": pl.Int64,
                "resolved_at_minute": pl.Int64,
                "acceptance_utility": pl.Float64,
                "reason": pl.Utf8,
            }
        )

    @staticmethod
    def _append(frame: pl.DataFrame, row: dict[str, Any]) -> pl.DataFrame:
        addition = pl.DataFrame([row], schema=frame.schema, strict=False)
        return pl.concat([frame, addition], how="vertical")

    @staticmethod
    def _replace(frame: pl.DataFrame, row: dict[str, Any]) -> pl.DataFrame:
        rows = [
            row if str(existing.get("id") or "") == str(row.get("id") or "") else existing
            for existing in frame.to_dicts()
        ]
        return AdvancedDiplomacySystem._frame(frame, rows)

    @staticmethod
    def _frame(frame: pl.DataFrame, rows: list[dict[str, Any]]) -> pl.DataFrame:
        return pl.DataFrame(rows, schema=frame.schema, strict=False)

    @staticmethod
    def _decode_clauses(value: Any) -> list[dict[str, Any]]:
        try:
            decoded = json.loads(str(value or "[]"))
        except (TypeError, ValueError):
            return []
        return decoded if isinstance(decoded, list) and all(isinstance(item, dict) for item in decoded) else []

    @staticmethod
    def _tag(value: Any) -> str:
        return str(value or "").strip().upper()

    @classmethod
    def _tags(cls, value: Any) -> set[str]:
        if isinstance(value, str):
            values = value.split(",")
        elif isinstance(value, (list, tuple, set)):
            values = value
        else:
            values = ()
        return {cls._tag(item) for item in values if cls._tag(item)}
