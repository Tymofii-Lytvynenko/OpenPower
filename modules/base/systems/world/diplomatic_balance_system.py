from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any

import polars as pl

from src.shared.events import (
    EventAggressiveExpansionUpdated,
    EventBattleEnded,
    EventBattleUpdated,
    EventCoalitionChanged,
    EventNewDay,
    EventOccupationChanged,
    EventTerritoryOwnershipChanged,
    EventWarExhaustionUpdated,
    EventWarEnded,
    EventWarStarted,
)
from src.shared.state import GAME_EPOCH, GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase


_EXPANSION_WINDOW = 365 * 1440
_COALITION_THRESHOLD = 0.6


class DiplomaticBalanceSystem(ISystem):
    """Maintains expansion pressure, defensive coalitions, and per-war exhaustion."""

    access = SystemAccess(
        reads=frozenset(
            {
                "countries",
                "regions",
                "region_adjacency",
                "countries_wars",
                "countries_treaties",
                "units",
                "battles",
                "battle_casualty_records",
                "naval_blockades",
                "aggressive_expansion_events",
                "aggressive_expansion_scores",
                "coalition_pacts",
                "war_exhaustion_states",
            }
        ),
        writes=frozenset(
            {
                "countries",
                "units",
                "aggressive_expansion_events",
                "aggressive_expansion_scores",
                "coalition_pacts",
                "war_exhaustion_states",
            }
        ),
        phase=SystemPhase.DIPLOMACY + 1,
    )

    @property
    def id(self) -> str:
        return "base.diplomatic_balance"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.bootstrap", "base.advanced_diplomacy", "base.diplomacy"]

    def update(self, state: GameState, delta_time: float) -> None:
        expansion_events = (
            EventWarStarted,
            EventOccupationChanged,
            EventTerritoryOwnershipChanged,
            EventNewDay,
            EventWarEnded,
        )
        exhaustion_events = (
            EventNewDay,
            EventBattleEnded,
            EventBattleUpdated,
            EventOccupationChanged,
            EventWarEnded,
            EventWarStarted,
        )
        if any(isinstance(event, expansion_events) for event in state.events):
            self._update_expansion_pressure(state)
        if any(isinstance(event, exhaustion_events) for event in state.events):
            self._update_war_exhaustion(state)

    def _update_expansion_pressure(self, state: GameState) -> None:
        now = max(0, int(state.time.total_minutes))
        event_table = state.tables.get("aggressive_expansion_events")
        events = [] if event_table is None else event_table.to_dicts()
        events = [row for row in events if int(row.get("expires_at_minute") or 0) > now]
        known_ids = {str(row.get("id") or "") for row in events}
        wars = self._rows(state, "countries_wars")
        regions = self._rows(state, "regions")
        owner_by_region = {
            int(row.get("id") or 0): self._tag(row.get("owner")) for row in regions
        }

        for event in state.events:
            if isinstance(event, EventWarStarted):
                war = next((row for row in wars if str(row.get("id") or "") == event.war_id), {})
                cause = str(war.get("casus_belli") or "").strip().lower()
                if cause not in {"", "none", "unspecified", "unprovoked", "no casus belli"}:
                    continue
                self._record_expansion_event(
                    events,
                    known_ids,
                    self._tag(event.attacker_tag),
                    self._tag(event.defender_tag),
                    0,
                    "unprovoked_war",
                    0.35,
                    now,
                )
            elif isinstance(event, EventOccupationChanged):
                owner = owner_by_region.get(int(event.region_id), "")
                attacker = self._tag(event.controller)
                defender = self._tag(event.previous_controller)
                if not owner or owner != defender or attacker == owner:
                    continue
                # Either side can capture enemy territory; restricting the
                # signal to side A made equivalent side-B occupations invisible.
                offensive = any(
                    (
                        (
                            attacker in self._tags(war.get("side_a"))
                            and owner in self._tags(war.get("side_b"))
                        )
                        or (
                            attacker in self._tags(war.get("side_b"))
                            and owner in self._tags(war.get("side_a"))
                        )
                    )
                    and str(war.get("status") or "active").lower() == "active"
                    for war in wars
                )
                if offensive:
                    self._record_expansion_event(
                        events,
                        known_ids,
                        attacker,
                        owner,
                        int(event.region_id),
                        "offensive_occupation",
                        0.15,
                        now,
                    )
            elif isinstance(event, EventTerritoryOwnershipChanged):
                if event.source != "ActionAnnexRegion":
                    continue
                self._record_expansion_event(
                    events,
                    known_ids,
                    self._tag(event.owner),
                    self._tag(event.previous_owner),
                    int(event.region_id),
                    "territory_annexation",
                    0.25,
                    now,
                )

        country_ids = {self._tag(row.get("id")) for row in self._rows(state, "countries")}
        score_rows: list[dict[str, Any]] = []
        score_by_country: dict[str, float] = {}
        stats_by_country: dict[str, tuple[int, int]] = {}
        for country_id in sorted(country_ids):
            country_events = [row for row in events if self._tag(row.get("source_country_id")) == country_id]
            score = min(1.0, sum(self._finite(row.get("threat_delta")) for row in country_events))
            unprovoked = sum(row.get("event_type") == "unprovoked_war" for row in country_events)
            occupied = len(
                {
                    int(row.get("region_id") or 0)
                    for row in country_events
                    if row.get("event_type") == "offensive_occupation" and int(row.get("region_id") or 0) > 0
                }
            )
            score_by_country[country_id] = score
            stats_by_country[country_id] = (unprovoked, occupied)
            score_rows.append(
                {
                    "country_id": country_id,
                    "threat_score": score,
                    "unprovoked_wars_365d": unprovoked,
                    "occupied_regions_365d": occupied,
                    "updated_at_minute": now,
                }
            )

        score_schema = state.get_table("aggressive_expansion_scores").schema
        score_frame = pl.DataFrame(score_rows, schema=score_schema, strict=False)
        state.update_table("aggressive_expansion_events", self._frame(state, "aggressive_expansion_events", events))
        state.update_table("aggressive_expansion_scores", score_frame)
        self._publish_expansion_scores(state, score_by_country, stats_by_country, now)
        self._update_coalitions(state, score_by_country, now)

    def _record_expansion_event(
        self,
        events: list[dict[str, Any]],
        known_ids: set[str],
        source: str,
        target: str,
        region_id: int,
        event_type: str,
        threat_delta: float,
        now: int,
    ) -> None:
        if not source or source == target:
            return
        signature = f"{event_type}|{source}|{target}|{region_id}|{now}"
        event_id = "expansion-" + hashlib.sha256(signature.encode("utf-8")).hexdigest()[:20]
        if event_id in known_ids:
            return
        events.append(
            {
                "id": event_id,
                "source_country_id": source,
                "target_country_id": target,
                "region_id": max(0, int(region_id)),
                "event_type": event_type,
                "threat_delta": max(0.0, min(1.0, float(threat_delta))),
                "at_minute": now,
                "expires_at_minute": now + _EXPANSION_WINDOW,
            }
        )
        known_ids.add(event_id)

    def _publish_expansion_scores(
        self,
        state: GameState,
        score_by_country: dict[str, float],
        stats_by_country: dict[str, tuple[int, int]],
        now: int,
    ) -> None:
        countries = state.get_table("countries")
        rows = countries.to_dicts()
        changed = False
        for row in rows:
            country = self._tag(row.get("id"))
            score = score_by_country.get(country, 0.0)
            previous = self._finite(row.get("aggressive_expansion"))
            if previous != score:
                row["aggressive_expansion"] = score
                changed = True
            stats = stats_by_country.get(country, (0, 0))
            if previous != score:
                state.events.append(
                    EventAggressiveExpansionUpdated(
                        country,
                        score,
                        stats[0],
                        stats[1],
                        now,
                    )
                )
        if changed:
            state.update_table("countries", pl.DataFrame(rows, schema=countries.schema, strict=False))

    def _update_coalitions(
        self,
        state: GameState,
        score_by_country: dict[str, float],
        now: int,
    ) -> None:
        countries = self._rows(state, "countries")
        regions = self._rows(state, "regions")
        region_adjacency = self._rows(state, "region_adjacency")
        treaties = self._rows(state, "countries_treaties")
        wars = self._rows(state, "countries_wars")
        pact_frame = state.get_table("coalition_pacts")
        pacts = pact_frame.to_dicts()
        threshold = max(
            0.1,
            min(1.0, self._finite(state.globals.get("aggressive_expansion_coalition_threshold"), _COALITION_THRESHOLD)),
        )
        owner_by_region = {
            int(row.get("id") or 0): self._tag(row.get("owner")) for row in regions
        }
        neighbors: dict[str, set[str]] = {}
        for edge in region_adjacency:
            left = owner_by_region.get(int(edge.get("region_id") or 0), "")
            right = owner_by_region.get(int(edge.get("neighbor_region_id") or 0), "")
            if left and right and left != right:
                neighbors.setdefault(left, set()).add(right)
                neighbors.setdefault(right, set()).add(left)
        target_allies: dict[str, set[str]] = {}
        for treaty in treaties:
            if str(treaty.get("status") or "active").lower() != "active":
                continue
            if str(treaty.get("type") or "").strip().lower() != "alliance":
                continue
            members = self._tags(treaty.get("members"))
            for member in members:
                target_allies.setdefault(member, set()).update(members - {member})

        country_by_id = {self._tag(row.get("id")): row for row in countries}
        active_war_pairs: set[frozenset[str]] = set()
        active_war_participants: set[str] = set()
        for war in wars:
            if str(war.get("status") or "active").lower() != "active":
                continue
            side_a = self._tags(war.get("side_a"))
            side_b = self._tags(war.get("side_b"))
            active_war_participants.update(side_a | side_b)
            active_war_pairs.update(frozenset((left, right)) for left in side_a for right in side_b)
        occupied_controllers = {
            controller
            for region in regions
            if self._tag(region.get("owner")) != (controller := self._tag(region.get("controller")))
        }
        existing_by_target = {
            self._tag(row.get("primary_target_country_id")): row for row in pacts
        }
        for target, score in sorted(score_by_country.items()):
            existing = existing_by_target.get(target)
            candidates = {
                country
                for country in neighbors.get(target, set())
                if country in country_by_id
                and country != target
                and country not in target_allies.get(target, set())
                and frozenset((country, target)) not in active_war_pairs
            }
            existing_active = existing is not None and str(existing.get("status") or "").lower() == "active"
            existing_members = (
                self._tags(existing.get("member_country_ids")) if existing_active else set()
            )
            candidates |= {
                country
                for country in existing_members
                if country in country_by_id and country not in target_allies.get(target, set())
            }
            active_wars = target in active_war_participants
            current_occupations = target in occupied_controllers
            collapsed = int(country_by_id.get(target, {}).get("military_count") or 0) <= 0
            threat_ended = not active_wars and not current_occupations
            should_dissolve = existing_active and (threat_ended or collapsed)
            should_form = score >= threshold and candidates and not should_dissolve

            if should_form:
                members = sorted(candidates)
                self._set_pact(
                    state,
                    pacts,
                    existing,
                    target,
                    members,
                    score,
                    now,
                    "Formed in response to elevated expansion pressure among neighboring states.",
                )
            elif should_dissolve and existing is not None:
                existing.update(
                    status="dissolved",
                    updated_at_minute=now,
                    dissolved_at_minute=now,
                    reason="The primary threat collapsed or no longer controls territory outside its borders.",
                )
                self._emit_pact_event(state, existing, now)
            elif existing_active and (active_wars or current_occupations):
                if self._finite(existing.get("threat_score")) != score:
                    existing["threat_score"] = score
                    existing["updated_at_minute"] = now
                    self._emit_pact_event(state, existing, now)

        state.update_table("coalition_pacts", pl.DataFrame(pacts, schema=pact_frame.schema, strict=False))
        self._publish_coalition_memberships(state, pacts)

    def _publish_coalition_memberships(
        self,
        state: GameState,
        pacts: list[dict[str, Any]],
    ) -> None:
        member_counts: dict[str, int] = {}
        for pact in pacts:
            if str(pact.get("status") or "").lower() != "active":
                continue
            for member in self._tags(pact.get("member_country_ids")):
                member_counts[member] = member_counts.get(member, 0) + 1
        countries = state.get_table("countries")
        rows = countries.to_dicts()
        changed = False
        for row in rows:
            count = member_counts.get(self._tag(row.get("id")), 0)
            if int(row.get("coalition_membership_count") or 0) != count:
                row["coalition_membership_count"] = count
                changed = True
        if changed:
            state.update_table("countries", pl.DataFrame(rows, schema=countries.schema, strict=False))

    def _set_pact(
        self,
        state: GameState,
        pacts: list[dict[str, Any]],
        existing: dict[str, Any] | None,
        target: str,
        members: list[str],
        score: float,
        now: int,
        reason: str,
    ) -> None:
        pact_id = f"coalition-{target}"
        if existing is not None:
            changed = (
                str(existing.get("status") or "").lower() != "active"
                or
                self._tags(existing.get("member_country_ids")) != set(members)
                or self._finite(existing.get("threat_score")) != score
                or self._tag(existing.get("leader_country_id")) != members[0]
            )
            if not changed:
                return
            existing.update(
                leader_country_id=members[0],
                member_country_ids=members,
                threat_score=score,
                status="active",
                updated_at_minute=now,
                dissolved_at_minute=0,
                reason=reason,
            )
            self._emit_pact_event(state, existing, now)
            return
        pact = {
            "id": pact_id,
            "leader_country_id": members[0],
            "member_country_ids": members,
            "primary_target_country_id": target,
            "mutual_defense": True,
            "threat_score": score,
            "status": "active",
            "formed_at_minute": now,
            "updated_at_minute": now,
            "dissolved_at_minute": 0,
            "reason": reason,
        }
        pacts.append(pact)
        self._emit_pact_event(state, pact, now)

    def _emit_pact_event(self, state: GameState, pact: dict[str, Any], now: int) -> None:
        state.events.append(
            EventCoalitionChanged(
                str(pact.get("id") or ""),
                self._tag(pact.get("primary_target_country_id")),
                tuple(sorted(self._tags(pact.get("member_country_ids")))),
                str(pact.get("status") or ""),
                self._finite(pact.get("threat_score")),
                now,
            )
        )

    def _update_war_exhaustion(self, state: GameState) -> None:
        now = max(0, int(state.time.total_minutes))
        countries = state.get_table("countries")
        country_rows = countries.to_dicts()
        country_by_id = {self._tag(row.get("id")): row for row in country_rows}
        wars = [row for row in self._rows(state, "countries_wars") if str(row.get("status") or "active").lower() == "active"]
        battle_to_war = {
            str(row.get("id") or ""): str(row.get("war_id") or "")
            for row in self._rows(state, "battles")
        }
        casualties_by_war_country: dict[tuple[str, str], int] = {}
        for casualty in self._rows(state, "battle_casualty_records"):
            war_id = battle_to_war.get(str(casualty.get("battle_id") or ""), "")
            key = (war_id, self._tag(casualty.get("country_id")))
            casualties_by_war_country[key] = casualties_by_war_country.get(key, 0) + max(0, int(casualty.get("losses") or 0))

        previous = self._rows(state, "war_exhaustion_states")
        previous_by_key = {
            (str(row.get("war_id") or ""), self._tag(row.get("country_id"))): row for row in previous
        }
        regions = self._rows(state, "regions")
        occupied_by_owner = self._occupied_region_counts(regions)
        blockades = self._rows(state, "naval_blockades")
        blockade_by_country: dict[str, float] = {}
        for row in blockades:
            if str(row.get("status") or "active").lower() != "active":
                continue
            if int(row.get("expires_at_minute") or 0) not in (0,) and int(row.get("expires_at_minute") or 0) <= now:
                continue
            target = self._tag(row.get("target_country_id"))
            blockade_by_country[target] = min(
                100.0,
                blockade_by_country.get(target, 0.0) + max(0.0, min(100.0, self._finite(row.get("blockade_percentage")))),
            )

        exhaustion_rows: list[dict[str, Any]] = []
        penalty_by_country: dict[str, float] = {}
        stability_by_country: dict[str, float] = {}
        war_count_by_country: dict[str, int] = {}
        for war in sorted(wars, key=lambda row: str(row.get("id") or "")):
            war_id = str(war.get("id") or "")
            side_a, side_b = self._tags(war.get("side_a")), self._tags(war.get("side_b"))
            participants = side_a | side_b
            days = self._war_days(war, now)
            for country in sorted(participants):
                country_row = country_by_id.get(country)
                if country_row is None:
                    continue
                war_count_by_country[country] = war_count_by_country.get(country, 0) + 1
                enemies = side_b if country in side_a else side_a
                casualties = casualties_by_war_country.get((war_id, country), 0)
                force = max(0, int(country_row.get("military_count") or 0))
                casualty_score = min(40.0, casualties / max(1, force + casualties) * 40.0)
                occupied = sum(
                    occupied_by_owner.get(country, {}).get(enemy, 0)
                    for enemy in enemies
                )
                occupation_score = min(20.0, occupied * 4.0)
                blockade = blockade_by_country.get(country, 0.0)
                blockade_score = min(20.0, blockade * 0.2)
                duration_score = min(20.0, days / 365.0 * 20.0)
                exhaustion = min(100.0, casualty_score + occupation_score + blockade_score + duration_score)
                key = (war_id, country)
                prior = previous_by_key.get(key, {})
                prior_index = self._finite(prior.get("exhaustion_index"))
                elapsed_days = max(1.0, (now - int(prior.get("updated_at_minute") or now)) / 1440.0)
                rate = (exhaustion - prior_index) / elapsed_days
                stability_penalty = min(12.0, exhaustion * 0.12)
                peace_desire = exhaustion / 100.0
                efficiency_penalty = min(0.35, exhaustion * 0.0035)
                exhaustion_rows.append(
                    {
                        "id": f"war-exhaustion-{war_id}-{country}",
                        "war_id": war_id,
                        "country_id": country,
                        "exhaustion_index": exhaustion,
                        "accumulation_rate": rate,
                        "stability_penalty": stability_penalty,
                        "peace_desire": peace_desire,
                        "military_efficiency_penalty": efficiency_penalty,
                        "casualties": casualties,
                        "occupied_regions": occupied,
                        "blockade_percentage": blockade,
                        "conflict_days": days,
                        "updated_at_minute": now,
                    }
                )
                penalty_by_country[country] = max(penalty_by_country.get(country, 0.0), efficiency_penalty)
                stability_by_country[country] = max(stability_by_country.get(country, 0.0), stability_penalty)
                if abs(exhaustion - prior_index) >= 0.01 or not prior:
                    state.events.append(EventWarExhaustionUpdated(war_id, country, exhaustion, peace_desire, now))

        exhaustion_table = state.get_table("war_exhaustion_states")
        state.update_table(
            "war_exhaustion_states",
            pl.DataFrame(exhaustion_rows, schema=exhaustion_table.schema, strict=False),
        )
        country_changed = False
        for row in country_rows:
            country = self._tag(row.get("id"))
            latest = [item for item in exhaustion_rows if item["country_id"] == country]
            current = max((float(item["exhaustion_index"]) for item in latest), default=0.0)
            efficiency = penalty_by_country.get(country, 0.0)
            stability = stability_by_country.get(country, 0.0)
            for field, value in (
                ("war_exhaustion", current),
                ("war_exhaustion_efficiency_penalty", efficiency),
                ("war_exhaustion_stability_penalty", stability),
                ("active_war_count", war_count_by_country.get(country, 0)),
            ):
                if self._finite(row.get(field)) != value:
                    row[field] = value
                    country_changed = True
        if country_changed:
            state.update_table("countries", pl.DataFrame(country_rows, schema=countries.schema, strict=False))

        units = state.tables.get("units")
        if units is not None and "owner" in units.columns:
            unit_rows = units.to_dicts()
            changed = False
            for unit in unit_rows:
                modifier = max(0.65, 1.0 - penalty_by_country.get(self._tag(unit.get("owner")), 0.0))
                if self._finite(unit.get("war_exhaustion_modifier"), 1.0) != modifier:
                    unit["war_exhaustion_modifier"] = modifier
                    changed = True
            if changed:
                state.update_table("units", pl.DataFrame(unit_rows, schema=units.schema, strict=False))

    @classmethod
    def _occupied_region_counts(
        cls, regions: list[dict[str, Any]]
    ) -> dict[str, dict[str, int]]:
        """Index regional occupation once for all war participants."""
        counts: dict[str, dict[str, int]] = {}
        for region in regions:
            owner = cls._tag(region.get("owner"))
            controller = cls._tag(region.get("controller"))
            if owner and controller:
                by_controller = counts.setdefault(owner, {})
                by_controller[controller] = by_controller.get(controller, 0) + 1
        return counts

    def _war_days(self, war: dict[str, Any], now: int) -> int:
        raw = str(war.get("created_at") or "").strip()
        try:
            created = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return 0
        if created.tzinfo is not None:
            created = created.replace(tzinfo=None)
        elapsed_minutes = max(
            0,
            int((GAME_EPOCH + timedelta(minutes=now) - created).total_seconds() // 60),
        )
        return elapsed_minutes // 1440

    @staticmethod
    def _frame(state: GameState, table: str, rows: list[dict[str, Any]]) -> pl.DataFrame:
        return pl.DataFrame(rows, schema=state.get_table(table).schema, strict=False)

    @staticmethod
    def _rows(state: GameState, table: str) -> list[dict[str, Any]]:
        frame = state.tables.get(table)
        return [] if frame is None else frame.to_dicts()

    @staticmethod
    def _finite(value: Any, fallback: float = 0.0) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError):
            return fallback
        return result if result == result and abs(result) != float("inf") else fallback

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
