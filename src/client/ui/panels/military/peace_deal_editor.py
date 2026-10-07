from __future__ import annotations

import json
from typing import Any

import polars as pl
from imgui_bundle import imgui

from src.shared.actions import ActionRespondPeaceDeal, ActionSubmitPeaceDeal


class PeaceDealEditor:
    """Builds and responds to bounded multi-clause settlements in the war context."""

    CLAUSE_TYPES = (
        "White peace",
        "War reparations",
        "Territory transfer",
        "Treaty annulment",
        "Demilitarization",
    )
    DIRECTIONS = ("Request from the other side", "Offer to the other side")
    MAX_CLAUSES = 16

    def __init__(self) -> None:
        self._war_id = ""
        self._clause_type = 0
        self._direction = 0
        self._region_id = 0
        self._treaty_id = ""
        self._amount = 1_000_000.0
        self._duration_months = 12.0
        self._maximum_strength = 100.0
        self._duration_days = 365.0
        self._offered: list[dict[str, Any]] = []
        self._requested: list[dict[str, Any]] = []

    def render(self, state, war, country_tag: str, is_own_country: bool, net_client) -> None:
        if war is None:
            return
        war_id = str(war.get("id") or "")
        if self._war_id != war_id:
            self._war_id = war_id
            self._offered.clear()
            self._requested.clear()

        imgui.separator()
        imgui.text("STRUCTURED PEACE PACKAGE")
        self._render_proposal_builder(state, war, country_tag, is_own_country, net_client)
        self._render_responses(state, war, country_tag, is_own_country, net_client)

    def _render_proposal_builder(self, state, war, country_tag, is_own_country, net_client) -> None:
        side_a, side_b = self._tags(war.get("side_a")), self._tags(war.get("side_b"))
        leader_a = self._tag(war.get("leader_a")) or (min(side_a) if side_a else "")
        leader_b = self._tag(war.get("leader_b")) or (min(side_b) if side_b else "")
        country = self._tag(country_tag)
        if country not in {leader_a, leader_b}:
            imgui.text_disabled("Only a war leader can submit a package.")
            return

        _, self._clause_type = imgui.combo(
            "Clause type##peace",
            max(0, min(self._clause_type, len(self.CLAUSE_TYPES) - 1)),
            self.CLAUSE_TYPES,
        )
        _, self._direction = imgui.combo(
            "Package side##peace",
            max(0, min(self._direction, len(self.DIRECTIONS) - 1)),
            self.DIRECTIONS,
        )
        clause = self._render_clause_fields(state, side_a, side_b, country, leader_a, leader_b)

        can_submit = is_own_country and net_client is not None
        imgui.begin_disabled(not can_submit)
        can_add_clause = clause is not None and len(self._offered) + len(self._requested) < self.MAX_CLAUSES
        imgui.begin_disabled(not can_add_clause)
        if imgui.button("Add clause##peace") and can_add_clause:
            destination = self._offered if self._direction == 1 else self._requested
            destination.append(clause)
        imgui.end_disabled()
        imgui.same_line()
        if imgui.button("Clear package##peace"):
            self._offered.clear()
            self._requested.clear()
        imgui.end_disabled()

        imgui.text_disabled("Offered: " + (self._summarize(self._offered) or "none"))
        imgui.text_disabled("Requested: " + (self._summarize(self._requested) or "none"))
        imgui.begin_disabled(not can_submit)
        if imgui.button("Submit package##peace") and can_submit:
            net_client.send_action(
                ActionSubmitPeaceDeal(
                    player_id=net_client.player_id,
                    war_id=str(war.get("id") or ""),
                    proposer_country_id=country,
                    offered_clauses=list(self._offered),
                    requested_clauses=list(self._requested),
                )
            )
            self._offered.clear()
            self._requested.clear()
        imgui.end_disabled()

    def _render_clause_fields(self, state, side_a, side_b, country, leader_a, leader_b):
        opponent = leader_b if country in side_a else leader_a
        if self._clause_type == 0:
            imgui.text_disabled("An empty package requests a white peace.")
            return None
        if self._clause_type == 1:
            _, self._amount = imgui.input_float("Amount##reparations", self._amount, 100_000.0, 1_000_000.0, "%.0f")
            _, self._duration_months = imgui.input_float("Term in months##reparations", self._duration_months, 1.0, 12.0, "%.0f")
            payer, recipient = (opponent, country) if self._direction == 0 else (country, opponent)
            return {
                "type": "war_reparations",
                "payer_country_id": payer,
                "recipient_country_id": recipient,
                "amount": max(1.0, float(self._amount)),
                "duration_months": max(1, min(360, round(self._duration_months))),
            }
        if self._clause_type == 2:
            regions = state.tables.get("regions")
            participant_ids = side_a | side_b
            region_options = [] if regions is None else [
                (int(row.get("id") or 0), row)
                for row in regions.to_dicts()
                if int(row.get("id") or 0) > 0
                and self._tag(row.get("owner")) in participant_ids
                and self._tag(row.get("controller") or row.get("owner")) in participant_ids
                and self._tag(row.get("owner")) != self._tag(
                    country if self._direction == 0 else opponent
                )
            ]
            region_options.sort(key=lambda item: item[0])
            if not region_options:
                imgui.text_disabled("No occupied war-participant territory can be transferred.")
                return None
            self._region_id = self._select_id(
                "Region##peace",
                self._region_id,
                [(region_id, f"Region {region_id} — {row.get('owner')}") for region_id, row in region_options],
            )
            new_owner = country if self._direction == 0 else opponent
            return {
                "type": "territory_transfer",
                "region_id": int(self._region_id),
                "new_owner_country_id": new_owner,
            }
        if self._clause_type == 3:
            treaties = state.tables.get("countries_treaties")
            available = []
            for treaty in ([] if treaties is None else treaties.to_dicts()):
                members = self._tags(treaty.get("members"))
                if (
                    str(treaty.get("status") or "active").lower() == "active"
                    and members & side_a
                    and members & side_b
                ):
                    available.append((str(treaty.get("id") or ""), str(treaty.get("name") or treaty.get("id") or "")))
            if not available:
                imgui.text_disabled("No active treaty binds both sides of this war.")
                return None
            self._treaty_id = self._select_id("Treaty##peace", self._treaty_id, available)
            return {"type": "treaty_annulment", "treaty_id": self._treaty_id}

        _, self._maximum_strength = imgui.input_float("Force cap##peace", self._maximum_strength, 10.0, 100.0, "%.0f")
        _, self._duration_days = imgui.input_float("Duration in days##peace", self._duration_days, 30.0, 90.0, "%.0f")
        target = opponent if self._direction == 0 else country
        return {
            "type": "demilitarization",
            "country_id": target,
            "maximum_strength": max(0, round(self._maximum_strength)),
            "duration_days": max(1, min(3650, round(self._duration_days))),
        }

    def _render_responses(self, state, war, country_tag, is_own_country, net_client) -> None:
        deals = state.tables.get("peace_deals")
        if deals is None or deals.is_empty():
            return
        country = self._tag(country_tag)
        for deal in deals.filter(
            (pl.col("war_id") == str(war.get("id") or "")) & (pl.col("status") == "pending")
        ).to_dicts():
            required = self._tags(deal.get("responding_side"))
            accepted = self._tags(deal.get("accepted_responses"))
            if country not in required or country in accepted:
                continue
            offered = self._decode(deal.get("offered_clauses_json"))
            requested = self._decode(deal.get("requested_clauses_json"))
            imgui.text_wrapped(
                f"Package from {deal.get('proposer_country_id')}: "
                f"offered {self._summarize(offered) or 'none'}; "
                f"requested {self._summarize(requested) or 'none'}"
            )
            can_respond = bool(is_own_country and net_client is not None)
            imgui.begin_disabled(not can_respond)
            if imgui.button(f"Accept##{deal['id']}") and can_respond:
                net_client.send_action(
                    ActionRespondPeaceDeal(net_client.player_id, str(deal["id"]), country, True)
                )
            imgui.same_line()
            if imgui.button(f"Reject##{deal['id']}") and can_respond:
                net_client.send_action(
                    ActionRespondPeaceDeal(net_client.player_id, str(deal["id"]), country, False)
                )
            imgui.end_disabled()

    def _select_id(self, label: str, current: Any, options: list[tuple[Any, str]]):
        option_ids = [item[0] for item in options]
        index = option_ids.index(current) if current in option_ids else 0
        _, index = imgui.combo(label, index, [item[1] for item in options])
        return option_ids[max(0, min(int(index), len(option_ids) - 1))]

    @staticmethod
    def _decode(value: Any) -> list[dict[str, Any]]:
        try:
            decoded = json.loads(str(value or "[]"))
        except (TypeError, ValueError):
            return []
        return decoded if isinstance(decoded, list) and all(isinstance(item, dict) for item in decoded) else []

    @staticmethod
    def _summarize(clauses: list[dict[str, Any]]) -> str:
        return "; ".join(str(row.get("type") or "clause") for row in clauses)

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
