"""Authoritative proposal, response, and settlement lifecycle for country trades."""

from __future__ import annotations

import json
import math
from typing import Any

import polars as pl

from modules.base.systems.world.authority_policy import player_controls_country
from modules.base.systems.world.bilateral_trade_policy import (
    apply_trade_package_frames,
    decode_trade_assets,
    encode_trade_assets,
    normalize_trade_assets,
    trade_package_value_frames,
    validate_trade_package_frames,
)
from src.shared.actions import (
    ActionCounterTradeDeal,
    ActionCreateTradeDeal,
    ActionRespondTradeDeal,
    ActionWithdrawTradeDeal,
)
from src.shared.determinism import DeterministicRuntime
from src.shared.events import (
    EventDiplomaticTradeChanged,
    EventNewDay,
    EventTerritoryOwnershipChanged,
)
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase


_TRADE_ACTIONS = (
    ActionCreateTradeDeal,
    ActionCounterTradeDeal,
    ActionRespondTradeDeal,
    ActionWithdrawTradeDeal,
)
_MAX_EXPIRY_DAYS = 365
_MINUTES_PER_DAY = 24 * 60


class BilateralTradeSystem(ISystem):
    """Runs diplomatic offers as validated, atomic two-country transactions."""

    access = SystemAccess(
        reads=frozenset(
            {
                "countries",
                "regions",
                "country_governments",
                "research_tracks",
                "occupations",
                "countries_wars",
                "diplomatic_trade_deals",
            }
        ),
        writes=frozenset(
            {
                "countries",
                "regions",
                "country_governments",
                "research_tracks",
                "diplomatic_trade_deals",
            }
        ),
        handles=frozenset(_TRADE_ACTIONS),
        phase=SystemPhase.TRADE,
    )

    @property
    def id(self) -> str:
        return "base.bilateral_trade"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.bootstrap", "base.diplomacy"]

    def update(self, state: GameState, delta_time: float) -> None:
        actions = [action for action in state.current_actions if isinstance(action, _TRADE_ACTIONS)]
        is_new_day = any(isinstance(event, EventNewDay) for event in state.events)
        deals_frame = state.tables.get("diplomatic_trade_deals")
        if deals_frame is None or (not actions and not is_new_day):
            return

        deals = deals_frame.to_dicts()
        for action in actions:
            if isinstance(action, ActionCreateTradeDeal):
                self._create(state, deals, action)
            elif isinstance(action, ActionCounterTradeDeal):
                self._counter(state, deals, action)
            elif isinstance(action, ActionRespondTradeDeal):
                self._respond(state, deals, action)
            elif isinstance(action, ActionWithdrawTradeDeal):
                self._withdraw(state, deals, action)

        if is_new_day:
            self._expire_and_process_ai(state, deals)
        state.update_table(
            "diplomatic_trade_deals",
            pl.DataFrame(deals, schema=deals_frame.schema, strict=False),
        )

    def _create(
        self, state: GameState, deals: list[dict[str, Any]], action: ActionCreateTradeDeal
    ) -> None:
        source = self._tag(action.source_country_tag)
        target = self._tag(action.target_country_tag)
        if not player_controls_country(state, action.player_id, source):
            self._reject_action(state, action, "The issuer does not control the proposing country.")
            return
        error = self._validate_participants(state, source, target)
        if error:
            self._reject_action(state, action, error)
            return
        self._create_row(
            state,
            deals,
            action,
            source,
            target,
            action.offered_assets,
            action.requested_assets,
            "",
        )

    def _counter(
        self, state: GameState, deals: list[dict[str, Any]], action: ActionCounterTradeDeal
    ) -> None:
        original = self._find_pending(deals, action.deal_id)
        counter_country = self._tag(action.counter_country_tag)
        if original is None:
            self._reject_action(state, action, "The trade offer is no longer pending.")
            return
        if int(original.get("expires_at_minute") or 0) <= self._now(state):
            self._resolve(state, original, "expired", "The trade offer expired before a counteroffer.", "expired", counter_country)
            self._reject_action(state, action, "The trade offer has expired.")
            return
        if counter_country != self._tag(original.get("target_country_id")):
            self._reject_action(state, action, "Only the recipient can counter this offer.")
            return
        if not player_controls_country(state, action.player_id, counter_country):
            self._reject_action(state, action, "The issuer does not control the countering country.")
            return
        proposer = self._tag(original.get("source_country_id"))
        error = self._validate_participants(state, counter_country, proposer)
        if error:
            self._reject_action(state, action, error)
            return
        new_row = self._create_row(
            state,
            deals,
            action,
            counter_country,
            proposer,
            action.offered_assets,
            action.requested_assets,
            str(original.get("id") or ""),
        )
        if new_row is None:
            return
        original["status"] = "countered"
        original["resolved_at_minute"] = self._now(state)
        original["countered_by_deal_id"] = str(new_row["id"])
        original["response_country_id"] = counter_country
        original["response"] = "counter"
        original["reason"] = f"{counter_country} submitted counteroffer {new_row['id']}."
        self._emit(state, original)

    def _create_row(
        self,
        state: GameState,
        deals: list[dict[str, Any]],
        action: Any,
        source: str,
        target: str,
        raw_offered: Any,
        raw_requested: Any,
        counter_to: str,
    ) -> dict[str, Any] | None:
        offered, error = normalize_trade_assets(raw_offered)
        if error:
            self._reject_action(state, action, error)
            return None
        requested, error = normalize_trade_assets(raw_requested)
        if error:
            self._reject_action(state, action, error)
            return None
        if not offered and not requested:
            self._reject_action(state, action, "A trade package must contain at least one asset.")
            return None
        error = self._validate_packages(state, source, target, offered, requested)
        if error:
            self._reject_action(state, action, error)
            return None

        try:
            expiry_days = int(action.expires_after_days)
        except (TypeError, ValueError, OverflowError):
            expiry_days = 30
        expiry_days = min(_MAX_EXPIRY_DAYS, max(1, expiry_days))
        now = self._now(state)
        deal_id = DeterministicRuntime(state.determinism).next_id(
            "trade", int(state.globals.get("tick", 0))
        )
        row = {
            "id": deal_id,
            "source_country_id": source,
            "target_country_id": target,
            "offered_assets_json": encode_trade_assets(offered),
            "requested_assets_json": encode_trade_assets(requested),
            "counter_to_deal_id": counter_to,
            "countered_by_deal_id": "",
            "created_by_player_id": str(action.player_id or ""),
            "created_at_minute": now,
            "expires_at_minute": now + expiry_days * _MINUTES_PER_DAY,
            "resolved_at_minute": 0,
            "response_country_id": "",
            "response": "",
            "status": "pending",
            "reason": f"Waiting for {target} to accept, reject, or counter the package.",
        }
        deals.append(row)
        self._emit(state, row)
        self._command_result(state, action, "applied", "Trade proposal created.")
        return row

    def _respond(
        self, state: GameState, deals: list[dict[str, Any]], action: ActionRespondTradeDeal
    ) -> None:
        row = self._find_pending(deals, action.deal_id)
        if row is None:
            self._reject_action(state, action, "The trade offer is no longer pending.")
            return
        responder = self._tag(action.responder_country_tag)
        target = self._tag(row.get("target_country_id"))
        if responder != target or not player_controls_country(state, action.player_id, responder):
            self._reject_action(state, action, "Only the controlled recipient can respond to this offer.")
            return
        now = self._now(state)
        if int(row.get("expires_at_minute") or 0) <= now:
            self._resolve(state, row, "expired", "The trade offer expired before a response.", "expired", responder)
            self._command_result(state, action, "rejected", "The trade offer has expired.")
            return
        if not action.accept:
            self._resolve(state, row, "rejected", f"{responder} rejected the package.", "rejected", responder)
            self._command_result(state, action, "applied", "Trade proposal rejected.")
            return

        source = self._tag(row.get("source_country_id"))
        offered = decode_trade_assets(row.get("offered_assets_json"))
        requested = decode_trade_assets(row.get("requested_assets_json"))
        error = self._validate_participants(state, source, target)
        if not error:
            error = self._validate_packages(state, source, target, offered, requested)
        if error:
            self._resolve(state, row, "rejected", f"Assets changed before acceptance: {error}", "rejected", responder)
            self._command_result(state, action, "rejected", error)
            return
        self._settle(state, row, offered, requested)
        self._resolve(
            state,
            row,
            "accepted",
            "Both countries' assets were validated and transferred atomically.",
            "accepted",
            responder,
        )
        self._command_result(state, action, "applied", "Bilateral trade settled.")

    def _withdraw(
        self, state: GameState, deals: list[dict[str, Any]], action: ActionWithdrawTradeDeal
    ) -> None:
        row = self._find_pending(deals, action.deal_id)
        source = self._tag(action.source_country_tag)
        if row is None:
            self._reject_action(state, action, "The trade offer is no longer pending.")
            return
        if int(row.get("expires_at_minute") or 0) <= self._now(state):
            self._resolve(state, row, "expired", "The trade offer expired before it was withdrawn.", "expired", source)
            self._reject_action(state, action, "The trade offer has expired.")
            return
        if source != self._tag(row.get("source_country_id")) or not player_controls_country(
            state, action.player_id, source
        ):
            self._reject_action(state, action, "Only the controlled proposing country can withdraw this offer.")
            return
        self._resolve(state, row, "withdrawn", f"{source} withdrew the offer.", "withdrawn", source)
        self._command_result(state, action, "applied", "Trade proposal withdrawn.")

    def _settle(
        self,
        state: GameState,
        deal: dict[str, Any],
        offered: list[dict[str, Any]],
        requested: list[dict[str, Any]],
    ) -> None:
        countries_frame = state.tables["countries"]
        regions_frame = state.tables["regions"]
        government_frame = state.tables.get("country_governments")
        tracks_frame = state.tables.get("research_tracks")
        ownership_changes = []
        for giver, receiver, assets in (
            (self._tag(deal.get("source_country_id")), self._tag(deal.get("target_country_id")), offered),
            (self._tag(deal.get("target_country_id")), self._tag(deal.get("source_country_id")), requested),
        ):
            for asset in assets:
                if asset.get("type") != "territory":
                    continue
                region_id = int(asset["region_id"])
                ownership_changes.append((region_id, giver, receiver))
        countries, regions, governments, tracks = apply_trade_package_frames(
            self._tag(deal.get("source_country_id")),
            self._tag(deal.get("target_country_id")),
            offered,
            requested,
            countries_frame,
            regions_frame,
            government_frame,
            tracks_frame,
        )
        updates = {
            "countries": countries,
            "regions": regions,
        }
        if government_frame is not None:
            updates["country_governments"] = governments
        if tracks_frame is not None:
            updates["research_tracks"] = tracks
        for table_name, frame in updates.items():
            state.update_table(table_name, frame)
        now = self._now(state)
        for region_id, previous_owner, owner in ownership_changes:
            state.events.append(
                EventTerritoryOwnershipChanged(
                    region_id=region_id,
                    previous_owner=previous_owner,
                    owner=owner,
                    source=f"bilateral_trade:{deal.get('id', '')}",
                    at_minute=now,
                )
            )

    def _expire_and_process_ai(self, state: GameState, deals: list[dict[str, Any]]) -> None:
        now = self._now(state)
        for row in deals:
            if row.get("status") != "pending":
                continue
            if int(row.get("expires_at_minute") or 0) <= now:
                self._resolve(state, row, "expired", "The response deadline passed.", "expired", "")
                continue
            target = self._tag(row.get("target_country_id"))
            if not self._is_ai_country(state, target):
                continue
            source = self._tag(row.get("source_country_id"))
            offered = decode_trade_assets(row.get("offered_assets_json"))
            requested = decode_trade_assets(row.get("requested_assets_json"))
            error = self._validate_participants(state, source, target)
            if not error:
                error = self._validate_packages(state, source, target, offered, requested)
            if error:
                self._resolve(state, row, "rejected", f"AI could not accept: {error}", "rejected", target)
                continue
            countries_frame = state.tables.get("countries")
            regions_frame = state.tables.get("regions")
            tracks_frame = state.tables.get("research_tracks")
            received_value = trade_package_value_frames(
                offered, source, target, countries_frame, regions_frame, tracks_frame
            )
            paid_value = trade_package_value_frames(
                requested, target, source, countries_frame, regions_frame, tracks_frame
            )
            if received_value + 0.01 < paid_value * 0.9:
                counter_assets = []
                if not self._is_ai_country(state, source):
                    counter_assets = self._build_ai_counter_package(
                        requested,
                        target,
                        source,
                        received_value / 0.9,
                        countries_frame,
                        regions_frame,
                        tracks_frame,
                    )
                if counter_assets:
                    self._counter(
                        state,
                        deals,
                        ActionCounterTradeDeal(
                            "AI_SYSTEM",
                            str(row.get("id") or ""),
                            target,
                            counter_assets,
                            offered,
                            30,
                        ),
                    )
                    continue
                self._resolve(
                    state,
                    row,
                    "rejected",
                    f"AI rejected the package: received value {received_value:.2f} is below the acceptance threshold for {paid_value:.2f} requested.",
                    "rejected",
                    target,
                )
                continue
            self._settle(state, row, offered, requested)
            self._resolve(
                state,
                row,
                "accepted",
                "AI accepted a package at or above its minimum exchange value.",
                "accepted",
                target,
            )

    def _build_ai_counter_package(
        self,
        requested_assets: list[dict[str, Any]],
        ai_country: str,
        player_country: str,
        value_limit: float,
        countries: pl.DataFrame | None,
        regions: pl.DataFrame | None,
        research_tracks: pl.DataFrame | None,
    ) -> list[dict[str, Any]]:
        remaining = max(0.0, value_limit)
        indivisible = sorted(
            (asset for asset in requested_assets if asset.get("type") != "cash"),
            key=lambda asset: (
                str(asset.get("type") or ""),
                str(asset.get("branch") or ""),
                int(asset.get("region_id") or 0),
            ),
        )
        counter_package: list[dict[str, Any]] = []
        for asset in indivisible:
            asset_value = trade_package_value_frames(
                [asset], ai_country, player_country, countries, regions, research_tracks
            )
            if asset_value <= remaining + 0.01:
                counter_package.append(dict(asset))
                remaining = max(0.0, remaining - asset_value)

        cash = sum(
            max(0.0, float(asset.get("amount") or 0.0))
            for asset in requested_assets
            if asset.get("type") == "cash"
        )
        partial_cash = round(min(cash, remaining), 2)
        if partial_cash >= 0.01:
            counter_package.append({"type": "cash", "amount": partial_cash})
        return counter_package

    def _validate_participants(self, state: GameState, source: str, target: str) -> str:
        if not source or not target or source == target:
            return "Choose two different valid countries."
        countries = state.tables.get("countries")
        if countries is None or "id" not in countries.columns:
            return "The countries table is unavailable."
        valid = {self._tag(value) for value in countries.get_column("id").to_list()}
        if source not in valid or target not in valid:
            return "Both countries must exist in the current world."
        wars = state.tables.get("countries_wars")
        if wars is not None:
            for war in wars.to_dicts():
                if str(war.get("status") or "active").casefold() != "active":
                    continue
                side_a = self._tags(war.get("side_a"))
                side_b = self._tags(war.get("side_b"))
                if (source in side_a and target in side_b) or (source in side_b and target in side_a):
                    return "Countries at war must negotiate through a peace deal."
        return ""

    def _validate_packages(
        self,
        state: GameState,
        source: str,
        target: str,
        offered: list[dict[str, Any]],
        requested: list[dict[str, Any]],
    ) -> str:
        countries = state.tables.get("countries")
        regions = state.tables.get("regions")
        if countries is None or regions is None:
            return "Country and territory data are required for bilateral trade."
        return validate_trade_package_frames(
            source,
            target,
            offered,
            requested,
            countries,
            regions,
            state.tables.get("country_governments"),
            state.tables.get("research_tracks"),
            state.tables.get("occupations"),
        )

    def _resolve(
        self,
        state: GameState,
        row: dict[str, Any],
        status: str,
        reason: str,
        response: str,
        responder: str,
    ) -> None:
        row["status"] = status
        row["resolved_at_minute"] = self._now(state)
        row["response_country_id"] = responder
        row["response"] = response
        row["reason"] = reason
        self._emit(state, row)

    def _emit(self, state: GameState, row: dict[str, Any]) -> None:
        state.events.append(
            EventDiplomaticTradeChanged(
                deal_id=str(row.get("id") or ""),
                source_country_id=self._tag(row.get("source_country_id")),
                target_country_id=self._tag(row.get("target_country_id")),
                status=str(row.get("status") or ""),
                reason=str(row.get("reason") or ""),
                at_minute=self._now(state),
            )
        )

    def _reject_action(self, state: GameState, action: Any, reason: str) -> None:
        self._command_result(state, action, "rejected", reason)

    def _command_result(self, state: GameState, action: Any, status: str, reason: str) -> None:
        state.journal.append_command_result(
            {
                "tick": int(state.globals.get("tick", 0)),
                "player_id": str(action.player_id or ""),
                "action_type": type(action).__name__,
                "status": status,
                "reason": reason,
            }
        )

    @staticmethod
    def _find_pending(deals: list[dict[str, Any]], deal_id: Any) -> dict[str, Any] | None:
        identifier = str(deal_id or "")
        return next(
            (row for row in deals if str(row.get("id") or "") == identifier and row.get("status") == "pending"),
            None,
        )

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

    @staticmethod
    def _tag(value: Any) -> str:
        return str(value or "").strip().upper()

    @classmethod
    def _tags(cls, values: Any) -> set[str]:
        if not isinstance(values, (list, tuple, set, frozenset)):
            return set()
        return {cls._tag(value) for value in values if cls._tag(value)}

    @staticmethod
    def _now(state: GameState) -> int:
        try:
            minute = int(state.time.total_minutes)
        except (TypeError, ValueError, OverflowError):
            minute = 0
        return max(0, minute) if math.isfinite(float(minute)) else 0
