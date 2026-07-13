"""Authoritative diplomacy lifecycle and treaty-effect simulation.

This implementation intentionally owns treaty persistence, lifecycle, and
effects in one system.  Other systems consume the materialized treaty effects
table instead of reimplementing treaty semantics.
"""

from __future__ import annotations

import calendar
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping

import polars as pl

from modules.base.systems.world.treaty_geography import TreatyGeography
from modules.base.systems.world.annexation_policy import AnnexationPolicy
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.actions import (
    ActionCreateTreaty,
    ActionDeclareWar,
    ActionExpelTreatyMember,
    ActionJoinTreaty,
    ActionLeaveTreaty,
    ActionOfferPeace,
    ActionRespondTreaty,
)
from src.shared.events import (
    EventMessageCreated,
    EventNewDay,
    EventTreatyProposed,
    EventTreatyRefused,
    EventWarStarted,
)
from src.shared.state import GAME_EPOCH, GameState
from src.shared.treaties import (
    ANNEXATION_CLAIM_SCHEMA,
    PENDING_TREATY_SCHEMA,
    TREATY_DEFINITIONS,
    TREATY_EFFECT_SCHEMA,
    TREATY_SCHEMA,
    active_treaty_rows,
    decode_conditions,
    encode_conditions,
    normalize_country_tags,
    normalize_treaty_type,
    treaty_definition,
    treaty_members,
    treaty_side,
)


RELATIONS_SCHEMA = {"source": pl.Utf8, "target": pl.Utf8, "value": pl.Float64}
WAR_SCHEMA = {
    "id": pl.Utf8,
    "name": pl.Utf8,
    "side_a": pl.List(pl.Utf8),
    "side_b": pl.List(pl.Utf8),
    "status": pl.Utf8,
    "casus_belli": pl.Utf8,
    "created_at": pl.Utf8,
    "leader_a": pl.Utf8,
    "leader_b": pl.Utf8,
    "intent_a": pl.Utf8,
    "intent_b": pl.Utf8,
}
MESSAGE_SCHEMA = {
    "id": pl.Utf8,
    "country_id": pl.Utf8,
    "category": pl.Utf8,
    "subject": pl.Utf8,
    "body": pl.Utf8,
    "is_read": pl.Boolean,
    "created_at": pl.Utf8,
}
NEWS_SCHEMA = {
    "id": pl.Utf8,
    "headline": pl.Utf8,
    "body": pl.Utf8,
    "category": pl.Utf8,
    "severity": pl.Utf8,
    "related_country_id": pl.Utf8,
    "created_at": pl.Utf8,
}

SIX_MONTHS_IN_DAYS = 183
LONG_TERM_RELATION_DELTAS = {
    "alliance": 15.0,
    "cultural_exchanges": 8.0,
    "noble_cause": 6.0,
    "research_partnership": 7.0,
    "human_development_collaboration": 6.0,
    "economic_partnership": 10.0,
    "common_market": 10.0,
    "weapons_trade": 5.0,
    "economic_aid": 8.0,
}


@dataclass(frozen=True)
class _TreatyEligibilityIndex:
    countries: Mapping[str, Mapping[str, Any]]
    relations: Mapping[tuple[str, str], float]
    governments: Mapping[str, str]
    war_pairs: set[frozenset[str]]


