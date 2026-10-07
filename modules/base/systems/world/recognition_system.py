"""Authoritative UN recognition votes for completed regional annexations."""

from __future__ import annotations

from typing import Any

import polars as pl

from modules.base.systems.world.authority_policy import player_controls_country
from modules.base.systems.world.recognition_policy import (
    eligible_voters,
    RecognitionAIPolicy,
)
from src.shared.actions import ActionCastRecognitionVote
from src.shared.determinism import DeterministicRuntime
from src.shared.events import (
    EventNewDay,
    EventRecognitionCaseOpened,
    EventRecognitionCaseResolved,
    EventRecognitionVoteChanged,
    EventRecognitionWithdrawn,
)
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_CACHE


MINUTES_PER_DAY = 1_440
DEFAULT_VOTING_WINDOW_DAYS = 30
VALID_VOTES = frozenset({"yes", "no", "abstain"})
MAX_VOTING_WINDOW_DAYS = 3_650


class RecognitionSystem(ISystem):
    """Opens cases from annexation facts, resolves votes, and withdraws stale access."""

    access = SystemAccess(
        reads=frozenset(
            {
                "countries",
                "regions",
                "annexation_claims",
                "recognition_cases",
                "recognition_votes",
                "regional_recognition_status",
                "countries_relations",
                "countries_wars",
                "countries_treaties",
                "messages",
                "news_items",
            }
        ),
        writes=frozenset(
            {
                "recognition_cases",
                "recognition_votes",
                "regional_recognition_status",
                "messages",
                "news_items",
            }
        ),
        handles=frozenset({ActionCastRecognitionVote}),
        phase=SystemPhase.DIPLOMACY + 1,
    )
    runtime_state_contract = {
        "_last_claim_revision": SYSTEM_STATE_CACHE,
        "_last_region_revision": SYSTEM_STATE_CACHE,
        "_last_case_revision": SYSTEM_STATE_CACHE,
        "_next_deadline": SYSTEM_STATE_CACHE,
    }

    def __init__(self) -> None:
        self._last_claim_revision = -1
        self._last_region_revision = -1
        self._last_case_revision = -1
        self._next_deadline = -1

    @property
    def id(self) -> str:
        return "base.recognition"

    @property
    def dependencies(self) -> list[str]:
        return ["base.diplomacy"]

    def update(self, state: GameState, delta_time: float) -> None:
        required = {
            "countries",
            "regions",
            "annexation_claims",
            "recognition_cases",
            "recognition_votes",
            "regional_recognition_status",
        }
        if not required.issubset(state.tables):
            return

        now = max(0, int(state.time.total_minutes))
        claim_revision = state.table_revisions.get("annexation_claims", 0)
        region_revision = state.table_revisions.get("regions", 0)
        case_revision = state.table_revisions.get("recognition_cases", 0)
        case_due = self._next_deadline >= 0 and now >= self._next_deadline
        is_new_day = any(isinstance(event, EventNewDay) for event in state.events)
        actions = [
            action
            for action in state.current_actions
            if isinstance(action, ActionCastRecognitionVote)
        ]
        claims_changed = claim_revision != self._last_claim_revision
        regions_changed = region_revision != self._last_region_revision
        cases_changed = case_revision != self._last_case_revision
        if not (claims_changed or regions_changed or cases_changed or case_due or is_new_day or actions):
            return

        cases = state.tables["recognition_cases"].to_dicts()
        votes = {
            str(row["id"]): row
            for row in state.tables["recognition_votes"].to_dicts()
        }
        statuses = (
            state.tables["regional_recognition_status"].to_dicts()
            if regions_changed or case_due
            else []
        )
        current_countries = {
            self._tag(value)
            for value in state.tables["countries"].get_column("id").to_list()
        }
        needs_notifications = bool(regions_changed or claims_changed or case_due or actions)
        messages = (
            state.tables.get("messages", pl.DataFrame()).to_dicts()
            if needs_notifications
            else []
        )
        news = (
            state.tables.get("news_items", pl.DataFrame()).to_dicts()
            if needs_notifications
            else []
        )
        case_by_id = {str(row["id"]): row for row in cases}
        events: list[Any] = []
        statuses_by_claim: dict[str, list[dict[str, Any]]] = {}
        for status in statuses:
            if status.get("status") == "recognized":
                statuses_by_claim.setdefault(str(status.get("annexation_claim_id") or ""), []).append(status)
        case_rows_changed = False
        vote_rows_changed = False
        status_rows_changed = False
        messages_changed = False
        news_changed = False

        if regions_changed:
            for case in sorted(cases, key=lambda row: str(row.get("id") or "")):
                if case.get("status") not in {"pending", "passed"}:
                    continue
                region = self._region(state, int(case.get("region_id") or 0))
                claimant = self._tag(case.get("claimant_id"))
                if region is None or self._tag(region.get("owner")) != claimant or self._tag(region.get("controller")) != claimant:
                    case["status"] = "withdrawn"
                    case["resolved_at_minute"] = now
                    case["reason"] = "Claimant no longer owns and controls the region."
                    case_rows_changed = True
                    for status in statuses_by_claim.get(str(case.get("annexation_claim_id") or ""), ()):
                        if status.get("status") == "recognized":
                            status["status"] = "withdrawn"
                            status["withdrawn_at_minute"] = now
                            status["reason"] = case["reason"]
                            status_rows_changed = True
                    event = EventRecognitionWithdrawn(
                        case_id=str(case["id"]),
                        region_id=int(case.get("region_id") or 0),
                        claimant_id=claimant,
                        at_minute=now,
                    )
                    events.append(event)
                    messages_changed |= self._notify(
                        state,
                        messages,
                        news,
                        message_id=self._new_id(state, "recognition-withdrawn"),
                        headline=f"Recognition withdrawn for region {case['region_id']}",
                        body="Recognition ended because the claimant no longer owns and controls the region.",
                        category="diplomacy",
                        country_ids=(claimant, self._tag(case.get("former_owner_id"))),
                        now=now,
                    )
                    news_changed = True

        opened_cases = self._open_completed_claims(state, cases, case_by_id, events, messages, news, now)
        if opened_cases:
            case_rows_changed = True
            messages_changed = True
            news_changed = True

        for action in actions:
            result = self._cast_vote(
                state,
                action,
                case_by_id,
                votes,
                events,
                messages,
                news,
                now,
                trusted_ai=False,
            )
            vote_rows_changed |= result == "changed"
            messages_changed |= result == "changed"
            news_changed |= result == "changed"

        if is_new_day or opened_cases:
            ai_policy = RecognitionAIPolicy(state)
            for case in sorted(cases, key=lambda row: str(row.get("id") or "")):
                if case.get("status") != "pending":
                    continue
                for country_id in case.get("eligible_voters") or []:
                    country_id = self._tag(country_id)
                    if country_id not in current_countries or self._is_human_country(state, country_id):
                        continue
                    vote_id = self._vote_id(str(case["id"]), country_id)
                    if vote_id in votes:
                        continue
                    action = ActionCastRecognitionVote(
                        player_id="AI_SYSTEM",
                        case_id=str(case["id"]),
                        country_tag=country_id,
                        vote=ai_policy.vote(country_id, str(case["claimant_id"])),
                    )
                    result = self._cast_vote(
                        state,
                        action,
                        case_by_id,
                        votes,
                        events,
                        messages,
                        news,
                        now,
                        trusted_ai=True,
                    )
                    vote_rows_changed |= result == "changed"

        for case in sorted(cases, key=lambda row: str(row.get("id") or "")):
            if case.get("status") != "pending" or int(case.get("deadline_at_minute") or 0) > now:
                continue
            voter_ids = tuple(self._tag(value) for value in case.get("eligible_voters") or [])
            case_votes = [
                votes[self._vote_id(str(case["id"]), voter_id)]["vote"]
                for voter_id in voter_ids
                if self._vote_id(str(case["id"]), voter_id) in votes
            ]
            yes_count = sum(value == "yes" for value in case_votes)
            no_count = sum(value == "no" for value in case_votes)
            abstain_count = sum(value == "abstain" for value in case_votes)
            case["yes_votes"] = yes_count
            case["no_votes"] = no_count
            case["abstain_votes"] = abstain_count
            case["resolved_at_minute"] = now
            case["status"] = "passed" if yes_count > len(voter_ids) / 2 else "rejected"
            case["reason"] = (
                "Strict majority of the captured UN voter roster recognized the annexation."
                if case["status"] == "passed"
                else "The recognition vote did not reach a strict majority of the captured UN voter roster."
            )
            case_rows_changed = True
            if case["status"] == "passed":
                yes_voters = {
                    voter_id
                    for voter_id in voter_ids
                    if self._vote_id(str(case["id"]), voter_id) in votes
                    and votes[self._vote_id(str(case["id"]), voter_id)]["vote"] == "yes"
                }
                for voter_id in voter_ids:
                    status_id = f"{case['id']}:{voter_id}"
                    status_row = {
                        "id": status_id,
                        "annexation_claim_id": str(case["annexation_claim_id"]),
                        "case_id": str(case["id"]),
                        "region_id": int(case["region_id"]),
                        "country_id": voter_id,
                        "claimant_id": str(case["claimant_id"]),
                        "status": "recognized" if voter_id in yes_voters else "not_recognized",
                        "granted_at_minute": now,
                        "withdrawn_at_minute": 0,
                        "reason": "Voted in a recognition case that passed by strict majority.",
                    }
                    statuses.append(status_row)
                status_rows_changed = bool(voter_ids)
            events.append(
                EventRecognitionCaseResolved(
                    case_id=str(case["id"]),
                    region_id=int(case["region_id"]),
                    status=str(case["status"]),
                    yes_votes=yes_count,
                    eligible_voters=len(voter_ids),
                    at_minute=now,
                )
            )
            messages_changed |= self._notify(
                state,
                messages,
                news,
                message_id=self._new_id(state, "recognition-resolved"),
                headline=f"Recognition vote {case['status']} for region {case['region_id']}",
                body=f"Claimant {case['claimant_id']}; votes: {yes_count} for, {no_count} against, {abstain_count} abstentions.",
                category="diplomacy",
                country_ids=(str(case["claimant_id"]), str(case["former_owner_id"])),
                now=now,
            )
            news_changed = True

        if case_rows_changed:
            state.update_table("recognition_cases", self._frame(state, "recognition_cases", cases))
        if vote_rows_changed:
            state.update_table("recognition_votes", self._frame(state, "recognition_votes", list(votes.values())))
        if status_rows_changed:
            state.update_table("regional_recognition_status", self._frame(state, "regional_recognition_status", statuses))
        if messages_changed:
            state.update_table("messages", self._frame(state, "messages", messages))
        if news_changed:
            state.update_table("news_items", self._frame(state, "news_items", news))
        state.events.extend(events)

        self._last_claim_revision = state.table_revisions.get("annexation_claims", 0)
        self._last_region_revision = state.table_revisions.get("regions", 0)
        self._last_case_revision = state.table_revisions.get("recognition_cases", 0)
        pending_deadlines = [
            int(row.get("deadline_at_minute") or 0)
            for row in cases
            if row.get("status") == "pending"
        ]
        self._next_deadline = min(pending_deadlines) if pending_deadlines else -1

    def _open_completed_claims(
        self,
        state: GameState,
        cases: list[dict[str, Any]],
        case_by_id: dict[str, dict[str, Any]],
        events: list[Any],
        messages: list[dict[str, Any]],
        news: list[dict[str, Any]],
        now: int,
    ) -> int:
        existing_claims = {str(row.get("annexation_claim_id")) for row in cases}
        opened = 0
        voting_window_days = self._voting_window_days(state)
        for claim in sorted(
            state.tables["annexation_claims"].to_dicts(),
            key=lambda row: str(row.get("id") or ""),
        ):
            if str(claim.get("status") or "").lower() != "annexed":
                continue
            claim_id = str(claim.get("id") or "")
            if not claim_id or claim_id in existing_claims:
                continue
            region_id = int(claim.get("region_id") or 0)
            claimant = self._tag(claim.get("annexing_country_id"))
            former_owner = self._tag(claim.get("political_owner_id"))
            region = self._region(state, region_id)
            if (
                not claimant
                or region is None
                or self._tag(region.get("owner")) != claimant
                or self._tag(region.get("controller")) != claimant
            ):
                continue
            voters = eligible_voters(state.tables.get("countries"), claimant, former_owner)
            case_id = f"recognition-{claim_id}"
            case = {
                "id": case_id,
                "annexation_claim_id": claim_id,
                "region_id": region_id,
                "claimant_id": claimant,
                "former_owner_id": former_owner,
                "eligible_voters": list(voters),
                "opened_at_minute": now,
                "deadline_at_minute": now + voting_window_days * MINUTES_PER_DAY,
                "status": "pending",
                "resolved_at_minute": 0,
                "yes_votes": 0,
                "no_votes": 0,
                "abstain_votes": 0,
                "reason": "Recognition vote opened after annexation completed.",
            }
            cases.append(case)
            case_by_id[case_id] = case
            existing_claims.add(claim_id)
            opened += 1
            events.append(
                EventRecognitionCaseOpened(
                    case_id=case_id,
                    region_id=region_id,
                    claimant_id=claimant,
                    former_owner_id=former_owner,
                    deadline_at_minute=int(case["deadline_at_minute"]),
                )
            )
            self._notify(
                state,
                messages,
                news,
                message_id=self._new_id(state, "recognition-opened"),
                headline=f"Recognition vote opened for region {region_id}",
                body=f"Claimant {claimant}; former owner {former_owner}; voting closes in {voting_window_days} game days.",
                category="diplomacy",
                country_ids=(claimant, former_owner),
                now=now,
            )
        return opened

    def _cast_vote(
        self,
        state: GameState,
        action: ActionCastRecognitionVote,
        case_by_id: dict[str, dict[str, Any]],
        votes: dict[str, dict[str, Any]],
        events: list[Any],
        messages: list[dict[str, Any]],
        news: list[dict[str, Any]],
        now: int,
        *,
        trusted_ai: bool,
    ) -> str:
        case_id = str(action.case_id or "")
        country_id = self._tag(action.country_tag)
        case = case_by_id.get(case_id)
        reason = ""
        vote = str(action.vote or "").strip().lower()
        if case is None or case.get("status") != "pending":
            reason = "The recognition case is not open."
        elif now >= int(case.get("deadline_at_minute") or 0):
            reason = "The recognition voting deadline has passed."
        elif vote not in VALID_VOTES:
            reason = "Vote must be yes, no, or abstain."
        elif country_id not in {self._tag(value) for value in case.get("eligible_voters") or []}:
            reason = "This country is not on the case's captured eligible voter roster."
        elif not trusted_ai and not self._country_exists(state, country_id):
            reason = "The voting country is no longer present in the country roster."
        elif not trusted_ai and not player_controls_country(state, action.player_id, country_id):
            reason = "The actor does not control the voting country."
        if reason:
            self._record_result(state, action, "rejected", reason, now)
            return "rejected"

        vote_id = self._vote_id(case_id, country_id)
        previous = votes.get(vote_id)
        if previous is not None and previous.get("vote") == vote:
            self._record_result(state, action, "applied", "This vote is already recorded.", now)
            return "unchanged"
        votes[vote_id] = {
            "id": vote_id,
            "case_id": case_id,
            "country_id": country_id,
            "vote": vote,
            "cast_at_minute": now,
            "source": "ai" if trusted_ai else "player",
        }
        events.append(
            EventRecognitionVoteChanged(
                case_id=case_id,
                country_id=country_id,
                vote=vote,
                at_minute=now,
            )
        )
        if not trusted_ai:
            self._record_result(state, action, "applied", "Recognition vote recorded.", now)
            self._notify(
                state,
                messages,
                news,
                message_id=self._new_id(state, "recognition-vote"),
                headline=f"{country_id} voted {vote} on region {case['region_id']}",
                body=f"Recognition case {case_id} received a {vote} vote from {country_id}.",
                category="diplomacy",
                country_ids=(country_id, str(case["claimant_id"])),
                now=now,
            )
        return "changed"

    def _notify(
        self,
        state: GameState,
        messages: list[dict[str, Any]],
        news: list[dict[str, Any]],
        *,
        message_id: str,
        headline: str,
        body: str,
        category: str,
        country_ids: tuple[str, ...],
        now: int,
    ) -> bool:
        changed = False
        known_messages = {str(row.get("id")) for row in messages}
        for country_id in sorted({self._tag(value) for value in country_ids if self._tag(value)}):
            row_id = f"{message_id}:{country_id}"
            if row_id in known_messages:
                continue
            messages.append(
                {
                    "id": row_id,
                    "country_id": country_id,
                    "category": category,
                    "subject": headline,
                    "body": body,
                    "is_read": False,
                    "created_at": str(state.time.date_str),
                }
            )
            known_messages.add(row_id)
            changed = True
        news_id = f"{message_id}:news"
        if news_id not in {str(row.get("id")) for row in news}:
            news.append(
                {
                    "id": news_id,
                    "headline": headline,
                    "body": body,
                    "category": category,
                    "severity": "info",
                    "related_country_id": country_ids[0] if country_ids else "",
                    "created_at": str(state.time.date_str),
                }
            )
            changed = True
        return changed

    def _record_result(
        self,
        state: GameState,
        action: ActionCastRecognitionVote,
        status: str,
        reason: str,
        now: int,
    ) -> None:
        state.journal.append_command_result(
            {
                "result_id": self._new_id(state, "recognition-command"),
                "action_type": type(action).__name__,
                "player_id": str(action.player_id),
                "status": status,
                "reason": reason,
                "game_minute": now,
                "case_id": str(action.case_id),
                "country_id": self._tag(action.country_tag),
                "vote": str(action.vote),
            }
        )

    @staticmethod
    def _new_id(state: GameState, prefix: str) -> str:
        runtime = DeterministicRuntime(state.determinism)
        return runtime.next_id(prefix, int(state.globals.get("tick", 0)))

    @staticmethod
    def _vote_id(case_id: str, country_id: str) -> str:
        return f"{case_id}:{country_id}"

    @staticmethod
    def _region(state: GameState, region_id: int) -> dict[str, Any] | None:
        regions = state.tables.get("regions")
        if regions is None or regions.is_empty() or "id" not in regions.columns:
            return None
        match = regions.filter(pl.col("id") == int(region_id))
        return match.row(0, named=True) if not match.is_empty() else None

    @staticmethod
    def _country_exists(state: GameState, country_id: str) -> bool:
        countries = state.tables.get("countries")
        return bool(
            countries is not None
            and not countries.is_empty()
            and "id" in countries.columns
            and not countries.filter(pl.col("id").cast(pl.Utf8).str.to_uppercase() == country_id).is_empty()
        )

    @staticmethod
    def _voting_window_days(state: GameState) -> int:
        raw = state.globals.get("recognition_voting_window_days", DEFAULT_VOTING_WINDOW_DAYS)
        if isinstance(raw, bool):
            return DEFAULT_VOTING_WINDOW_DAYS
        try:
            value = int(raw)
        except (TypeError, ValueError, OverflowError):
            return DEFAULT_VOTING_WINDOW_DAYS
        if not 1 <= value <= MAX_VOTING_WINDOW_DAYS:
            return DEFAULT_VOTING_WINDOW_DAYS
        state.globals.setdefault("recognition_voting_window_days", value)
        return value

    @staticmethod
    def _is_human_country(state: GameState, country_id: str) -> bool:
        player_map = state.globals.get("player_country_map", {})
        if isinstance(player_map, dict) and country_id in {
            str(value or "").strip().upper() for value in player_map.values()
        }:
            return True
        return country_id == str(state.globals.get("player_tag") or "").strip().upper()

    @staticmethod
    def _tag(value: Any) -> str:
        return str(value or "").strip().upper()

    @staticmethod
    def _frame(state: GameState, table_name: str, rows: list[dict[str, Any]]) -> pl.DataFrame:
        schema = state.tables[table_name].schema
        return pl.DataFrame(rows, schema=schema, strict=False) if rows else pl.DataFrame(schema=schema)
