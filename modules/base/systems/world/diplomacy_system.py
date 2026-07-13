from __future__ import annotations

import re
from typing import Any, Iterable, Sequence

import polars as pl

from src.engine.interfaces import ISystem
from src.shared.actions import (
    ActionCreateTreaty,
    ActionDeclareWar,
    ActionLeaveTreaty,
    ActionOfferPeace,
    ActionRespondTreaty,
)
from src.shared.events import (
    EventMessageCreated,
    EventTreatyProposed,
    EventTreatyRefused,
    EventWarStarted,
)
from src.shared.state import GameState


TREATY_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.Utf8,
    "name": pl.Utf8,
    "type": pl.Utf8,
    "members": pl.List(pl.Utf8),
    "status": pl.Utf8,
    "terms": pl.Utf8,
    "created_at": pl.Utf8,
    "source_country_id": pl.Utf8,
    "target_country_id": pl.Utf8,
}

PENDING_TREATY_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.Utf8,
    "source_country_id": pl.Utf8,
    "target_country_id": pl.Utf8,
    "treaty_type": pl.Utf8,
    "title": pl.Utf8,
    "terms": pl.Utf8,
    "status": pl.Utf8,
    "created_at": pl.Utf8,
}

WAR_SCHEMA: dict[str, pl.DataType] = {
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

RELATIONS_SCHEMA: dict[str, pl.DataType] = {
    "source": pl.Utf8,
    "target": pl.Utf8,
    "value": pl.Float64,
}

MILITARY_ALLIANCE_TYPES = {"alliance", "military_alliance", "military_pact"}
DEFENSIVE_TREATY_TYPES = {"defensive_alliance", "defensive_pact", *MILITARY_ALLIANCE_TYPES}


class DiplomacySystem(ISystem):
    """
    Processes diplomacy actions into authoritative treaty and war state.

    The client already knows how to render diplomacy tables. This system is the
    missing server-side piece that turns those panels from read-only data views
    into actual simulation state changes.
    """

    @property
    def id(self) -> str:
        return "base.diplomacy"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.bootstrap"]

    def update(self, state: GameState, delta_time: float) -> None:
        relevant_actions = [
            action
            for action in state.current_actions
            if isinstance(
                action,
                (
                    ActionCreateTreaty,
                    ActionRespondTreaty,
                    ActionLeaveTreaty,
                    ActionDeclareWar,
                    ActionOfferPeace,
                ),
            )
        ]
        if not relevant_actions:
            return

        treaties, pending, wars, relations, messages, news = self._ensure_tables(state)

        for action in relevant_actions:
            if isinstance(action, ActionCreateTreaty):
                pending, messages, news = self._handle_create_treaty(
                    state,
                    action,
                    treaties,
                    pending,
                    messages,
                    news,
                )
            elif isinstance(action, ActionRespondTreaty):
                treaties, pending, relations, messages, news = self._handle_respond_treaty(
                    state,
                    action,
                    treaties,
                    pending,
                    relations,
                    messages,
                    news,
                )
            elif isinstance(action, ActionLeaveTreaty):
                treaties, relations, messages, news = self._handle_leave_treaty(
                    state,
                    action,
                    treaties,
                    relations,
                    messages,
                    news,
                )
            elif isinstance(action, ActionDeclareWar):
                wars, relations, messages, news = self._handle_declare_war(
                    state,
                    action,
                    treaties,
                    wars,
                    relations,
                    messages,
                    news,
                )
            elif isinstance(action, ActionOfferPeace):
                wars, relations, messages, news = self._handle_offer_peace(
                    state,
                    action,
                    wars,
                    relations,
                    messages,
                    news,
                )

        state.update_table("countries_treaties", treaties)
        state.update_table("pending_treaties", pending)
        state.update_table("countries_wars", wars)
        state.update_table("countries_relations", relations)
        state.update_table("messages", messages)
        state.update_table("news_items", news)

    def _ensure_tables(
        self,
        state: GameState,
    ) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
        treaties = self._normalize_treaties_table(state.tables.get("countries_treaties"))
        pending = self._normalize_pending_table(state.tables.get("pending_treaties"))
        wars = self._normalize_wars_table(state.tables.get("countries_wars"))
        relations = self._normalize_relations_table(state.tables.get("countries_relations"))
        messages = state.tables.get("messages")
        if messages is None:
            messages = pl.DataFrame(
                schema={
                    "id": pl.Utf8,
                    "country_id": pl.Utf8,
                    "category": pl.Utf8,
                    "subject": pl.Utf8,
                    "body": pl.Utf8,
                    "is_read": pl.Boolean,
                    "created_at": pl.Utf8,
                }
            )
        news = state.tables.get("news_items")
        if news is None:
            news = pl.DataFrame(
                schema={
                    "id": pl.Utf8,
                    "headline": pl.Utf8,
                    "body": pl.Utf8,
                    "category": pl.Utf8,
                    "severity": pl.Utf8,
                    "related_country_id": pl.Utf8,
                    "created_at": pl.Utf8,
                }
            )
        return treaties, pending, wars, relations, messages, news

    def _handle_create_treaty(
        self,
        state: GameState,
        action: ActionCreateTreaty,
        treaties: pl.DataFrame,
        pending: pl.DataFrame,
        messages: pl.DataFrame,
        news: pl.DataFrame,
    ) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
        source = self._normalize_country_tag(action.source_country_tag)
        target = self._normalize_country_tag(action.target_country_tag)
        treaty_type = self._normalize_treaty_type(action.treaty_type)
        if not source or not target or source == target or not treaty_type:
            return pending, messages, news

        if self._has_matching_treaty(treaties, source, target, treaty_type):
            return pending, messages, news
        if self._has_matching_pending_treaty(pending, source, target, treaty_type):
            return pending, messages, news

        proposal_id = self._next_identifier("treaty", pending["id"].to_list(), state)
        created_at = self._timestamp(state)
        title = str(action.title or self._default_treaty_title(source, target, treaty_type))
        pending = self._append_rows(
            pending,
            [
                {
                    "id": proposal_id,
                    "source_country_id": source,
                    "target_country_id": target,
                    "treaty_type": treaty_type,
                    "title": title,
                    "terms": str(action.terms or ""),
                    "status": "pending",
                    "created_at": created_at,
                }
            ],
        )
        state.events.append(EventTreatyProposed(proposal_id, source, target))

        messages = self._append_message(
            state,
            messages,
            country_id=target,
            category="diplomacy",
            subject=f"Treaty proposal from {source}",
            body=f"{source} proposes {self._humanize_key(treaty_type)}: {title}",
        )
        news = self._append_news(
            state,
            news,
            headline=f"{source} sends a treaty proposal to {target}",
            body="Diplomatic channels are active and awaiting a formal response.",
            category="diplomacy",
            related_country_id=target,
        )
        return pending, messages, news

    def _handle_respond_treaty(
        self,
        state: GameState,
        action: ActionRespondTreaty,
        treaties: pl.DataFrame,
        pending: pl.DataFrame,
        relations: pl.DataFrame,
        messages: pl.DataFrame,
        news: pl.DataFrame,
    ) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
        if pending.is_empty() or "id" not in pending.columns:
            return treaties, pending, relations, messages, news

        match = pending.filter(pl.col("id") == action.treaty_id)
        if match.is_empty():
            return treaties, pending, relations, messages, news

        proposal = match.to_dicts()[0]
        source = self._normalize_country_tag(proposal.get("source_country_id"))
        target = self._normalize_country_tag(proposal.get("target_country_id"))
        responder = self._normalize_country_tag(action.responder_country_tag)
        if responder != target:
            return treaties, pending, relations, messages, news

        pending = pending.filter(pl.col("id") != action.treaty_id)
        treaty_type = self._normalize_treaty_type(proposal.get("treaty_type"))
        title = str(proposal.get("title") or self._default_treaty_title(source, target, treaty_type))

        if action.accept:
            if not self._has_matching_treaty(treaties, source, target, treaty_type):
                treaties = self._append_rows(
                    treaties,
                    [
                        {
                            "id": self._active_treaty_id(title, treaties, state),
                            "name": title,
                            "type": treaty_type,
                            "members": sorted({source, target}),
                            "status": "active",
                            "terms": str(proposal.get("terms") or ""),
                            "created_at": self._timestamp(state),
                            "source_country_id": source,
                            "target_country_id": target,
                        }
                    ],
                )
            relations = self._adjust_relation_pair(relations, source, target, self._treaty_relation_delta(treaty_type))
            messages = self._append_message(
                state,
                messages,
                country_id=source,
                category="diplomacy",
                subject=f"Treaty accepted by {target}",
                body=f"{target} accepted {title}.",
            )
            messages = self._append_message(
                state,
                messages,
                country_id=target,
                category="diplomacy",
                subject=f"Treaty activated with {source}",
                body=f"{title} is now active.",
            )
            news = self._append_news(
                state,
                news,
                headline=f"{title} enters into force",
                body="The agreement has moved from proposal to active obligations.",
                category="diplomacy",
                related_country_id=source,
            )
            return treaties, pending, relations, messages, news

        state.events.append(EventTreatyRefused(action.treaty_id, responder))
        relations = self._adjust_relation_pair(relations, source, target, -5.0)
        messages = self._append_message(
            state,
            messages,
            country_id=source,
            category="diplomacy",
            subject=f"Treaty rejected by {target}",
            body=f"{target} rejected {title}.",
        )
        news = self._append_news(
            state,
            news,
            headline=f"{target} rejects a treaty proposal from {source}",
            body="The proposal has been declined and removed from the pending queue.",
            category="diplomacy",
            related_country_id=target,
        )
        return treaties, pending, relations, messages, news

    def _handle_leave_treaty(
        self,
        state: GameState,
        action: ActionLeaveTreaty,
        treaties: pl.DataFrame,
        relations: pl.DataFrame,
        messages: pl.DataFrame,
        news: pl.DataFrame,
    ) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
        if treaties.is_empty():
            return treaties, relations, messages, news

        rows = []
        departing_country = self._normalize_country_tag(action.country_tag)
        changed_row: dict[str, Any] | None = None
        remaining_members: set[str] = set()

        for row in treaties.to_dicts():
            if str(row.get("id")) != action.treaty_id:
                rows.append(row)
                continue

            members = self._normalize_side(row.get("members"))
            if departing_country not in members:
                rows.append(row)
                continue

            remaining_members = members - {departing_country}
            changed_row = row
            if len(remaining_members) >= 2:
                row["members"] = sorted(remaining_members)
                rows.append(row)

        if changed_row is None:
            return treaties, relations, messages, news

        treaty_type = self._normalize_treaty_type(changed_row.get("type"))
        for peer in remaining_members:
            relations = self._adjust_relation_pair(
                relations,
                departing_country,
                peer,
                -0.5 * self._treaty_relation_delta(treaty_type),
            )

        treaties = self._frame_from_rows(TREATY_SCHEMA, rows)
        title = str(changed_row.get("name") or changed_row.get("id") or "Treaty")
        news = self._append_news(
            state,
            news,
            headline=f"{departing_country} leaves {title}",
            body="The agreement has been updated after a member withdrawal.",
            category="diplomacy",
            related_country_id=departing_country,
        )
        for peer in remaining_members:
            messages = self._append_message(
                state,
                messages,
                country_id=peer,
                category="diplomacy",
                subject=f"{departing_country} left {title}",
                body="Review the remaining obligations and force posture.",
            )
        return treaties, relations, messages, news

    def _handle_declare_war(
        self,
        state: GameState,
        action: ActionDeclareWar,
        treaties: pl.DataFrame,
        wars: pl.DataFrame,
        relations: pl.DataFrame,
        messages: pl.DataFrame,
        news: pl.DataFrame,
    ) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
        attacker = self._normalize_country_tag(action.source_country_tag)
        defender = self._normalize_country_tag(action.target_country_tag)
        if not attacker or not defender or attacker == defender:
            return wars, relations, messages, news

        if self._has_active_war(wars, attacker, defender):
            return wars, relations, messages, news

        attacker_side = self._expand_allies(treaties, attacker, include_defensive=False)
        defender_side = self._expand_allies(treaties, defender, include_defensive=True)
        attacker_side.discard(defender)
        defender_side.discard(attacker)

        overlapping = (attacker_side & defender_side) - {attacker, defender}
        if overlapping:
            # Defensive obligations should win when a country is pulled both ways.
            attacker_side -= overlapping

        war_id = self._next_identifier("war", wars["id"].to_list(), state)
        wars = self._append_rows(
            wars,
            [
                {
                    "id": war_id,
                    "name": f"{attacker} vs {defender}",
                    "side_a": sorted(attacker_side),
                    "side_b": sorted(defender_side),
                    "status": "active",
                    "casus_belli": str(action.casus_belli or ""),
                    "created_at": self._timestamp(state),
                    "leader_a": attacker,
                    "leader_b": defender,
                    "intent_a": "war",
                    "intent_b": "war",
                }
            ],
        )
        state.events.append(EventWarStarted(war_id, attacker, defender))

        for side_a_tag in attacker_side:
            for side_b_tag in defender_side:
                relations = self._set_relation_pair(relations, side_a_tag, side_b_tag, -100.0)

        for country_id in sorted(attacker_side | defender_side):
            if country_id in attacker_side:
                subject = f"War declared against {', '.join(sorted(defender_side))}"
                body = f"{attacker} opened a new war front. Casus belli: {action.casus_belli or 'Unspecified'}"
            else:
                subject = f"War declared by {', '.join(sorted(attacker_side))}"
                body = f"{defender} is now mobilizing with its partners. Casus belli: {action.casus_belli or 'Unspecified'}"
            messages = self._append_message(state, messages, country_id, "war", subject, body)

        news = self._append_news(
            state,
            news,
            headline=f"War breaks out: {attacker} vs {defender}",
            body="Alliance commitments and active war tables have been updated.",
            category="war",
            related_country_id=attacker,
            severity="warning",
        )
        return wars, relations, messages, news

    def _handle_offer_peace(
        self,
        state: GameState,
        action: ActionOfferPeace,
        wars: pl.DataFrame,
        relations: pl.DataFrame,
        messages: pl.DataFrame,
        news: pl.DataFrame,
    ) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
        if wars.is_empty() or "id" not in wars.columns:
            return wars, relations, messages, news

        match = wars.filter(pl.col("id") == action.war_id)
        if match.is_empty():
            return wars, relations, messages, news

        war = match.to_dicts()[0]
        side_a = self._normalize_side(war.get("side_a"))
        side_b = self._normalize_side(war.get("side_b"))
        source = self._normalize_country_tag(action.source_country_tag)

        leader_a = war.get("leader_a")
        leader_b = war.get("leader_b")

        # Only the two initial countries (leaders) can declare peace/war intentions
        if source != leader_a and source != leader_b:
            return wars, relations, messages, news

        # Intention is determined by action.terms ("peace" or "war")
        new_intent = "war" if action.terms == "war" else "peace"
        intent_col = "intent_a" if source == leader_a else "intent_b"

        # Update the intention in the dataframe
        wars = wars.with_columns(
            pl.when(pl.col("id") == action.war_id)
            .then(pl.lit(new_intent))
            .otherwise(pl.col(intent_col))
            .alias(intent_col)
        )

        # Retrieve the updated row to check if BOTH leaders agree on peace
        updated_match = wars.filter(pl.col("id") == action.war_id)
        if not updated_match.is_empty():
            updated_war = updated_match.to_dicts()[0]
            if updated_war.get("intent_a") == "peace" and updated_war.get("intent_b") == "peace":
                # BOTH AGREE -> END THE WAR FOR EVERYONE
                wars = wars.filter(pl.col("id") != action.war_id)
                for left in side_a:
                    for right in side_b:
                        relations = self._adjust_relation_pair(relations, left, right, 15.0)

                all_participants = sorted(side_a | side_b)
                for country_id in all_participants:
                    messages = self._append_message(
                        state,
                        messages,
                        country_id=country_id,
                        category="war",
                        subject=f"Peace treaty signed for {action.war_id}",
                        body=f"Both {leader_a} and {leader_b} have agreed to cease hostilities. The war has ended.",
                    )

                news = self._append_news(
                    state,
                    news,
                    headline=f"Peace treaty signed: {leader_a} & {leader_b}",
                    body=f"Hostilities in {action.war_id} have ceased after mutual agreement.",
                    category="war",
                    related_country_id=source,
                    severity="info",
                )
            else:
                # Intentions updated, but war not ended yet. Send inbox messages to leaders.
                opposing_leader = leader_b if source == leader_a else leader_a
                messages = self._append_message(
                    state,
                    messages,
                    country_id=opposing_leader,
                    category="war",
                    subject=f"Peace terms proposed in {action.war_id}",
                    body=f"{source} has declared its intention: {new_intent.upper()}. It awaits your decision.",
                )

        return wars, relations, messages, news

    def _normalize_treaties_table(self, df: pl.DataFrame | None) -> pl.DataFrame:
        rows = [] if df is None or df.is_empty() else df.to_dicts()
        normalized_rows = []
        for row in rows:
            members = self._normalize_side(row.get("members"))
            if not members:
                members = self._normalize_side(row.get("side_a")) | self._normalize_side(row.get("side_b"))
            normalized_rows.append(
                {
                    "id": str(row.get("id") or ""),
                    "name": str(row.get("name") or row.get("id") or "Treaty"),
                    "type": self._normalize_treaty_type(row.get("type")),
                    "members": sorted(members),
                    "status": str(row.get("status") or "active"),
                    "terms": str(row.get("terms") or ""),
                    "created_at": str(row.get("created_at") or ""),
                    "source_country_id": str(row.get("source_country_id") or ""),
                    "target_country_id": str(row.get("target_country_id") or ""),
                }
            )
        return self._frame_from_rows(TREATY_SCHEMA, normalized_rows)

    def _normalize_pending_table(self, df: pl.DataFrame | None) -> pl.DataFrame:
        rows = [] if df is None or df.is_empty() else df.to_dicts()
        normalized_rows = [
            {
                "id": str(row.get("id") or ""),
                "source_country_id": str(row.get("source_country_id") or ""),
                "target_country_id": str(row.get("target_country_id") or ""),
                "treaty_type": self._normalize_treaty_type(row.get("treaty_type")),
                "title": str(row.get("title") or ""),
                "terms": str(row.get("terms") or ""),
                "status": str(row.get("status") or "pending"),
                "created_at": str(row.get("created_at") or ""),
            }
            for row in rows
        ]
        return self._frame_from_rows(PENDING_TREATY_SCHEMA, normalized_rows)

    def _normalize_wars_table(self, df: pl.DataFrame | None) -> pl.DataFrame:
        rows = [] if df is None or df.is_empty() else df.to_dicts()
        normalized_rows = []
        for index, row in enumerate(rows, start=1):
            raw_a = list(row.get("side_a") or [])
            raw_b = list(row.get("side_b") or [])
            
            leader_a = str(row.get("leader_a") or (raw_a[0] if raw_a else "UNK"))
            leader_b = str(row.get("leader_b") or (raw_b[0] if raw_b else "UNK"))
            
            normalized_rows.append(
                {
                    "id": str(row.get("id") or f"war-{index:03d}"),
                    "name": str(row.get("name") or row.get("id") or f"War {index}"),
                    "side_a": sorted(self._normalize_side(raw_a)),
                    "side_b": sorted(self._normalize_side(raw_b)),
                    "status": str(row.get("status") or "active"),
                    "casus_belli": str(row.get("casus_belli") or ""),
                    "created_at": str(row.get("created_at") or ""),
                    "leader_a": leader_a,
                    "leader_b": leader_b,
                    "intent_a": str(row.get("intent_a") or "war"),
                    "intent_b": str(row.get("intent_b") or "war"),
                }
            )
        return self._frame_from_rows(WAR_SCHEMA, normalized_rows)

    def _normalize_relations_table(self, df: pl.DataFrame | None) -> pl.DataFrame:
        if df is None or df.is_empty():
            return pl.DataFrame(schema=RELATIONS_SCHEMA)

        required = set(RELATIONS_SCHEMA)
        if required.issubset(set(df.columns)):
            return df.select(
                pl.col("source").cast(pl.Utf8),
                pl.col("target").cast(pl.Utf8),
                pl.col("value").cast(pl.Float64),
            )

        rows = [
            {
                "source": str(row.get("source") or ""),
                "target": str(row.get("target") or ""),
                "value": float(row.get("value") or 0.0),
            }
            for row in df.to_dicts()
            if row.get("source") is not None and row.get("target") is not None
        ]
        return self._frame_from_rows(RELATIONS_SCHEMA, rows)

    def _has_matching_treaty(self, treaties: pl.DataFrame, source: str, target: str, treaty_type: str) -> bool:
        participants = {source, target}
        for row in treaties.to_dicts():
            if self._normalize_treaty_type(row.get("type")) != treaty_type:
                continue
            if (
                self._normalize_side(row.get("members")) == participants
                and str(row.get("status") or "active").lower() == "active"
            ):
                return True
        return False

    def _has_matching_pending_treaty(self, pending: pl.DataFrame, source: str, target: str, treaty_type: str) -> bool:
        participants = {source, target}
        for row in pending.to_dicts():
            row_participants = {
                self._normalize_country_tag(row.get("source_country_id")),
                self._normalize_country_tag(row.get("target_country_id")),
            }
            if row_participants == participants and self._normalize_treaty_type(row.get("treaty_type")) == treaty_type:
                return True
        return False

    def _has_active_war(self, wars: pl.DataFrame, attacker: str, defender: str) -> bool:
        for row in wars.to_dicts():
            if str(row.get("status") or "active").lower() != "active":
                continue
            side_a = self._normalize_side(row.get("side_a"))
            side_b = self._normalize_side(row.get("side_b"))
            if (attacker in side_a and defender in side_b) or (attacker in side_b and defender in side_a):
                return True
        return False

    def _expand_allies(self, treaties: pl.DataFrame, seed_country: str, include_defensive: bool) -> set[str]:
        allowed_types = DEFENSIVE_TREATY_TYPES if include_defensive else MILITARY_ALLIANCE_TYPES
        coalition = {seed_country}
        frontier = [seed_country]
        rows = treaties.to_dicts()

        while frontier:
            country = frontier.pop(0)
            for row in rows:
                treaty_type = self._normalize_treaty_type(row.get("type"))
                if treaty_type not in allowed_types or str(row.get("status") or "active").lower() != "active":
                    continue
                members = self._normalize_side(row.get("members"))
                if country not in members:
                    continue

                new_members = members - coalition
                if new_members:
                    coalition.update(new_members)
                    frontier.extend(sorted(new_members))

        return coalition

    def _adjust_relation_pair(self, relations: pl.DataFrame, left: str, right: str, delta: float) -> pl.DataFrame:
        relations = self._adjust_relation(relations, left, right, delta)
        relations = self._adjust_relation(relations, right, left, delta)
        return relations

    def _set_relation_pair(self, relations: pl.DataFrame, left: str, right: str, value: float) -> pl.DataFrame:
        relations = self._set_relation(relations, left, right, value)
        relations = self._set_relation(relations, right, left, value)
        return relations

    def _adjust_relation(self, relations: pl.DataFrame, source: str, target: str, delta: float) -> pl.DataFrame:
        current_value = self._relation_value(relations, source, target)
        return self._set_relation(relations, source, target, current_value + delta)

    def _set_relation(self, relations: pl.DataFrame, source: str, target: str, value: float) -> pl.DataFrame:
        clamped_value = max(-100.0, min(100.0, float(value)))
        mask = (pl.col("source") == source) & (pl.col("target") == target)
        if not relations.filter(mask).is_empty():
            return relations.with_columns(
                pl.when(mask).then(pl.lit(clamped_value)).otherwise(pl.col("value")).alias("value")
            )

        return self._append_rows(
            relations,
            [{"source": source, "target": target, "value": clamped_value}],
        )

    def _relation_value(self, relations: pl.DataFrame, source: str, target: str) -> float:
        match = relations.filter((pl.col("source") == source) & (pl.col("target") == target))
        if match.is_empty():
            return 0.0
        return float(match["value"][0] or 0.0)

    def _append_message(
        self,
        state: GameState,
        messages: pl.DataFrame,
        country_id: str,
        category: str,
        subject: str,
        body: str,
    ) -> pl.DataFrame:
        message_id = self._next_identifier("msg", messages["id"].to_list(), state)
        state.events.append(EventMessageCreated(message_id, country_id, category))
        return self._append_rows(
            messages,
            [
                {
                    "id": message_id,
                    "country_id": country_id,
                    "category": category,
                    "subject": subject,
                    "body": body,
                    "is_read": False,
                    "created_at": self._timestamp(state),
                }
            ],
        )

    def _append_news(
        self,
        state: GameState,
        news: pl.DataFrame,
        headline: str,
        body: str,
        category: str,
        related_country_id: str,
        severity: str = "info",
    ) -> pl.DataFrame:
        news_id = self._next_identifier("news", news["id"].to_list(), state)
        return self._append_rows(
            news,
            [
                {
                    "id": news_id,
                    "headline": headline,
                    "body": body,
                    "category": category,
                    "severity": severity,
                    "related_country_id": related_country_id,
                    "created_at": self._timestamp(state),
                }
            ],
        )

    def _append_rows(self, base: pl.DataFrame, rows: list[dict[str, Any]]) -> pl.DataFrame:
        if not rows:
            return base
        return pl.concat([base, pl.DataFrame(rows)], how="diagonal_relaxed")

    def _frame_from_rows(self, schema: dict[str, pl.DataType], rows: Sequence[dict[str, Any]]) -> pl.DataFrame:
        if not rows:
            return pl.DataFrame(schema=schema)
        return pl.DataFrame(list(rows), schema=schema)

    def _normalize_side(self, value: Any) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, list):
            return {self._normalize_country_tag(item) for item in value if self._normalize_country_tag(item)}
        if isinstance(value, tuple):
            return {self._normalize_country_tag(item) for item in value if self._normalize_country_tag(item)}
        if isinstance(value, str):
            return {self._normalize_country_tag(item) for item in value.split(",") if self._normalize_country_tag(item)}
        return set()

    def _normalize_country_tag(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip().upper()

    def _normalize_treaty_type(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return ""
        return re.sub(r"[^a-z0-9]+", "_", text).strip("_")

    def _humanize_key(self, value: str) -> str:
        return value.replace("_", " ").title()

    def _default_treaty_title(self, source: str, target: str, treaty_type: str) -> str:
        return f"{source}-{target} {self._humanize_key(treaty_type)}"

    def _active_treaty_id(self, title: str, treaties: pl.DataFrame, state: GameState) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
        if not slug:
            slug = self._next_identifier("treaty", treaties["id"].to_list(), state)
        existing_ids = {str(value) for value in treaties["id"].to_list()} if "id" in treaties.columns else set()
        candidate = slug
        counter = 2
        while candidate in existing_ids:
            candidate = f"{slug}_{counter}"
            counter += 1
        return candidate

    def _treaty_relation_delta(self, treaty_type: str) -> float:
        if treaty_type in MILITARY_ALLIANCE_TYPES:
            return 18.0
        if treaty_type in {"defensive_alliance", "defensive_pact"}:
            return 14.0
        if treaty_type == "research_accord":
            return 12.0
        if treaty_type == "trade_accord":
            return 10.0
        return 8.0

    def _timestamp(self, state: GameState) -> str:
        return state.time.date_str or "2001-01-01 00:00"

    def _next_identifier(self, prefix: str, existing_ids: Iterable[Any], state: GameState) -> str:
        normalized_existing = {str(value) for value in existing_ids if value is not None}
        tick = int(state.globals.get("tick", 0))
        counter = max(1, len(normalized_existing) + 1)
        candidate = f"{prefix}-{tick:07d}-{counter:03d}"
        while candidate in normalized_existing:
            counter += 1
            candidate = f"{prefix}-{tick:07d}-{counter:03d}"
        return candidate


# The public import path predates the richer treaty lifecycle implementation.
# Keeping it stable avoids coupling clients and mods to an internal module move.
from modules.base.systems.world.treaty_diplomacy import TreatyDiplomacySystem

DiplomacySystem = TreatyDiplomacySystem