class DiplomacySystem(ISystem):
    """Processes treaty commands and publishes deterministic gameplay effects."""

    access = SystemAccess(
        reads=frozenset({'countries', 'regions', 'units', 'countries_relations', 'countries_treaties', 'countries_wars', 'pending_treaties', 'treaty_effects', 'annexation_claims'}),
        writes=frozenset({'countries_relations', 'countries_treaties', 'countries_wars', 'pending_treaties', 'treaty_effects', 'annexation_claims', 'messages', 'news_items', 'regions'}),
        handles=frozenset(
            {
                ActionCreateTreaty,
                ActionDeclareWar,
                ActionExpelTreatyMember,
                ActionJoinTreaty,
                ActionLeaveTreaty,
                ActionOfferPeace,
                ActionRespondTreaty,
            }
        ),
        phase=SystemPhase.DIPLOMACY,
    )

    @property
    def id(self) -> str:
        return "base.diplomacy"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.bootstrap"]

    def update(self, state: GameState, delta_time: float) -> None:
        has_diplomatic_action = any(isinstance(
            action,
            (ActionCreateTreaty, ActionRespondTreaty, ActionJoinTreaty, ActionExpelTreatyMember, ActionLeaveTreaty, ActionDeclareWar, ActionOfferPeace),
        ) for action in state.current_actions)
        treaties_table = state.tables.get("countries_treaties")
        claims_table = state.tables.get("annexation_claims")
        has_new_day = any(isinstance(event, EventNewDay) for event in state.events)
        effects_table = state.tables.get("treaty_effects")
        if not has_diplomatic_action and not has_new_day and (claims_table is None or claims_table.is_empty()) and (treaties_table is None or treaties_table.is_empty() or (effects_table is not None and not effects_table.is_empty())):
            return
        treaties = self._treaties(state.tables.get("countries_treaties"))
        pending = self._pending(state.tables.get("pending_treaties"))
        wars = self._wars(state.tables.get("countries_wars"))
        relations = self._relations(state.tables.get("countries_relations"))
        messages = self._messages(state.tables.get("messages"))
        news = self._news(state.tables.get("news_items"))
        claims = self._claims(state.tables.get("annexation_claims"))

        for action in state.current_actions:
            if isinstance(action, ActionCreateTreaty):
                pending, messages, news = self._create_proposal(
                    state, action, treaties, pending, messages, news
                )
            elif isinstance(action, ActionRespondTreaty):
                treaties, pending, wars, relations, messages, news, claims = self._respond_to_proposal(
                    state, action, treaties, pending, wars, relations, messages, news, claims
                )
            elif isinstance(action, ActionJoinTreaty):
                treaties, messages = self._join_open_treaty(state, action, treaties, messages)
            elif isinstance(action, ActionExpelTreatyMember):
                treaties, messages = self._expel_treaty_member(state, action, treaties, messages)
            elif isinstance(action, ActionLeaveTreaty):
                treaties, relations, messages, news = self._leave_treaty(
                    state, action, treaties, relations, messages, news
                )
            elif isinstance(action, ActionDeclareWar):
                wars, relations, messages, news = self._start_war(
                    state,
                    source=action.source_country_tag,
                    target=action.target_country_tag,
                    casus_belli=action.casus_belli,
                    treaties=treaties,
                    wars=wars,
                    relations=relations,
                    messages=messages,
                    news=news,
                )
            elif isinstance(action, ActionOfferPeace):
                wars, relations, messages, news = self._offer_peace(
                    state, action, wars, relations, messages, news
                )

        if has_diplomatic_action or has_new_day:
            treaties = self._refresh_suspended_members(state, treaties, wars)
        claims, state_regions = self._resolve_annexation_claims(state, claims)
        if state_regions is not None:
            state.update_table("regions", state_regions)

        treaties, relations, effects = self._apply_long_term_effects(
            state, treaties, relations
        )
        state.update_table("countries_treaties", treaties)
        state.update_table("pending_treaties", pending)
        state.update_table("countries_wars", wars)
        state.update_table("countries_relations", relations)
        state.update_table("messages", messages)
        state.update_table("news_items", news)
        state.update_table("annexation_claims", claims)
        state.update_table("treaty_effects", effects)

    def _create_proposal(
        self,
        state: GameState,
        action: ActionCreateTreaty,
        treaties: pl.DataFrame,
        pending: pl.DataFrame,
        messages: pl.DataFrame,
        news: pl.DataFrame,
    ) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
        treaty_type = normalize_treaty_type(action.treaty_type)
        definition = treaty_definition(treaty_type)
        source = self._tag(action.source_country_tag)
        target = self._tag(action.target_country_tag)
        if definition is None or not source or not target or source == target:
            return pending, messages, news

        side_a = self._tags(action.side_a_country_tags) or (source,)
        side_b = self._tags(action.side_b_country_tags)
        if definition.two_sided:
            side_b = side_b or (target,)
            if not set(side_a).isdisjoint(side_b):
                return pending, messages, news
            members = tuple(sorted(set(side_a) | set(side_b)))
        else:
            members = self._tags(action.member_country_tags) or tuple(sorted({source, target}))
            if source not in members:
                members = tuple(sorted(set(members) | {source}))
            side_a = members
            side_b = ()

        if not definition.multi_member and len(members) != 2:
            return pending, messages, news
        if len(members) < 2 or not self._all_known_countries(state, members):
            return pending, messages, news
        if self._has_matching_treaty(treaties, pending, treaty_type, members):
            return pending, messages, news

        required = tuple(tag for tag in members if tag != source)
        proposal_id = self._next_identifier("treaty", pending["id"].to_list(), state)
        title = str(action.title or definition.label)
        conditions = encode_conditions(action.conditions)
        row = {
            "id": proposal_id,
            "source_country_id": source,
            "target_country_id": target,
            "treaty_type": treaty_type,
            "title": title,
            "terms": str(action.terms or ""),
            "side_a": list(side_a),
            "side_b": list(side_b),
            "members": list(members),
            "required_responses": list(required),
            "accepted_members": [source],
            "conditions_json": conditions,
            "open_to_new_members": bool(action.open_to_new_members and definition.long_term),
            "status": "pending",
            "created_at": self._timestamp(state),
        }
        pending = self._append(pending, PENDING_TREATY_SCHEMA, row)
        state.events.append(EventTreatyProposed(proposal_id, source, target))
        for recipient in required:
            messages = self._append_message(
                state,
                messages,
                recipient,
                "diplomacy",
                f"Treaty proposal from {source}",
                f"{source} proposes {definition.label}: {title}. Review the proposal in mail.",
            )
        news = self._append_news(
            state,
            news,
            headline=f"{source} proposes {title}",
            body=f"The {definition.label.lower()} proposal awaits the invited countries' responses.",
            category="diplomacy",
            related_country_id=source,
        )
        return pending, messages, news

    def _respond_to_proposal(
        self,
        state: GameState,
        action: ActionRespondTreaty,
        treaties: pl.DataFrame,
        pending: pl.DataFrame,
        wars: pl.DataFrame,
        relations: pl.DataFrame,
        messages: pl.DataFrame,
        news: pl.DataFrame,
        claims: pl.DataFrame,
    ) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
        matches = pending.filter(pl.col("id") == str(action.treaty_id))
        if matches.is_empty():
            return treaties, pending, wars, relations, messages, news, claims
        proposal = matches.to_dicts()[0]
        responder = self._tag(action.responder_country_tag)
        required = set(self._tags(proposal.get("required_responses")))
        accepted = set(self._tags(proposal.get("accepted_members")))
        if responder not in required or responder in accepted:
            return treaties, pending, wars, relations, messages, news, claims

        source = self._tag(proposal.get("source_country_id"))
        if not action.accept:
            pending = pending.filter(pl.col("id") != str(action.treaty_id))
            state.events.append(EventTreatyRefused(str(action.treaty_id), responder))
            relations = self._adjust_relation_pair(relations, source, responder, -5.0)
            messages = self._append_message(
                state, messages, source, "diplomacy", f"Treaty rejected by {responder}",
                f"{responder} rejected {proposal.get('title') or 'the treaty proposal'}.",
            )
            return treaties, pending, wars, relations, messages, news, claims

        accepted.add(responder)
        if not required.issubset(accepted):
            pending = self._replace_row(
                pending,
                PENDING_TREATY_SCHEMA,
                str(action.treaty_id),
                {**proposal, "accepted_members": sorted(accepted)},
            )
            return treaties, pending, wars, relations, messages, news, claims

        pending = pending.filter(pl.col("id") != str(action.treaty_id))
        treaty_type = normalize_treaty_type(proposal.get("treaty_type"))
        definition = treaty_definition(treaty_type)
        if definition is None:
            return treaties, pending, wars, relations, messages, news, claims
        members = self._tags(proposal.get("members"))
        record = {
            "id": self._next_identifier("agreement", treaties["id"].to_list(), state),
            "name": str(proposal.get("title") or definition.label),
            "type": treaty_type,
            "members": list(members),
            "side_a": list(self._tags(proposal.get("side_a"))),
            "side_b": list(self._tags(proposal.get("side_b"))),
            "status": "active" if definition.long_term else "completed",
            "terms": str(proposal.get("terms") or ""),
            "conditions_json": str(proposal.get("conditions_json") or encode_conditions(None)),
            "open_to_new_members": bool(proposal.get("open_to_new_members", False) and definition.long_term),
            "suspended_members": [],
            "created_at": self._timestamp(state),
            "activated_at_minute": int(state.time.total_minutes),
            "expires_at_minute": 0,
            "maintenance_cost": 0.0,
            "source_country_id": source,
            "target_country_id": self._tag(proposal.get("target_country_id")),
        }
        treaties = self._append(treaties, TREATY_SCHEMA, record)
        relations = self._apply_activation_relations(relations, treaty_type, members)
        treaties, wars, relations, messages, news, claims = self._apply_punctual_effect(
            state, record, treaties, wars, relations, messages, news, claims
        )
        for member in members:
            messages = self._append_message(
                state, messages, member, "diplomacy", f"{record['name']} is effective",
                f"All invited countries accepted the {definition.label.lower()}.",
            )
        news = self._append_news(
            state, news, f"{record['name']} enters into force",
            "The agreement has become effective and its treaty rules are now applied.",
            "diplomacy", source,
        )
        return treaties, pending, wars, relations, messages, news, claims

    def _join_open_treaty(
        self,
        state: GameState,
        action: ActionJoinTreaty,
        treaties: pl.DataFrame,
        messages: pl.DataFrame,
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        matches = treaties.filter(pl.col("id") == str(action.treaty_id))
        candidate = self._tag(action.country_tag)
        if matches.is_empty() or not candidate:
            return treaties, messages
        row = matches.to_dicts()[0]
        definition = treaty_definition(row.get("type"))
        members = self._tags(row.get("members"))
        if (
            definition is None
            or not definition.long_term
            or not bool(row.get("open_to_new_members"))
            or candidate in members
            or not self._country_exists(state, candidate)
            or not self._eligible_for_treaty(state, row, candidate, members)
        ):
            return treaties, messages
        updated = {**row, "members": sorted(set(members) | {candidate})}
        if not definition.two_sided:
            updated["side_a"] = updated["members"]
        treaties = self._replace_row(treaties, TREATY_SCHEMA, str(action.treaty_id), updated)
        messages = self._append_message(
            state, messages, candidate, "diplomacy", "Treaty membership accepted",
            f"You automatically joined {row.get('name') or row.get('id')} after meeting its conditions.",
        )
        return treaties, messages

    def _expel_treaty_member(
        self,
        state: GameState,
        action: ActionExpelTreatyMember,
        treaties: pl.DataFrame,
        messages: pl.DataFrame,
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        matches = treaties.filter(pl.col("id") == str(action.treaty_id))
        if matches.is_empty():
            return treaties, messages
        row = matches.to_dicts()[0]
        sponsor = self._tag(row.get("source_country_id"))
        member = self._tag(action.country_tag)
        members = self._tags(row.get("members"))
        if sponsor != self._tag(action.player_id) or member not in members or member == sponsor:
            return treaties, messages
        remaining = tuple(tag for tag in members if tag != member)
        if len(remaining) < 2:
            treaties = treaties.filter(pl.col("id") != str(action.treaty_id))
        else:
            updated = {**row, "members": list(remaining), "suspended_members": []}
            treaties = self._replace_row(treaties, TREATY_SCHEMA, str(action.treaty_id), updated)
        messages = self._append_message(
            state, messages, member, "diplomacy", "Treaty membership ended",
            f"You were removed from {row.get('name') or row.get('id')} by its sponsor.",
        )
        return treaties, messages

    def _leave_treaty(
        self,
        state: GameState,
        action: ActionLeaveTreaty,
        treaties: pl.DataFrame,
        relations: pl.DataFrame,
        messages: pl.DataFrame,
        news: pl.DataFrame,
    ) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
        matches = treaties.filter(pl.col("id") == str(action.treaty_id))
        member = self._tag(action.country_tag)
        if matches.is_empty():
            return treaties, relations, messages, news
        row = matches.to_dicts()[0]
        members = self._tags(row.get("members"))
        if member not in members:
            return treaties, relations, messages, news
        remaining = tuple(tag for tag in members if tag != member)
        for peer in remaining:
            relations = self._adjust_relation_pair(
                relations, member, peer, -0.5 * self._relation_delta(row.get("type"))
            )
        if len(remaining) < 2:
            treaties = treaties.filter(pl.col("id") != str(action.treaty_id))
        else:
            updated = {**row, "members": list(remaining)}
            if not treaty_definition(row.get("type")).two_sided:
                updated["side_a"] = list(remaining)
            treaties = self._replace_row(treaties, TREATY_SCHEMA, str(action.treaty_id), updated)
        messages = self._append_message(
            state, messages, member, "diplomacy", "Treaty membership ended",
            f"You left {row.get('name') or row.get('id')}.",
        )
        news = self._append_news(
            state, news, f"{member} leaves {row.get('name') or row.get('id')}",
            "The agreement's membership has been updated.", "diplomacy", member,
        )
        return treaties, relations, messages, news

    def _start_war(
        self,
        state: GameState,
        *,
        source: Any,
        target: Any,
        casus_belli: str,
        treaties: pl.DataFrame,
        wars: pl.DataFrame,
        relations: pl.DataFrame,
        messages: pl.DataFrame,
        news: pl.DataFrame,
    ) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
        attacker, defender = self._tag(source), self._tag(target)
        if not attacker or not defender or attacker == defender or self._active_war(wars, attacker, defender):
            return wars, relations, messages, news
        side_a = self._expand_allies(treaties, attacker)
        side_b = self._expand_allies(treaties, defender)
        side_a.discard(defender)
        side_b.discard(attacker)
        side_a -= (side_a & side_b) - {attacker}
        war_id = self._next_identifier("war", wars["id"].to_list(), state)
        row = {
            "id": war_id,
            "name": f"{attacker} vs {defender}",
            "side_a": sorted(side_a),
            "side_b": sorted(side_b),
            "status": "active",
            "casus_belli": str(casus_belli or ""),
            "created_at": self._timestamp(state),
            "leader_a": attacker,
            "leader_b": defender,
            "intent_a": "war",
            "intent_b": "war",
        }
        wars = self._append(wars, WAR_SCHEMA, row)
        state.events.append(EventWarStarted(war_id, attacker, defender))
        hostile_pairs = {
            (left, right)
            for left in side_a
            for right in side_b
            if left != right
        }
        relations = self._set_relation_pairs(relations, hostile_pairs, -100.0)
        messages = self._append_messages(
            state,
            messages,
            [
                {
                    "country_id": member,
                    "category": "war",
                    "subject": f"War: {attacker} vs {defender}",
                    "body": f"Casus belli: {casus_belli or 'Unspecified'}.",
                }
                for member in sorted(side_a | side_b)
            ],
        )
        news = self._append_news(
            state, news, f"War breaks out: {attacker} vs {defender}",
            "Alliance obligations and hostile relations have been updated.", "war", attacker, "warning",
        )
        return wars, relations, messages, news

    def _offer_peace(
        self,
        state: GameState,
        action: ActionOfferPeace,
        wars: pl.DataFrame,
        relations: pl.DataFrame,
        messages: pl.DataFrame,
        news: pl.DataFrame,
    ) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
        matches = wars.filter(pl.col("id") == str(action.war_id))
        if matches.is_empty():
            return wars, relations, messages, news
        row = matches.to_dicts()[0]
        source = self._tag(action.source_country_tag)
        leader_a, leader_b = self._tag(row.get("leader_a")), self._tag(row.get("leader_b"))
        if source not in {leader_a, leader_b}:
            return wars, relations, messages, news
        intent_key = "intent_a" if source == leader_a else "intent_b"
        updated = {**row, intent_key: "war" if str(action.terms).strip().lower() == "war" else "peace"}
        if updated.get("intent_a") != "peace" or updated.get("intent_b") != "peace":
            wars = self._replace_row(wars, WAR_SCHEMA, str(action.war_id), updated)
            opposing = leader_b if source == leader_a else leader_a
            messages = self._append_message(
                state, messages, opposing, "war", f"Peace proposal from {source}",
                "Accept peace from the War List to end this conflict.",
            )
            return wars, relations, messages, news
        wars = wars.filter(pl.col("id") != str(action.war_id))
        relation_deltas = {
            pair: 15.0
            for left in self._tags(row.get("side_a"))
            for right in self._tags(row.get("side_b"))
            if left != right
            for pair in ((left, right), (right, left))
        }
        relations = self._apply_relation_deltas(relations, relation_deltas)
        news = self._append_news(
            state, news, f"Peace agreed: {leader_a} vs {leader_b}",
            "Both war leaders accepted peace and the conflict was closed.", "war", source,
        )
        return wars, relations, messages, news

    def _apply_punctual_effect(
        self,
        state: GameState,
        treaty: Mapping[str, Any],
        treaties: pl.DataFrame,
        wars: pl.DataFrame,
        relations: pl.DataFrame,
        messages: pl.DataFrame,
        news: pl.DataFrame,
        claims: pl.DataFrame,
    ) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
        definition = treaty_definition(treaty.get("type"))
        if definition is None or definition.long_term:
            return treaties, wars, relations, messages, news, claims
        side_a, side_b = treaty_side(treaty, "a"), treaty_side(treaty, "b")
        if definition.key == "request_war_declaration":
            wars, relations, messages, news = self._start_war(
                state,
                source=side_a[0],
                target=side_b[0],
                casus_belli=str(treaty.get("terms") or "Formal treaty declaration"),
                treaties=treaties,
                wars=wars,
                relations=relations,
                messages=messages,
                news=news,
            )
        elif definition.key == "request_military_presence_removal":
            self._remove_foreign_units(state, set(side_a), set(side_b))
        elif definition.key == "free_region":
            self._release_regions(state, set(side_a), set(side_b))
        elif definition.key == "annexation":
            claims = self._schedule_annexation(state, claims, str(treaty.get("id")), set(side_a), set(side_b))
        elif definition.key == "assume_foreign_debt":
            self._assume_foreign_debt(state, set(side_a), set(side_b))
        return treaties, wars, relations, messages, news, claims

    def _apply_long_term_effects(
        self,
        state: GameState,
        treaties: pl.DataFrame,
        relations: pl.DataFrame,
    ) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
        effects: list[dict[str, Any]] = []
        maintenance_by_country: dict[str, float] = {}
        is_new_day = any(isinstance(event, EventNewDay) for event in state.events)
        is_new_month = any(
            isinstance(event, EventNewDay) and event.day == 1 for event in state.events
        )
        countries = self._country_rows(state)
        country_by_id = {self._tag(row.get("id")): row for row in countries}
        all_country_tags = tuple(sorted(country_by_id))

        updated_rows: list[dict[str, Any]] = []
        daily_relation_deltas: dict[tuple[str, str], float] = {}
        for treaty in treaties.to_dicts():
            definition = treaty_definition(treaty.get("type"))
            members = tuple(
                tag for tag in treaty_members(treaty)
                if tag not in set(self._tags(treaty.get("suspended_members")))
            )
            if definition is None or not definition.long_term or treaty.get("status") != "active" or len(members) < 2:
                updated_rows.append(treaty)
                continue
            annual_cost, cost_shares = self._maintenance_cost(members, country_by_id)
            treaty["maintenance_cost"] = annual_cost
            for country_id, amount in cost_shares.items():
                maintenance_by_country[country_id] = maintenance_by_country.get(country_id, 0.0) + amount
            effects.extend(self._effect_rows(treaty, members, country_by_id))
            if is_new_day:
                for pair, delta in self._daily_relation_deltas(
                    definition.key,
                    members,
                    all_country_tags,
                    country_by_id,
                ).items():
                    daily_relation_deltas[pair] = daily_relation_deltas.get(pair, 0.0) + delta
            if is_new_month and definition.key == "human_development_collaboration":
                countries = self._apply_human_development_convergence(countries, members)
                country_by_id = {self._tag(row.get("id")): row for row in countries}
            updated_rows.append(treaty)

        relations = self._apply_relation_deltas(relations, daily_relation_deltas)
        treaties = self._frame(TREATY_SCHEMA, updated_rows)
        if countries and (effects or maintenance_by_country):
            countries = self._set_treaty_maintenance(countries, maintenance_by_country)
            state.update_table("countries", self._frame_like(state.get_table("countries"), countries))
        return treaties, relations, self._frame(TREATY_EFFECT_SCHEMA, effects)

    def _effect_rows(
        self,
        treaty: Mapping[str, Any],
        members: tuple[str, ...],
        country_by_id: Mapping[str, Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        definition = treaty_definition(treaty.get("type"))
        if definition is None:
            return []
        treaty_id = str(treaty.get("id") or "")
        rows: list[dict[str, Any]] = []
        member_payload = json.dumps(members)
        for effect in definition.effects:
            if effect == "research_capacity_bonus":
                capacity = sum(self._research_capacity(country_by_id.get(tag, {})) for tag in members)
                for tag in members:
                    rows.append(self._effect(treaty_id, tag, effect, capacity * 0.10, member_payload))
            elif effect == "resource_production_bonus":
                output = {tag: max(0.0, self._number(country_by_id.get(tag, {}).get("gdp"))) for tag in members}
                total = sum(output.values()) or float(len(members))
                for tag in members:
                    bonus = 0.01 + 0.04 * (output[tag] / total)
                    rows.append(self._effect(treaty_id, tag, effect, bonus, member_payload))
            elif effect in {"common_market_priority", "weapons_market_access", "stationing_rights", "transit_rights"}:
                for tag in members:
                    peers = tuple(member for member in members if member != tag)
                    rows.append(self._effect(treaty_id, tag, effect, 1.0, json.dumps(peers)))
            elif effect == "economic_aid":
                for tag in treaty_side(treaty, "a"):
                    rows.append(self._effect(treaty_id, tag, "economic_aid_contributor", 0.01, json.dumps(treaty_side(treaty, "b"))))
                for tag in treaty_side(treaty, "b"):
                    rows.append(self._effect(treaty_id, tag, "economic_aid_recipient", 0.10, json.dumps(treaty_side(treaty, "a"))))
            elif effect in {"resource_trade_embargo", "weapons_trade_embargo"}:
                for tag in treaty_side(treaty, "a"):
                    rows.append(self._effect(treaty_id, tag, effect, 1.0, json.dumps(treaty_side(treaty, "b"))))
                for tag in treaty_side(treaty, "b"):
                    rows.append(self._effect(treaty_id, tag, effect, 1.0, json.dumps(treaty_side(treaty, "a"))))
        return rows

    def _refresh_suspended_members(
        self,
        state: GameState,
        treaties: pl.DataFrame,
        wars: pl.DataFrame,
    ) -> pl.DataFrame:
        rows: list[dict[str, Any]] = []
        treaty_rows = treaties.to_dicts()
        relation_pairs: set[tuple[str, str]] = set()
        for treaty in treaty_rows:
            conditions = decode_conditions(treaty.get("conditions_json"))
            if self._number(conditions.get("minimum_relation"), -100.0) <= -100.0:
                continue
            members = treaty_members(treaty)
            relation_pairs.update(
                (member, peer)
                for member in members
                for peer in members
                if member != peer
            )
        eligibility = self._eligibility_index(state, wars, relation_pairs)
        war_pairs = eligibility.war_pairs
        for row in treaty_rows:
            definition = treaty_definition(row.get("type"))
            members = treaty_members(row)
            if definition is None or not definition.long_term or not members:
                rows.append(row)
                continue
            conditions = decode_conditions(row.get("conditions_json"))
            if self._has_profile_conditions(conditions):
                suspended = [
                    member for member in members
                    if not self._eligible_for_treaty(
                        state,
                        row,
                        member,
                        tuple(tag for tag in members if tag != member),
                        wars,
                        eligibility,
                    )
                ]
            elif bool(conditions.get("allow_members_at_war")):
                suspended = []
            else:
                suspended = [member for member in members if any(frozenset((member, peer)) in war_pairs for peer in members if peer != member)]
            row["suspended_members"] = sorted(suspended)
            rows.append(row)
        return self._frame(TREATY_SCHEMA, rows)

    def _has_profile_conditions(self, conditions: Mapping[str, Any]) -> bool:
        return any((
            self._number(conditions.get("minimum_relation"), -100.0) > -100.0,
            self._number(conditions.get("max_military_strength_ratio")) > 0.0,
            self._number(conditions.get("max_economic_strength_ratio")) > 0.0,
            self._number(conditions.get("max_research_ratio")) > 0.0,
            str(conditions.get("government_type") or "").strip(),
            self._number(conditions.get("maximum_geographic_distance_km")) > 0.0,
        ))

    def _war_pair_index(self, wars: pl.DataFrame) -> set[frozenset[str]]:
        pairs: set[frozenset[str]] = set()
        for war in wars.to_dicts():
            if str(war.get("status") or "active").lower() != "active":
                continue
            side_a, side_b = self._tags(war.get("side_a")), self._tags(war.get("side_b"))
            pairs.update(frozenset((left, right)) for left in side_a for right in side_b if left != right)
        return pairs

    def _eligibility_index(
        self,
        state: GameState,
        wars: pl.DataFrame,
        relation_pairs: Iterable[tuple[str, str]] = (),
    ) -> _TreatyEligibilityIndex:
        countries = {
            self._tag(row.get("id")): row
            for row in self._country_rows(state)
            if self._tag(row.get("id"))
        }
        relations_table = state.tables.get("countries_relations")
        requested_pairs = sorted(set(relation_pairs))
        if relations_table is None or not requested_pairs:
            relations: dict[tuple[str, str], float] = {}
        else:
            requested = pl.DataFrame(
                requested_pairs,
                schema={"source": pl.Utf8, "target": pl.Utf8},
                orient="row",
            )
            selected = requested.join(
                relations_table.select("source", "target", "value"),
                on=["source", "target"],
                how="left",
            ).with_columns(pl.col("value").fill_null(0.0))
            relations = {
                (str(source), str(target)): self._number(value)
                for source, target, value in selected.iter_rows()
            }
        government_table = state.tables.get("country_governments")
        governments = {
            self._tag(row.get("country_id")): str(row.get("government_type") or "")
            for row in (() if government_table is None else government_table.to_dicts())
        }
        return _TreatyEligibilityIndex(
            countries=countries,
            relations=relations,
            governments=governments,
            war_pairs=self._war_pair_index(wars),
        )

    def _eligible_for_treaty(
        self,
        state: GameState,
        treaty: Mapping[str, Any],
        candidate: str,
        peers: Iterable[str],
        wars: pl.DataFrame | None = None,
        index: _TreatyEligibilityIndex | None = None,
    ) -> bool:
        conditions = decode_conditions(treaty.get("conditions_json"))
        candidate_tag = self._tag(candidate)
        candidate_row = (
            index.countries.get(candidate_tag, {})
            if index is not None
            else self._country_row(state, candidate_tag)
        )
        if not candidate_row:
            return False
        government_type = str(conditions.get("government_type") or "").strip().lower()
        candidate_government = (
            index.governments.get(candidate_tag, "")
            if index is not None
            else self._government_type(state, candidate_tag)
        )
        if government_type and candidate_government.lower() != government_type:
            return False

        minimum_relation = self._number(conditions.get("minimum_relation"), -100.0)
        maximum_distance = self._number(conditions.get("maximum_geographic_distance_km"))
        for peer in peers:
            peer_tag = self._tag(peer)
            peer_row = (
                index.countries.get(peer_tag, {})
                if index is not None
                else self._country_row(state, peer_tag)
            )
            if not peer_row:
                return False
            relation = (
                index.relations.get((candidate_tag, peer_tag), 0.0)
                if index is not None
                else self._relation_value(state.tables.get("countries_relations"), candidate_tag, peer_tag)
            )
            if minimum_relation > -100.0 and relation < minimum_relation:
                return False
            if maximum_distance > 0.0 and not TreatyGeography.within_limit(state, candidate_tag, peer_tag, maximum_distance):
                return False
            if not self._similar(self._number(candidate_row.get("military_count")), self._number(peer_row.get("military_count")), conditions.get("max_military_strength_ratio")):
                return False
            if not self._similar(self._number(candidate_row.get("gdp")), self._number(peer_row.get("gdp")), conditions.get("max_economic_strength_ratio")):
                return False
            if not self._similar(self._research_capacity(candidate_row), self._research_capacity(peer_row), conditions.get("max_research_ratio")):
                return False
            if not bool(conditions.get("allow_members_at_war")):
                at_war = (
                    frozenset((candidate_tag, peer_tag)) in index.war_pairs
                    if index is not None
                    else self._countries_at_war(
                        wars if wars is not None else self._wars(state.tables.get("countries_wars")),
                        candidate_tag,
                        peer_tag,
                    )
                )
                if at_war:
                    return False
        return True

    def _resolve_annexation_claims(
        self,
        state: GameState,
        claims: pl.DataFrame,
    ) -> tuple[pl.DataFrame, pl.DataFrame | None]:
        if claims.is_empty() or "regions" not in state.tables:
            return claims, None
        regions = state.get_table("regions")
        region_rows = regions.to_dicts()
        by_id = {int(row.get("id") or 0): row for row in region_rows}
        rows: list[dict[str, Any]] = []
        changed = False
        invalidated_regions = AnnexationPolicy().invalidated_claim_regions(state, claims)
        for claim in claims.to_dicts():
            if claim.get("status") != "pending":
                rows.append(claim)
                continue
            if int(claim.get("region_id") or 0) in invalidated_regions:
                claim["status"] = "void"
                rows.append(claim)
                continue
            if int(claim.get("due_at_minute") or 0) > int(state.time.total_minutes):
                rows.append(claim)
                continue
            region = by_id.get(int(claim.get("region_id") or 0))
            if region and self._tag(region.get("owner")) == self._tag(claim.get("political_owner_id")) and self._tag(region.get("controller")) == self._tag(claim.get("annexing_country_id")):
                region["owner"] = self._tag(claim.get("annexing_country_id"))
                claim["status"] = "annexed"
                changed = True
            else:
                claim["status"] = "void"
            rows.append(claim)
        result = self._frame(ANNEXATION_CLAIM_SCHEMA, rows)
        return result, self._frame_like(regions, region_rows) if changed else None

    def _schedule_annexation(
        self,
        state: GameState,
        claims: pl.DataFrame,
        treaty_id: str,
        side_a: set[str],
        side_b: set[str],
    ) -> pl.DataFrame:
        if "regions" not in state.tables:
            return claims
        due_at = self._after_calendar_months(state, 6)
        rows = claims.to_dicts()
        known = {str(row.get("id")) for row in rows}
        for region in state.get_table("regions").to_dicts():
            owner, controller = self._tag(region.get("owner")), self._tag(region.get("controller"))
            if owner not in side_b or controller not in side_a:
                continue
            claim_id = f"claim-{treaty_id}-{int(region.get('id') or 0)}"
            if claim_id in known:
                continue
            rows.append({
                "id": claim_id,
                "treaty_id": treaty_id,
                "region_id": int(region.get("id") or 0),
                "annexing_country_id": controller,
                "political_owner_id": owner,
                "controller_at_start": controller,
                "due_at_minute": due_at,
                "status": "pending",
            })
        return self._frame(ANNEXATION_CLAIM_SCHEMA, rows)

    def _remove_foreign_units(self, state: GameState, requesters: set[str], removed_side: set[str]) -> None:
        if not {"units", "regions"}.issubset(state.tables):
            return
        units, regions = state.get_table("units"), state.get_table("regions")
        region_by_id = {int(row.get("id") or 0): row for row in regions.to_dicts()}
        home_regions = {
            tag: [row for row in region_by_id.values() if self._tag(row.get("owner")) == tag and self._tag(row.get("controller")) == tag]
            for tag in removed_side
        }
        rows = units.to_dicts()
        for unit in rows:
            owner = self._tag(unit.get("owner"))
            current = region_by_id.get(int(unit.get("current_region_id") or 0), {})
            if owner not in removed_side or self._tag(current.get("owner")) not in requesters:
                continue
            destinations = home_regions.get(owner, [])
            if not destinations:
                continue
            target = min(destinations, key=lambda region: self._region_distance(unit, region))
            self._relocate_unit(unit, target, int(state.time.total_minutes))
        state.update_table("units", self._frame_like(units, rows))

    def _release_regions(self, state: GameState, releasers: set[str], owners: set[str]) -> None:
        if "regions" not in state.tables:
            return
        regions = state.get_table("regions")
        rows = regions.to_dicts()
        for region in rows:
            if self._tag(region.get("controller")) in releasers and self._tag(region.get("owner")) in owners:
                region["controller"] = self._tag(region.get("owner"))
        state.update_table("regions", self._frame_like(regions, rows))

    def _assume_foreign_debt(self, state: GameState, contributors: set[str], recipients: set[str]) -> None:
        if "countries" not in state.tables:
            return
        countries = self._country_rows(state)
        by_id = {self._tag(row.get("id")): row for row in countries}
        weights = {tag: max(0.0, self._number(by_id.get(tag, {}).get("gdp"))) for tag in contributors}
        total_weight = sum(weights.values()) or float(len(contributors) or 1)
        for recipient in recipients:
            receiver = by_id.get(recipient)
            if receiver is None:
                continue
            debt = max(0.0, -self._number(receiver.get("money_reserves")))
            if debt <= 0:
                continue
            receiver["money_reserves"] = self._number(receiver.get("money_reserves")) + debt
            for contributor, weight in weights.items():
                donor = by_id.get(contributor)
                if donor is not None:
                    donor["money_reserves"] = self._number(donor.get("money_reserves")) - debt * (weight / total_weight)
        state.update_table("countries", self._frame_like(state.get_table("countries"), countries))

    def _expand_allies(self, treaties: pl.DataFrame, country: str) -> set[str]:
        expanded = {country}
        changed = True
        while changed:
            changed = False
            for row in active_treaty_rows(treaties):
                if normalize_treaty_type(row.get("type")) != "alliance":
                    continue
                members = set(treaty_members(row)) - set(self._tags(row.get("suspended_members")))
                if expanded & members and not members <= expanded:
                    expanded |= members
                    changed = True
        return expanded

    def _maintenance_cost(
        self, members: Iterable[str], country_by_id: Mapping[str, Mapping[str, Any]]
    ) -> tuple[float, dict[str, float]]:
        member_list = tuple(members)
        strength = {
            tag: max(1.0, self._number(country_by_id.get(tag, {}).get("gdp"), 1.0))
            for tag in member_list
        }
        total_strength = sum(strength.values())
        cost = total_strength * 0.00025 * max(1, len(member_list) - 1)
        return cost, {tag: cost * value / total_strength for tag, value in strength.items()}

    def _apply_daily_relations(
        self,
        relations: pl.DataFrame,
        treaty_type: str,
        members: Iterable[str],
        all_countries: Iterable[str],
        country_by_id: Mapping[str, Mapping[str, Any]],
    ) -> pl.DataFrame:
        return self._apply_relation_deltas(
            relations,
            self._daily_relation_deltas(
                treaty_type,
                members,
                all_countries,
                country_by_id,
            ),
        )

    def _daily_relation_deltas(
        self,
        treaty_type: str,
        members: Iterable[str],
        all_countries: Iterable[str],
        country_by_id: Mapping[str, Mapping[str, Any]],
    ) -> dict[tuple[str, str], float]:
        members = tuple(members)
        deltas: dict[tuple[str, str], float] = {}
        if treaty_type in {"cultural_exchanges", "noble_cause"}:
            member_delta = 0.05 if treaty_type == "cultural_exchanges" else 0.03
            for index, left in enumerate(members):
                for right in members[index + 1:]:
                    deltas[(left, right)] = deltas.get((left, right), 0.0) + member_delta
                    deltas[(right, left)] = deltas.get((right, left), 0.0) + member_delta
        if treaty_type == "noble_cause":
            total_gdp = sum(max(1.0, self._number(row.get("gdp"), 1.0)) for row in country_by_id.values())
            for member in members:
                for outsider in all_countries:
                    if outsider not in members:
                        pressure = -0.02 * max(1.0, self._number(country_by_id[outsider].get("gdp"), 1.0)) / total_gdp
                        deltas[(member, outsider)] = deltas.get((member, outsider), 0.0) + pressure
                        deltas[(outsider, member)] = deltas.get((outsider, member), 0.0) + pressure
        return deltas

    def _apply_human_development_convergence(
        self, countries: list[dict[str, Any]], members: Iterable[str]
    ) -> list[dict[str, Any]]:
        member_set = set(members)
        values = [self._number(row.get("human_dev"), 0.0) for row in countries if self._tag(row.get("id")) in member_set]
        if not values:
            return countries
        target = max(values)
        for row in countries:
            if self._tag(row.get("id")) in member_set:
                current = self._number(row.get("human_dev"), 0.0)
                row["human_dev"] = min(1.0, current + (target - current) * 0.08)
        return countries

    def _set_treaty_maintenance(
        self, countries: list[dict[str, Any]], maintenance_by_country: Mapping[str, float]
    ) -> list[dict[str, Any]]:
        for row in countries:
            row["treaty_maintenance"] = float(maintenance_by_country.get(self._tag(row.get("id")), 0.0))
        return countries

    def _apply_activation_relations(self, relations: pl.DataFrame, treaty_type: str, members: Iterable[str]) -> pl.DataFrame:
        delta = self._relation_delta(treaty_type)
        if not delta:
            return relations
        member_list = tuple(members)
        deltas = {
            pair: delta
            for index, left in enumerate(member_list)
            for right in member_list[index + 1:]
            for pair in ((left, right), (right, left))
        }
        return self._apply_relation_deltas(relations, deltas)

    def _relation_delta(self, treaty_type: Any) -> float:
        return LONG_TERM_RELATION_DELTAS.get(normalize_treaty_type(treaty_type), 0.0)

    def _active_war(self, wars: pl.DataFrame, left: str, right: str) -> bool:
        return self._countries_at_war(wars, left, right)

    def _countries_at_war(self, wars: pl.DataFrame, left: str, right: str) -> bool:
        for war in wars.to_dicts():
            if str(war.get("status") or "active").lower() != "active":
                continue
            side_a, side_b = set(self._tags(war.get("side_a"))), set(self._tags(war.get("side_b")))
            if (left in side_a and right in side_b) or (left in side_b and right in side_a):
                return True
        return False

    def _has_matching_treaty(self, treaties: pl.DataFrame, pending: pl.DataFrame, treaty_type: str, members: Iterable[str]) -> bool:
        desired = set(members)
        for table, type_column in ((treaties, "type"), (pending, "treaty_type")):
            for row in table.to_dicts():
                if normalize_treaty_type(row.get(type_column)) == treaty_type and set(self._tags(row.get("members"))) == desired:
                    return True
        return False

    def _all_known_countries(self, state: GameState, country_tags: Iterable[str]) -> bool:
        return all(self._country_exists(state, country_tag) for country_tag in country_tags)

    def _country_exists(self, state: GameState, country_tag: str) -> bool:
        return bool(self._country_row(state, country_tag))

    def _country_row(self, state: GameState, country_tag: str) -> dict[str, Any]:
        for row in self._country_rows(state):
            if self._tag(row.get("id")) == self._tag(country_tag):
                return row
        return {}

    def _country_rows(self, state: GameState) -> list[dict[str, Any]]:
        countries = state.tables.get("countries")
        return [] if countries is None or countries.is_empty() else countries.to_dicts()

    def _government_type(self, state: GameState, country_tag: str) -> str:
        governments = state.tables.get("country_governments")
        if governments is None or governments.is_empty():
            return ""
        for row in governments.to_dicts():
            if self._tag(row.get("country_id")) == self._tag(country_tag):
                return str(row.get("government_type") or "")
        return ""

    def _research_capacity(self, country: Mapping[str, Any]) -> float:
        return max(0.0, self._number(country.get("gdp"))) * max(0.0, self._number(country.get("budget_research_ratio")))

    def _similar(self, left: float, right: float, maximum_ratio: Any) -> bool:
        maximum = self._number(maximum_ratio)
        if maximum <= 0:
            return True
        low, high = sorted((max(left, 1.0), max(right, 1.0)))
        return high / low <= maximum

    def _after_calendar_months(self, state: GameState, months: int) -> int:
        current = GAME_EPOCH + timedelta(minutes=int(state.time.total_minutes))
        month_index = current.month - 1 + months
        year, month = current.year + month_index // 12, month_index % 12 + 1
        day = min(current.day, calendar.monthrange(year, month)[1])
        target = datetime(year, month, day, current.hour, current.minute)
        return int((target - GAME_EPOCH).total_seconds() // 60)

    def _region_distance(self, unit: Mapping[str, Any], region: Mapping[str, Any]) -> float:
        return math.hypot(
            self._number(unit.get("latitude")) - self._number(region.get("latitude")),
            self._number(unit.get("longitude")) - self._number(region.get("longitude")),
        )

    def _relocate_unit(self, unit: dict[str, Any], target: Mapping[str, Any], now: int) -> None:
        unit["current_region_id"] = int(target.get("id") or 0)
        for column in ("latitude", "longitude"):
            unit[column] = self._number(target.get(column))
        unit["source_region_id"] = unit["current_region_id"]
        unit["source_latitude"] = unit["latitude"]
        unit["source_longitude"] = unit["longitude"]
        unit["target_region_id"] = -1
        unit["target_latitude"] = unit["latitude"]
        unit["target_longitude"] = unit["longitude"]
        unit["departed_at_minute"] = now
        unit["arrival_at_minute"] = now
        unit["movement_progress"] = 0.0
        unit["is_moving"] = False

    def _relations(self, frame: pl.DataFrame | None) -> pl.DataFrame:
        if frame is None or frame.is_empty():
            return pl.DataFrame(schema=RELATIONS_SCHEMA)
        normalized = frame.select(
            pl.col("source").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase(),
            pl.col("target").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase(),
            pl.col("value").cast(pl.Float64, strict=False).fill_null(0.0),
        )
        return normalized.filter(
            (pl.col("source") != "")
            & (pl.col("target") != "")
        )

    def _wars(self, frame: pl.DataFrame | None) -> pl.DataFrame:
        rows = [] if frame is None else frame.to_dicts()
        return self._frame(WAR_SCHEMA, [{
            "id": str(row.get("id") or ""), "name": str(row.get("name") or ""),
            "side_a": list(self._tags(row.get("side_a"))), "side_b": list(self._tags(row.get("side_b"))),
            "status": str(row.get("status") or "active"), "casus_belli": str(row.get("casus_belli") or ""),
            "created_at": str(row.get("created_at") or ""),
            "leader_a": self._tag(row.get("leader_a")) or (self._tags(row.get("side_a")) or ("",))[0],
            "leader_b": self._tag(row.get("leader_b")) or (self._tags(row.get("side_b")) or ("",))[0],
            "intent_a": str(row.get("intent_a") or "war"), "intent_b": str(row.get("intent_b") or "war"),
        } for row in rows])

    def _treaties(self, frame: pl.DataFrame | None) -> pl.DataFrame:
        rows = [] if frame is None else frame.to_dicts()
        normalized = []
        for row in rows:
            side_a, side_b = self._tags(row.get("side_a")), self._tags(row.get("side_b"))
            members = self._tags(row.get("members")) or tuple(sorted(set(side_a) | set(side_b)))
            source, target = self._tag(row.get("source_country_id")), self._tag(row.get("target_country_id"))
            if not side_a and source:
                side_a = (source,)
            if not side_b and target and target not in side_a:
                side_b = (target,)
            normalized.append({
                "id": str(row.get("id") or ""), "name": str(row.get("name") or row.get("id") or "Treaty"),
                "type": normalize_treaty_type(row.get("type")), "members": list(members),
                "side_a": list(side_a), "side_b": list(side_b), "status": str(row.get("status") or "active"),
                "terms": str(row.get("terms") or ""), "conditions_json": str(row.get("conditions_json") or encode_conditions(None)),
                "open_to_new_members": bool(row.get("open_to_new_members", False)),
                "suspended_members": list(self._tags(row.get("suspended_members"))),
                "created_at": str(row.get("created_at") or ""), "activated_at_minute": int(row.get("activated_at_minute") or 0),
                "expires_at_minute": int(row.get("expires_at_minute") or 0), "maintenance_cost": self._number(row.get("maintenance_cost")),
                "source_country_id": source, "target_country_id": target,
            })
        return self._frame(TREATY_SCHEMA, normalized)

    def _pending(self, frame: pl.DataFrame | None) -> pl.DataFrame:
        rows = [] if frame is None else frame.to_dicts()
        normalized = []
        for row in rows:
            source, target = self._tag(row.get("source_country_id")), self._tag(row.get("target_country_id"))
            side_a, side_b = self._tags(row.get("side_a")) or ((source,) if source else ()), self._tags(row.get("side_b")) or ((target,) if target else ())
            members = self._tags(row.get("members")) or tuple(sorted(set(side_a) | set(side_b)))
            normalized.append({
                "id": str(row.get("id") or ""), "source_country_id": source, "target_country_id": target,
                "treaty_type": normalize_treaty_type(row.get("treaty_type")), "title": str(row.get("title") or "Treaty"),
                "terms": str(row.get("terms") or ""), "side_a": list(side_a), "side_b": list(side_b), "members": list(members),
                "required_responses": list(self._tags(row.get("required_responses")) or tuple(tag for tag in members if tag != source)),
                "accepted_members": list(self._tags(row.get("accepted_members")) or ((source,) if source else ())),
                "conditions_json": str(row.get("conditions_json") or encode_conditions(None)),
                "open_to_new_members": bool(row.get("open_to_new_members", False)), "status": str(row.get("status") or "pending"),
                "created_at": str(row.get("created_at") or ""),
            })
        return self._frame(PENDING_TREATY_SCHEMA, normalized)

    def _claims(self, frame: pl.DataFrame | None) -> pl.DataFrame:
        rows = [] if frame is None else frame.to_dicts()
        return self._frame(ANNEXATION_CLAIM_SCHEMA, [{
            "id": str(row.get("id") or ""), "treaty_id": str(row.get("treaty_id") or ""),
            "region_id": int(row.get("region_id") or 0), "annexing_country_id": self._tag(row.get("annexing_country_id")),
            "political_owner_id": self._tag(row.get("political_owner_id")), "controller_at_start": self._tag(row.get("controller_at_start")),
            "due_at_minute": int(row.get("due_at_minute") or 0), "status": str(row.get("status") or "pending"),
        } for row in rows])

    def _messages(self, frame: pl.DataFrame | None) -> pl.DataFrame:
        return self._owned_frame(frame, MESSAGE_SCHEMA)

    def _news(self, frame: pl.DataFrame | None) -> pl.DataFrame:
        return self._owned_frame(frame, NEWS_SCHEMA)

    def _owned_frame(
        self,
        frame: pl.DataFrame | None,
        schema: Mapping[str, pl.DataType],
    ) -> pl.DataFrame:
        if frame is None or frame.is_empty():
            return pl.DataFrame(schema=dict(schema))
        if frame.schema == dict(schema):
            return frame
        return self._frame(schema, frame.to_dicts())

    def _append_messages(
        self,
        state: GameState,
        messages: pl.DataFrame,
        payloads: Iterable[Mapping[str, Any]],
    ) -> pl.DataFrame:
        existing_ids = set(messages["id"].to_list())
        rows: list[dict[str, Any]] = []
        for payload in payloads:
            message_id = self._next_identifier("message", existing_ids, state)
            existing_ids.add(message_id)
            country_id = self._tag(payload.get("country_id"))
            category = str(payload.get("category") or "")
            state.events.append(EventMessageCreated(message_id, country_id, category))
            rows.append({
                "id": message_id,
                "country_id": country_id,
                "category": category,
                "subject": str(payload.get("subject") or ""),
                "body": str(payload.get("body") or ""),
                "is_read": False,
                "created_at": self._timestamp(state),
            })
        if not rows:
            return messages
        return messages.vstack(self._frame(MESSAGE_SCHEMA, rows))

    def _append_message(self, state: GameState, messages: pl.DataFrame, country_id: str, category: str, subject: str, body: str) -> pl.DataFrame:
        message_id = self._next_identifier("message", messages["id"].to_list(), state)
        state.events.append(EventMessageCreated(message_id, country_id, category))
        return self._append(messages, MESSAGE_SCHEMA, {
            "id": message_id, "country_id": country_id, "category": category, "subject": subject,
            "body": body, "is_read": False, "created_at": self._timestamp(state),
        })

    def _append_news(self, state: GameState, news: pl.DataFrame, headline: str, body: str, category: str, related_country_id: str, severity: str = "info") -> pl.DataFrame:
        return self._append(news, NEWS_SCHEMA, {
            "id": self._next_identifier("news", news["id"].to_list(), state), "headline": headline,
            "body": body, "category": category, "severity": severity, "related_country_id": related_country_id,
            "created_at": self._timestamp(state),
        })


    def _apply_relation_deltas(self, relations: pl.DataFrame, deltas: Mapping[tuple[str, str], float]) -> pl.DataFrame:
        if not deltas:
            return relations
        updates = pl.DataFrame(
            [
                {"source": source, "target": target, "_delta": float(delta)}
                for (source, target), delta in sorted(deltas.items())
            ],
            schema={"source": pl.Utf8, "target": pl.Utf8, "_delta": pl.Float64},
        )
        return (
            relations.join(
                updates,
                on=["source", "target"],
                how="full",
                coalesce=True,
            )
            .with_columns(
                (
                    pl.col("value").fill_null(0.0)
                    + pl.col("_delta").fill_null(0.0)
                ).clip(-100.0, 100.0).alias("value")
            )
            .select("source", "target", "value")
            .sort(["source", "target"])
        )

    def _set_relation_pairs(
        self,
        relations: pl.DataFrame,
        pairs: Iterable[tuple[str, str]],
        value: float,
    ) -> pl.DataFrame:
        normalized_value = float(max(-100.0, min(100.0, value)))
        replacements = {
            (self._tag(left), self._tag(right)): normalized_value
            for left, right in pairs
            if self._tag(left) and self._tag(right) and self._tag(left) != self._tag(right)
        }
        replacements.update({
            (right, left): pair_value
            for (left, right), pair_value in tuple(replacements.items())
        })
        if not replacements:
            return relations
        updates = pl.DataFrame(
            [
                {"source": source, "target": target, "_value": pair_value}
                for (source, target), pair_value in sorted(replacements.items())
            ],
            schema={"source": pl.Utf8, "target": pl.Utf8, "_value": pl.Float64},
        )
        return (
            relations.join(
                updates,
                on=["source", "target"],
                how="full",
                coalesce=True,
            )
            .with_columns(
                pl.coalesce("_value", "value").alias("value")
            )
            .select("source", "target", "value")
            .sort(["source", "target"])
        )

    def _adjust_relation_pair(self, relations: pl.DataFrame, left: str, right: str, delta: float) -> pl.DataFrame:
        return self._set_relation_pair(
            relations, left, right,
            self._relation_value(relations, left, right) + delta,
            self._relation_value(relations, right, left) + delta,
        )

    def _set_relation_pair(self, relations: pl.DataFrame, left: str, right: str, left_value: float, right_value: float | None = None) -> pl.DataFrame:
        right_value = left_value if right_value is None else right_value
        rows = [row for row in relations.to_dicts() if (self._tag(row.get("source")), self._tag(row.get("target"))) not in {(left, right), (right, left)}]
        rows.extend(({"source": left, "target": right, "value": float(max(-100.0, min(100.0, left_value)))}, {"source": right, "target": left, "value": float(max(-100.0, min(100.0, right_value)))}))
        return self._frame(RELATIONS_SCHEMA, rows)

    def _relation_value(self, relations: pl.DataFrame | None, source: str, target: str) -> float:
        if relations is None or relations.is_empty():
            return 0.0
        source_tag, target_tag = self._tag(source), self._tag(target)
        matches = relations.filter(
            (pl.col("source") == source_tag)
            & (pl.col("target") == target_tag)
        ).select("value").head(1)
        return 0.0 if matches.is_empty() else self._number(matches.item())

    def _replace_row(self, frame: pl.DataFrame, schema: Mapping[str, pl.DataType], identifier: str, updated: Mapping[str, Any]) -> pl.DataFrame:
        remaining = frame.filter(pl.col("id").cast(pl.Utf8) != str(identifier))
        return remaining.vstack(self._frame(schema, [dict(updated)]))

    def _append(self, frame: pl.DataFrame, schema: Mapping[str, pl.DataType], row: Mapping[str, Any]) -> pl.DataFrame:
        return frame.vstack(self._frame(schema, [dict(row)]))

    def _frame(self, schema: Mapping[str, pl.DataType], rows: list[Mapping[str, Any]]) -> pl.DataFrame:
        if not rows:
            return pl.DataFrame(schema=dict(schema))
        prepared = [{column: row.get(column) for column in schema} for row in rows]
        return pl.DataFrame(prepared, schema=dict(schema), strict=False)

    def _frame_like(self, original: pl.DataFrame, rows: list[Mapping[str, Any]]) -> pl.DataFrame:
        if not rows:
            return pl.DataFrame(schema=original.schema)
        # Sparse region columns must not let row order redefine the runtime schema.
        return pl.DataFrame(rows, schema=original.schema, strict=False)

    def _next_identifier(self, prefix: str, existing: Iterable[Any], state: GameState) -> str:
        known = {str(value) for value in existing}
        index = 1
        while f"{prefix}-{index:04d}" in known:
            index += 1
        return f"{prefix}-{index:04d}"

    def _timestamp(self, state: GameState) -> str:
        return str(getattr(state.time, "date_str", "") or "")

    def _effect(self, treaty_id: str, country_id: str, effect: str, value: float, detail: str) -> dict[str, Any]:
        return {"treaty_id": treaty_id, "country_id": country_id, "effect": effect, "value": float(value), "detail": detail}

    def _tag(self, value: Any) -> str:
        return str(value or "").strip().upper()

    def _tags(self, values: Any) -> tuple[str, ...]:
        return normalize_country_tags(values)

    def _number(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)
