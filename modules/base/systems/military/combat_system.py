from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import polars as pl

from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_HELPER
from src.shared.events import EventBattleEnded, EventBattleParticipantRejected, EventBattleStarted, EventBattleUpdated, EventNewHour
from src.shared.actions import ActionAttackUnit, ActionMoveUnit
from src.shared.state import GameState
from modules.base.systems.military.alliance_policy import AlliancePolicy
from modules.base.systems.military.readiness_policy import ReadinessPolicy
from modules.base.systems.military.readiness_system import cancel_readiness_for_contact


BATTLE_TABLE = "battles"
BATTLE_UNITS_TABLE = "battle_units"
COUNTRIES_WARS_TABLE = "countries_wars"
REGIONS_TABLE = "regions"
UNITS_TABLE = "units"
UNCLAIMED_TAGS = {"", "None"}

BATTLE_SCHEMA: dict[str, pl.DataType] = {
    "id": pl.Utf8,
    "war_id": pl.Utf8,
    "region_id": pl.Int32,
    "attacker_side": pl.Utf8,
    "mode": pl.Utf8,
    "defender_side": pl.Utf8,
    "balance": pl.Float64,
    "side_a_strength": pl.Float64,
    "side_b_strength": pl.Float64,
    "side_a_losses": pl.Int64,
    "side_b_losses": pl.Int64,
    "round": pl.Int32,
    "started_at_minute": pl.Int64,
    "updated_at_minute": pl.Int64,
    "concluded_at_minute": pl.Int64,
    "victor_side": pl.Utf8,
    "status": pl.Utf8,
}

BATTLE_UNITS_SCHEMA: dict[str, pl.DataType] = {
    "battle_id": pl.Utf8,
    "unit_id": pl.Utf8,
    "country_id": pl.Utf8,
    "side": pl.Utf8,
    "role": pl.Utf8,
    "readiness_status": pl.Utf8,
    "contribution_weight": pl.Float64,
    "effective_strength": pl.Float64,
    "strength_share": pl.Float64,
}

BATTLE_PARTICIPANTS_SCHEMA: dict[str, pl.DataType] = {
    "battle_id": pl.Utf8,
    "country_id": pl.Utf8,
    "side": pl.Utf8,
    "role": pl.Utf8,
    "eligibility_basis": pl.Utf8,
    "unit_count": pl.Int32,
    "weighted_strength": pl.Float64,
}

OCCUPATION_SCHEMA: dict[str, pl.DataType] = {
    "region_id": pl.Int32,
    "controller_country_id": pl.Utf8,
    "garrison_strength": pl.Int64,
    "resistance": pl.Float64,
    "occupation_status": pl.Utf8,
    "started_at_minute": pl.Int64,
    "updated_at_minute": pl.Int64,
    "contested": pl.Boolean,
}

UNIT_REQUIRED_COLUMNS: dict[str, tuple[pl.DataType, Any]] = {
    "id": (pl.Utf8, ""),
    "owner": (pl.Utf8, ""),
    "strength": (pl.Int64, 0),
    "engagement_mode": (pl.Utf8, ""),
    "current_region_id": (pl.Int32, 0),
    "is_moving": (pl.Boolean, False),
    "readiness_status": (pl.Utf8, "ready"),
}


@dataclass(frozen=True, slots=True)
class WarRecord:
    war_id: str
    side_a: frozenset[str]
    side_b: frozenset[str]
    status: str


@dataclass(frozen=True, slots=True)
class ConflictContext:
    war_id: str
    side_a_members: frozenset[str]
    side_b_members: frozenset[str]
    side_a_tags: frozenset[str]
    side_b_tags: frozenset[str]
    roles: dict[str, str] | None = None
    bases: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class CombatOutcome:
    attacker_losses: int
    defender_losses: int


class WarIndex:
    """Resolves active wartime relationships without coupling combat to table shape."""

    def __init__(self, active_wars: list[WarRecord]):
        self._active_wars = active_wars

    @classmethod
    def from_table(cls, wars: pl.DataFrame | None) -> "WarIndex":
        if wars is None or wars.is_empty():
            return cls([])

        records: list[WarRecord] = []
        for index, row in enumerate(wars.to_dicts(), start=1):
            status = str(row.get("status") or "active").lower()
            if status not in {"active", "ongoing", ""}:
                continue

            side_a = cls._normalize_side(row.get("side_a"))
            side_b = cls._normalize_side(row.get("side_b"))
            if not side_a or not side_b:
                continue

            records.append(
                WarRecord(
                    war_id=str(row.get("id") or f"war-{index:03d}"),
                    side_a=frozenset(side_a),
                    side_b=frozenset(side_b),
                    status=status or "active",
                )
            )

        return cls(sorted(records, key=lambda record: record.war_id))

    def active_battle_for_region(self, owners: set[str]) -> ConflictContext | None:
        for war in self._active_wars:
            present_a = frozenset(tag for tag in owners if tag in war.side_a)
            present_b = frozenset(tag for tag in owners if tag in war.side_b)
            if present_a and present_b:
                return ConflictContext(
                    war_id=war.war_id,
                    side_a_members=war.side_a,
                    side_b_members=war.side_b,
                    side_a_tags=present_a,
                    side_b_tags=present_b,
                )
        return None

    def is_hostile(self, left: str | None, right: str | None) -> bool:
        if not left or not right or left == right:
            return False

        for war in self._active_wars:
            if (left in war.side_a and right in war.side_b) or (left in war.side_b and right in war.side_a):
                return True
        return False

    @staticmethod
    def _normalize_side(value: Any) -> set[str]:
        if value is None:
            return set()
        if isinstance(value, list):
            return {str(tag).strip().upper() for tag in value if str(tag).strip()}
        if isinstance(value, tuple):
            return {str(tag).strip().upper() for tag in value if str(tag).strip()}
        if isinstance(value, str):
            return {tag.strip().upper() for tag in value.split(",") if tag.strip()}
        return set()


class CombatResolutionPolicy:
    """Keeps combat deterministic and easy to tune independently from system flow."""

    def resolve(self, attacker_strength: int, defender_strength: int, mode: str = "positional") -> CombatOutcome:
        if attacker_strength <= 0 or defender_strength <= 0:
            return CombatOutcome(0, 0)

        intensity = 1.35 if mode == "assault" else 1.0
        stronger = max(attacker_strength, defender_strength)
        weaker = min(attacker_strength, defender_strength)
        if weaker > 0 and stronger / weaker >= 2.5:
            if attacker_strength >= defender_strength:
                return CombatOutcome(
                    attacker_losses=max(1, int(round(attacker_strength * 0.08 * intensity))),
                    defender_losses=defender_strength,
                )
            return CombatOutcome(
                attacker_losses=attacker_strength,
                defender_losses=max(1, int(round(defender_strength * 0.08 * intensity))),
            )

        total = attacker_strength + defender_strength
        attacker_share = attacker_strength / total
        defender_share = defender_strength / total

        attacker_losses = max(1, int(round(attacker_strength * (0.10 + (defender_share * 0.18)) * intensity)))
        defender_losses = max(1, int(round(defender_strength * (0.12 + (attacker_share * 0.22)) * intensity)))
        return CombatOutcome(attacker_losses=attacker_losses, defender_losses=defender_losses)


class CombatSystem(ISystem):
    access = SystemAccess(
        reads=frozenset({'countries', 'regions', 'units', 'countries_wars', 'countries_treaties', 'battles', 'unit_readiness_transitions'}),
        writes=frozenset({'regions', 'units', 'battles', 'battle_units', 'battle_participants', 'occupations'}),
        handles=frozenset({ActionAttackUnit, ActionMoveUnit}),
        phase=SystemPhase.COMBAT,
    )
    runtime_state_contract = {
        "_policy": SYSTEM_STATE_HELPER,
        "_readiness": SYSTEM_STATE_HELPER,
        "_alliances": SYSTEM_STATE_HELPER,
    }

    def __init__(self):
        self._policy = CombatResolutionPolicy()
        self._readiness = ReadinessPolicy()
        self._alliances = AlliancePolicy()

    @property
    def id(self) -> str:
        return "base.combat"

    @property
    def dependencies(self) -> list[str]:
        return ["base.military", "base.diplomacy"]

    def update(self, state: GameState, delta_time: float) -> None:
        if REGIONS_TABLE not in state.tables or UNITS_TABLE not in state.tables:
            self._reset_battle_tables(state)
            return

        regions = self._ensure_regions_table(state.get_table(REGIONS_TABLE))
        units = self._ensure_units_table(state.get_table(UNITS_TABLE))
        wars = WarIndex.from_table(state.tables.get(COUNTRIES_WARS_TABLE))
        existing_battles = self._existing_active_battle_ids(state.tables.get(BATTLE_TABLE))
        should_resolve = (not state.time.is_paused) and any(isinstance(event, EventNewHour) for event in state.events)
        assaulting_unit_ids = {
            action.attacker_unit_id if isinstance(action, ActionAttackUnit) else action.unit_id
            for action in state.current_actions
            if isinstance(action, (ActionAttackUnit, ActionMoveUnit))
        }

        unit_rows = units.to_dicts()
        stationary_units = self._stationary_units_by_region(unit_rows)
        relevant_region_ids = sorted(stationary_units)
        region_rows = (
            regions.filter(pl.col("id").is_in(relevant_region_ids)).to_dicts()
            if relevant_region_ids
            else []
        )
        original_controllers = {
            int(row.get("id") or 0): str(row.get("controller") or "")
            for row in region_rows
        }

        battle_rows: list[dict[str, Any]] = []
        battle_unit_rows: list[dict[str, Any]] = []
        participant_rows: list[dict[str, Any]] = []
        occupation_rows: list[dict[str, Any]] = []
        existing_occupations = state.tables.get("occupations")
        if existing_occupations is not None and not existing_occupations.is_empty():
            occupation_rows = existing_occupations.to_dicts()
        active_battle_ids: set[str] = set()
        victorious_battles: dict[str, str] = {}
        victorious_sides: dict[str, str] = {}
        battle_regions: dict[str, int] = {}
        battle_metadata: dict[str, dict[str, Any]] = {}

        regions_by_id = {
            int(row.get("id") or 0): row
            for row in region_rows
            if int(row.get("id") or 0) > 0
        }
        def battle_iteration_key(region_id: int) -> tuple[int, str, int]:
            owners = {
                self._clean_tag(row.get("owner"))
                for row in stationary_units[region_id]
                if self._clean_tag(row.get("owner"))
            }
            conflict = wars.active_battle_for_region(owners)
            if conflict is not None:
                return (0, self._battle_id(region_id, conflict.war_id), region_id)
            return (1, f"region-{region_id:010d}", region_id)

        # Stable battle-ID ordering keeps multi-region event sequences replayable
        # even when numeric region IDs do not share the same lexical order.
        for region_id in sorted(stationary_units, key=battle_iteration_key):
            region_row = regions_by_id.get(region_id)
            if region_row is None:
                continue
            local_units = stationary_units[region_id]

            present_owners = {self._clean_tag(row.get("owner")) for row in local_units if self._clean_tag(row.get("owner"))}
            if not present_owners:
                continue

            conflict = wars.active_battle_for_region(present_owners)
            if conflict is not None:
                for occupation in occupation_rows:
                    if int(occupation.get("region_id") or 0) == region_id:
                        if not bool(occupation.get("contested")) or str(occupation.get("occupation_status")) != "contested":
                            occupation["contested"] = True
                            occupation["occupation_status"] = "contested"
                            occupation["updated_at_minute"] = int(state.time.total_minutes)
                eligibility = self._alliances.expand(
                    next(war for war in wars._active_wars if war.war_id == conflict.war_id),
                    local_units,
                    state.tables.get("countries_treaties"),
                )
                conflict = ConflictContext(
                    war_id=conflict.war_id,
                    side_a_members=eligibility.side_a,
                    side_b_members=eligibility.side_b,
                    side_a_tags=frozenset(tag for tag in present_owners if tag in eligibility.side_a),
                    side_b_tags=frozenset(tag for tag in present_owners if tag in eligibility.side_b),
                    roles=eligibility.roles,
                    bases=eligibility.bases,
                )
                for country_id, reason in eligibility.rejected:
                    state.events.append(EventBattleParticipantRejected(
                        battle_id=self._battle_id(region_id, conflict.war_id),
                        country_id=country_id,
                        reason=reason,
                        at_minute=int(state.time.total_minutes),
                    ))
                battle_mode = self._battle_mode(local_units)
                battle_id = self._battle_id(region_id, conflict.war_id)
                battle_regions[battle_id] = region_id
                active_battle_ids.add(battle_id)
                if battle_id not in existing_battles:
                    state.events.append(EventBattleStarted(
                        battle_id=battle_id,
                        region_id=region_id,
                        war_id=conflict.war_id,
                        side_a_countries=tuple(sorted(conflict.side_a_members)),
                        side_b_countries=tuple(sorted(conflict.side_b_members)),
                        started_at_minute=int(state.time.total_minutes),
                    ))

                # Contact and explicit assaults interrupt a readiness change
                # before the same tick can complete it.
                contact_ids = [str(row.get("id") or "") for row in local_units if str(row.get("engagement_mode") or "").lower() in {"assault", "positional"}]
                if contact_ids:
                    cancel_readiness_for_contact(state, contact_ids)
                    for unit in local_units:
                        if str(unit.get("id") or "") in contact_ids:
                            unit["readiness_transition_id"] = ""
                            unit["readiness_progress"] = 0.0
                            unit["readiness_eta_minute"] = 0

                prior_row = self._battle_row(state.tables.get(BATTLE_TABLE), battle_id)
                previous_a = self._total_strength(local_units, conflict.side_a_members)
                previous_b = self._total_strength(local_units, conflict.side_b_members)
                battle_metadata[battle_id] = {
                    "war_id": conflict.war_id,
                    "mode": battle_mode,
                    "side_a_tags": conflict.side_a_tags,
                    "side_b_tags": conflict.side_b_tags,
                    "prior_row": prior_row,
                    "previous_a": previous_a,
                    "previous_b": previous_b,
                    "round_resolved": False,
                }

                resolve_this_tick = should_resolve or (
                    battle_mode == "assault"
                    and any(str(row.get("id") or "") in assaulting_unit_ids for row in local_units)
                )
                if resolve_this_tick:
                    battle_metadata[battle_id]["round_resolved"] = True
                    victor = self._apply_combat_round(local_units, conflict, battle_mode)
                    if victor is not None:
                        victorious_battles[battle_id] = victor
                        victorious_sides[battle_id] = "SIDE_A" if victor in conflict.side_a_members else "SIDE_B"
                    post_a = self._total_strength(local_units, conflict.side_a_members)
                    post_b = self._total_strength(local_units, conflict.side_b_members)
                    if post_a <= 0 and post_b <= 0:
                        victorious_battles[battle_id] = ""
                        victorious_sides[battle_id] = ""

                side_a_strength = self._total_strength(local_units, conflict.side_a_members)
                side_b_strength = self._total_strength(local_units, conflict.side_b_members)
                battle_metadata[battle_id]["side_a_strength"] = side_a_strength
                battle_metadata[battle_id]["side_b_strength"] = side_b_strength
                if side_a_strength > 0 and side_b_strength > 0:
                    status = self._lifecycle_status(
                        prior_row,
                        resolve_this_tick,
                        previous_a,
                        previous_b,
                        side_a_strength,
                        side_b_strength,
                    )
                    round_number = int(prior_row.get("round") or 0) + (1 if resolve_this_tick else 0)
                    current_balance = float(side_a_strength / max(1, side_a_strength + side_b_strength))
                    battle_changed = (
                        not prior_row
                        or resolve_this_tick
                        or str(prior_row.get("status") or "active") != status
                        or str(prior_row.get("mode") or "") != battle_mode
                        or str(prior_row.get("attacker_side") or "") != ",".join(sorted(conflict.side_a_tags))
                        or str(prior_row.get("defender_side") or "") != ",".join(sorted(conflict.side_b_tags))
                        or float(prior_row.get("side_a_strength") or -1.0) != float(side_a_strength)
                        or float(prior_row.get("side_b_strength") or -1.0) != float(side_b_strength)
                        or float(prior_row.get("balance") or -1.0) != current_balance
                        or self._battle_units_changed(state.tables.get(BATTLE_UNITS_TABLE), battle_id, local_units, conflict)
                    )
                    if battle_changed:
                        battle_row = self._build_battle_row(
                            battle_id=battle_id,
                            mode=battle_mode,
                            region_id=region_id,
                            side_a_tags=conflict.side_a_tags,
                            side_b_tags=conflict.side_b_tags,
                            side_a_strength=side_a_strength,
                            side_b_strength=side_b_strength,
                            war_id=conflict.war_id,
                            now=int(state.time.total_minutes),
                            side_a_losses=int(prior_row.get("side_a_losses") or 0) + (max(0, previous_a - side_a_strength) if resolve_this_tick else 0),
                            side_b_losses=int(prior_row.get("side_b_losses") or 0) + (max(0, previous_b - side_b_strength) if resolve_this_tick else 0),
                            status=status,
                            round_number=round_number,
                            prior_row=prior_row,
                        )
                    else:
                        battle_row = prior_row
                    battle_rows.append(battle_row)
                    battle_unit_rows.extend(
                        self._build_battle_units(
                            battle_id=battle_id,
                            local_units=local_units,
                            conflict=conflict,
                            total_strength=side_a_strength + side_b_strength,
                        )
                    )
                    participant_rows.extend(self._build_participants(
                        battle_id, local_units, conflict,
                    ))
                    if battle_changed or float(prior_row.get("balance") or -1.0) != current_balance:
                        state.events.append(EventBattleUpdated(
                            battle_id=battle_id,
                            region_id=region_id,
                            status=status,
                            round=round_number,
                            side_a_countries=tuple(sorted(conflict.side_a_members)),
                            side_b_countries=tuple(sorted(conflict.side_b_members)),
                            side_a_strength=float(side_a_strength),
                            side_b_strength=float(side_b_strength),
                            balance=current_balance,
                            updated_at_minute=int(state.time.total_minutes),
                        ))
                else:
                    winner = self._winning_country(local_units, conflict)
                    if winner:
                        victorious_battles[battle_id] = winner
                        victorious_sides[battle_id] = "SIDE_A" if winner in conflict.side_a_members else "SIDE_B"
            else:
                for unit in local_units:
                    unit["engagement_mode"] = ""
                occupier = self._occupation_candidate(
                    local_units=local_units,
                    current_controller=self._clean_tag(region_row.get("controller")),
                    wars=wars,
                )
                if occupier is not None:
                    region_row["controller"] = occupier
                    previous_occupation = next(
                        (
                            row
                            for row in occupation_rows
                            if int(row.get("region_id") or 0) == region_id
                        ),
                        None,
                    )
                    updated_occupation = self._occupation_row(
                        region_id,
                        occupier,
                        local_units,
                        int(state.time.total_minutes),
                        previous_occupation,
                    )
                    occupation_rows = [row for row in occupation_rows if int(row.get("region_id") or 0) != region_id]
                    occupation_rows.append(updated_occupation)

        # Apply battle outcomes after the scan so a resolved battle does not emit both
        # an active row and an end event for the same tick.
        for battle_id, victor in victorious_battles.items():
            if battle_id in active_battle_ids:
                active_battle_ids.remove(battle_id)
            region_id = battle_regions.get(battle_id, int(battle_id.split("-")[2]))
            prior_row = self._battle_row(state.tables.get(BATTLE_TABLE), battle_id)
            concluded_row = dict(prior_row)
            if not concluded_row:
                metadata = battle_metadata.get(battle_id, {})
                side_a_strength = int(metadata.get("side_a_strength", 0))
                side_b_strength = int(metadata.get("side_b_strength", 0))
                previous_a = int(metadata.get("previous_a", 0))
                previous_b = int(metadata.get("previous_b", 0))
                round_number = 1 if bool(metadata.get("round_resolved")) else 0
                concluded_row = self._build_battle_row(
                    battle_id=battle_id,
                    mode=str(metadata.get("mode") or "positional"),
                    region_id=region_id,
                    side_a_tags=frozenset(metadata.get("side_a_tags") or ()),
                    side_b_tags=frozenset(metadata.get("side_b_tags") or ()),
                    side_a_strength=side_a_strength,
                    side_b_strength=side_b_strength,
                    war_id=str(metadata.get("war_id") or ""),
                    now=int(state.time.total_minutes),
                    side_a_losses=max(0, previous_a - side_a_strength) if bool(metadata.get("round_resolved")) else 0,
                    side_b_losses=max(0, previous_b - side_b_strength) if bool(metadata.get("round_resolved")) else 0,
                    status="concluded",
                    round_number=round_number,
                )
            else:
                metadata = battle_metadata.get(battle_id, {})
                if bool(metadata.get("round_resolved")):
                    current_a = int(metadata.get("side_a_strength", concluded_row.get("side_a_strength") or 0))
                    current_b = int(metadata.get("side_b_strength", concluded_row.get("side_b_strength") or 0))
                    previous_a = int(metadata.get("previous_a", current_a))
                    previous_b = int(metadata.get("previous_b", current_b))
                    concluded_row["side_a_strength"] = float(current_a)
                    concluded_row["side_b_strength"] = float(current_b)
                    concluded_row["balance"] = float(current_a / max(1, current_a + current_b))
                    concluded_row["side_a_losses"] = int(concluded_row.get("side_a_losses") or 0) + max(0, previous_a - current_a)
                    concluded_row["side_b_losses"] = int(concluded_row.get("side_b_losses") or 0) + max(0, previous_b - current_b)
                    concluded_row["round"] = int(concluded_row.get("round") or 0) + 1
            concluded_row["status"] = "concluded"
            concluded_row["updated_at_minute"] = int(state.time.total_minutes)
            concluded_row["concluded_at_minute"] = int(state.time.total_minutes)
            concluded_row["victor_side"] = victorious_sides.get(battle_id, "")
            battle_rows.append(concluded_row)
            state.events.append(EventBattleEnded(
                battle_id=battle_id,
                victor_tag=victor,
                victor_side=victorious_sides.get(battle_id, ""),
                region_id=region_id,
                concluded_at_minute=int(state.time.total_minutes),
            ))
            if victor:
                self._set_region_controller(region_rows, region_id, victor)
                victor_tag = self._clean_tag(victor)
                garrison_units = [
                    row
                    for row in unit_rows
                    if int(row.get("current_region_id") or 0) == region_id
                    and self._clean_tag(row.get("owner")) == victor_tag
                    and int(row.get("strength") or 0) > 0
                    and not bool(row.get("is_moving"))
                ]
                previous_occupation = next(
                    (row for row in occupation_rows if int(row.get("region_id") or 0) == region_id),
                    None,
                )
                occupation_rows = [
                    row for row in occupation_rows if int(row.get("region_id") or 0) != region_id
                ]
                occupation_rows.append(
                    self._occupation_row(
                        region_id,
                        victor_tag,
                        garrison_units,
                        int(state.time.total_minutes),
                        previous_occupation,
                    )
                )
            else:
                for occupation in occupation_rows:
                    if int(occupation.get("region_id") or 0) == region_id:
                        occupation["contested"] = True
                        occupation["occupation_status"] = "contested"
                        occupation["updated_at_minute"] = int(state.time.total_minutes)

        unit_rows = [row for row in unit_rows if int(row.get("strength") or 0) > 0]
        self._update_table_if_changed(state, UNITS_TABLE, self._frame_from_rows(units.schema, unit_rows))
        controller_updates = {
            int(row.get("id") or 0): str(row.get("controller") or "")
            for row in region_rows
            if str(row.get("controller") or "")
            != original_controllers.get(int(row.get("id") or 0), "")
        }
        updated_regions = regions
        if controller_updates:
            all_region_rows = regions.to_dicts()
            for region_id, controller in controller_updates.items():
                self._set_region_controller(all_region_rows, region_id, controller)
            updated_regions = self._frame_from_rows(regions.schema, all_region_rows)
        self._update_table_if_changed(state, REGIONS_TABLE, updated_regions)
        self._update_table_if_changed(state, BATTLE_TABLE, self._frame_from_rows(BATTLE_SCHEMA, battle_rows))
        self._update_table_if_changed(state, BATTLE_UNITS_TABLE, self._frame_from_rows(BATTLE_UNITS_SCHEMA, battle_unit_rows))
        self._update_table_if_changed(
            state,
            "battle_participants",
            self._frame_from_rows(BATTLE_PARTICIPANTS_SCHEMA, participant_rows),
        )
        self._update_table_if_changed(
            state,
            "occupations",
            self._frame_from_rows(OCCUPATION_SCHEMA, occupation_rows),
        )

        if "countries" in state.tables:
            self._update_table_if_changed(
                state,
                "countries",
                self._sync_country_strengths(state.get_table("countries"), unit_rows),
            )

    def _ensure_regions_table(self, regions: pl.DataFrame) -> pl.DataFrame:
        if "controller" not in regions.columns:
            return regions.with_columns(pl.col("owner").alias("controller"))
        return regions

    def _ensure_units_table(self, units: pl.DataFrame) -> pl.DataFrame:
        for column, (_, default_value) in UNIT_REQUIRED_COLUMNS.items():
            if column not in units.columns:
                units = units.with_columns(pl.lit(default_value).alias(column))

        casted_columns = []
        for column, (dtype, _) in UNIT_REQUIRED_COLUMNS.items():
            casted_columns.append(pl.col(column).cast(dtype).alias(column))

        return units.with_columns(casted_columns)

    def _stationary_units_by_region(self, unit_rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in sorted(unit_rows, key=lambda unit: str(unit.get("id") or "")):
            if bool(row.get("is_moving", False)):
                continue
            region_id = int(row.get("current_region_id") or 0)
            if region_id <= 0:
                continue
            grouped.setdefault(region_id, []).append(row)
        return grouped

    def engagement_anchor_region(self, contact_units: Iterable[dict[str, Any]]) -> int:
        """Return the deterministic region anchor for an engagement contact."""
        candidates = sorted(
            (
                int(row.get("current_region_id") or 0),
                str(row.get("id") or ""),
            )
            for row in contact_units
            if int(row.get("current_region_id") or 0) > 0
        )
        return candidates[0][0] if candidates else 0

    def _battle_mode(self, local_units: list[dict[str, Any]]) -> str:
        return "assault" if any(str(row.get("engagement_mode") or "").lower() == "assault" for row in local_units) else "positional"

    def _lifecycle_status(
        self,
        prior_row: dict[str, Any],
        round_resolved: bool,
        previous_a: int,
        previous_b: int,
        current_a: int,
        current_b: int,
    ) -> str:
        """Classify a still-contested battle without inventing extra outcomes."""
        prior_status = str(prior_row.get("status") or "active").lower()
        if not round_resolved:
            return prior_status if prior_status in {"active", "stalemate"} else "active"
        if current_a == previous_a and current_b == previous_b:
            return "stalemate"
        return "active"

    def _battle_units_changed(
        self,
        battle_units: pl.DataFrame | None,
        battle_id: str,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
    ) -> bool:
        """Detect readiness or participant changes that require a status update."""
        if battle_units is None or battle_units.is_empty() or "battle_id" not in battle_units.columns:
            return bool(local_units)
        existing = {
            str(row.get("unit_id") or ""): (
                str(row.get("country_id") or ""),
                str(row.get("side") or ""),
                str(row.get("readiness_status") or ""),
                float(row.get("contribution_weight") or 0.0),
                float(row.get("effective_strength") or 0.0),
            )
            for row in battle_units.filter(pl.col("battle_id") == battle_id).to_dicts()
        }
        current: dict[str, tuple[str, str, str, float, float]] = {}
        for row in sorted(local_units, key=lambda unit: str(unit.get("id") or "")):
            owner = self._clean_tag(row.get("owner"))
            if owner in conflict.side_a_members:
                side = "SIDE_A"
            elif owner in conflict.side_b_members:
                side = "SIDE_B"
            else:
                continue
            weight = self._readiness.combat_weight(row.get("readiness_status"))
            unit_id = str(row.get("id") or "")
            current[unit_id] = (
                owner,
                side,
                self._readiness.normalize(row.get("readiness_status")),
                float(weight),
                float(max(0, int(row.get("strength") or 0)) * weight),
            )
        return existing != current


    def _apply_combat_round(
        self,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
        mode: str,
    ) -> str | None:
        side_a_strength = self._total_strength(local_units, conflict.side_a_members)
        side_b_strength = self._total_strength(local_units, conflict.side_b_members)
        raw_a = self._raw_strength(local_units, conflict.side_a_members)
        raw_b = self._raw_strength(local_units, conflict.side_b_members)
        outcome = self._policy.resolve(side_a_strength, side_b_strength, mode)
        # Resolve tactics on readiness-weighted strength, then translate losses
        # back to personnel so a low-readiness modifier does not make a unit
        # impossible to eliminate in a decisive round.
        losses_a = int(round(outcome.attacker_losses * raw_a / max(1, side_a_strength)))
        losses_b = int(round(outcome.defender_losses * raw_b / max(1, side_b_strength)))
        self._distribute_losses(local_units, conflict.side_a_members, losses_a)
        self._distribute_losses(local_units, conflict.side_b_members, losses_b)

        remaining_a = self._total_strength(local_units, conflict.side_a_members)
        remaining_b = self._total_strength(local_units, conflict.side_b_members)
        if remaining_a > 0 and remaining_b > 0:
            return None
        if remaining_a <= 0 and remaining_b <= 0:
            return None
        if remaining_a > 0:
            return self._dominant_country(local_units, conflict.side_a_members)
        return self._dominant_country(local_units, conflict.side_b_members)

    def _build_battle_row(
        self,
        battle_id: str,
        war_id: str,
        mode: str,
        region_id: int,
        side_a_tags: frozenset[str],
        side_b_tags: frozenset[str],
        side_a_strength: int,
        side_b_strength: int,
        now: int,
        side_a_losses: int = 0,
        side_b_losses: int = 0,
        status: str = "active",
        round_number: int | None = None,
        prior_row: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        prior = prior_row or {}
        total_strength = max(1, side_a_strength + side_b_strength)
        current_round = int(prior.get("round") or 0) if round_number is None else int(round_number)
        return {
            "id": battle_id,
            "war_id": war_id,
            "region_id": region_id,
            "attacker_side": ",".join(sorted(side_a_tags)),
            "defender_side": ",".join(sorted(side_b_tags)),
            "mode": mode,
            "balance": float(side_a_strength / total_strength),
            "side_a_strength": float(side_a_strength),
            "side_b_strength": float(side_b_strength),
            "side_a_losses": int(side_a_losses),
            "side_b_losses": int(side_b_losses),
            "round": current_round,
            "started_at_minute": int(
                prior.get("started_at_minute")
                if prior.get("started_at_minute") is not None
                else now
            ),
            "updated_at_minute": now,
            "concluded_at_minute": 0,
            "victor_side": "",
            "status": status,
        }

    def _build_battle_units(
        self,
        battle_id: str,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
        total_strength: int,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        safe_total = max(1, total_strength)
        for row in sorted(local_units, key=lambda unit: str(unit.get("id") or "")):
            owner = self._clean_tag(row.get("owner"))
            if owner in conflict.side_a_members:
                side = "SIDE_A"
            elif owner in conflict.side_b_members:
                side = "SIDE_B"
            else:
                continue

            rows.append(
                {
                    "battle_id": battle_id,
                    "unit_id": str(row.get("id") or ""),
                    "country_id": owner,
                    "side": side,
                    "role": (conflict.roles or {}).get(owner, "principal"),
                    "readiness_status": self._readiness.normalize(row.get("readiness_status")),
                    "contribution_weight": self._readiness.combat_weight(row.get("readiness_status")),
                    "effective_strength": float(max(0, int(row.get("strength") or 0)) * self._readiness.combat_weight(row.get("readiness_status"))),
                    "strength_share": float(int(row.get("strength") or 0) / safe_total),
                }
            )
        return rows

    def _build_participants(
        self,
        battle_id: str,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
    ) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for unit in local_units:
            owner = self._clean_tag(unit.get("owner"))
            if owner in conflict.side_a_members:
                side = "SIDE_A"
            elif owner in conflict.side_b_members:
                side = "SIDE_B"
            else:
                continue
            key = (owner, side)
            row = grouped.setdefault(key, {
                "battle_id": battle_id,
                "country_id": owner,
                "side": side,
                "role": (conflict.roles or {}).get(owner, "principal"),
                "eligibility_basis": (conflict.bases or {}).get(owner, "war_side"),
                "unit_count": 0,
                "weighted_strength": 0.0,
            })
            row["unit_count"] += 1
            row["weighted_strength"] += max(0, int(unit.get("strength") or 0)) * self._readiness.combat_weight(unit.get("readiness_status"))
        return [grouped[key] for key in sorted(grouped)]

    def _occupation_row(
        self,
        region_id: int,
        occupier: str,
        local_units: list[dict[str, Any]],
        now: int,
        previous: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        prior = previous or {}
        row = {
            "region_id": region_id,
            "controller_country_id": occupier,
            "garrison_strength": int(self._raw_strength(local_units, {occupier})),
            "resistance": 0.0,
            "occupation_status": "active",
            "started_at_minute": int(
                prior.get("started_at_minute")
                if prior.get("started_at_minute") is not None
                else now
            ),
            "updated_at_minute": now,
            "contested": False,
        }
        stable_fields = (
            "region_id",
            "controller_country_id",
            "garrison_strength",
            "resistance",
            "occupation_status",
            "contested",
        )
        if prior and all(prior.get(field) == row.get(field) for field in stable_fields):
            return prior
        return row

    def _occupation_candidate(
        self,
        local_units: list[dict[str, Any]],
        current_controller: str,
        wars: WarIndex,
    ) -> str | None:
        if not local_units or current_controller in UNCLAIMED_TAGS:
            return None

        sorted_strengths = sorted(
            (
                (owner, self._total_strength(local_units, {owner}))
                for owner in {self._clean_tag(row.get("owner")) for row in local_units if self._clean_tag(row.get("owner"))}
            ),
            key=lambda item: (-item[1], item[0]),
        )
        if not sorted_strengths:
            return None

        occupier = sorted_strengths[0][0]
        if occupier == current_controller or not wars.is_hostile(occupier, current_controller):
            return None

        for owner, _ in sorted_strengths[1:]:
            if wars.is_hostile(owner, occupier):
                return None

        return occupier

    def _dominant_country(self, local_units: list[dict[str, Any]], eligible_tags: Iterable[str]) -> str:
        best_tag = ""
        best_strength = -1
        eligible = set(eligible_tags)
        for tag in sorted(eligible):
            strength = self._total_strength(local_units, {tag})
            if strength > best_strength:
                best_strength = strength
                best_tag = tag
        return best_tag

    def _winning_country(self, local_units: list[dict[str, Any]], conflict: ConflictContext) -> str:
        remaining_a = self._total_strength(local_units, conflict.side_a_members)
        remaining_b = self._total_strength(local_units, conflict.side_b_members)
        if remaining_a > remaining_b:
            return self._dominant_country(local_units, conflict.side_a_members)
        if remaining_b > remaining_a:
            return self._dominant_country(local_units, conflict.side_b_members)
        return ""

    def _total_strength(self, local_units: list[dict[str, Any]], eligible_tags: Iterable[str]) -> int:
        eligible = set(eligible_tags)
        raw_strength = sum(
            max(0, int(row.get("strength") or 0))
            for row in local_units
            if self._clean_tag(row.get("owner")) in eligible
        )
        if raw_strength <= 0:
            return 0
        effective_strength = sum(
            max(0, int(row.get("strength") or 0)) * self._readiness.combat_weight(row.get("readiness_status"))
            for row in local_units
            if self._clean_tag(row.get("owner")) in eligible
        )
        return max(1, int(round(effective_strength)))

    def _raw_strength(self, local_units: list[dict[str, Any]], eligible_tags: Iterable[str]) -> int:
        eligible = set(eligible_tags)
        return sum(
            max(0, int(row.get("strength") or 0))
            for row in local_units
            if self._clean_tag(row.get("owner")) in eligible
        )

    def _distribute_losses(self, local_units: list[dict[str, Any]], eligible_tags: Iterable[str], total_losses: int) -> None:
        remaining_losses = max(0, total_losses)
        if remaining_losses <= 0:
            return

        eligible_rows = [
            row
            for row in sorted(local_units, key=lambda unit: str(unit.get("id") or ""))
            if self._clean_tag(row.get("owner")) in set(eligible_tags) and int(row.get("strength") or 0) > 0
        ]
        if not eligible_rows:
            return

        remaining_strength = sum(int(row.get("strength") or 0) for row in eligible_rows)
        for index, row in enumerate(eligible_rows):
            if remaining_losses <= 0:
                break

            strength = max(0, int(row.get("strength") or 0))
            if strength <= 0 or remaining_strength <= 0:
                continue

            if index == len(eligible_rows) - 1:
                row_losses = remaining_losses
            else:
                row_share = strength / remaining_strength
                row_losses = max(1, int(round(total_losses * row_share)))
                row_losses = min(row_losses, remaining_losses)

            applied_losses = min(strength, row_losses)
            row["strength"] = strength - applied_losses
            remaining_losses -= applied_losses
            remaining_strength -= strength

    def _existing_active_battle_ids(self, battles: pl.DataFrame | None) -> set[str]:
        if battles is None or battles.is_empty() or "id" not in battles.columns:
            return set()
        if "status" not in battles.columns:
            return {str(value) for value in battles["id"].to_list()}
        return {
            str(row["id"])
            for row in battles.select(["id", "status"]).iter_rows(named=True)
            if str(row.get("status") or "").lower() == "active"
        }

    def _battle_row(self, battles: pl.DataFrame | None, battle_id: str) -> dict[str, Any]:
        if battles is None or battles.is_empty() or "id" not in battles.columns:
            return {}
        matches = battles.filter(pl.col("id") == battle_id)
        return matches.to_dicts()[0] if not matches.is_empty() else {}

    def _sync_country_strengths(self, countries: pl.DataFrame, unit_rows: list[dict[str, Any]]) -> pl.DataFrame:
        if "id" not in countries.columns:
            return countries

        if "military_count" not in countries.columns:
            countries = countries.with_columns(pl.lit(0).alias("military_count"))

        strength_by_owner: dict[str, int] = {}
        for row in unit_rows:
            owner = self._clean_tag(row.get("owner"))
            if not owner:
                continue
            strength_by_owner[owner] = strength_by_owner.get(owner, 0) + max(0, int(row.get("strength") or 0))

        return countries.with_columns(
            pl.col("id").map_elements(
                lambda country_id: int(strength_by_owner.get(str(country_id), 0)),
                return_dtype=pl.Int64,
            ).alias("military_count")
        )

    def _set_region_controller(self, region_rows: list[dict[str, Any]], region_id: int, controller_tag: str) -> None:
        for row in region_rows:
            if int(row.get("id") or 0) == region_id:
                row["controller"] = controller_tag
                return

    def _battle_id(self, region_id: int, war_id: str) -> str:
        return f"battle-region-{region_id}-{war_id}"

    def _clean_tag(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip().upper()

    def _reset_battle_tables(self, state: GameState) -> None:
        self._update_table_if_changed(state, BATTLE_TABLE, pl.DataFrame(schema=BATTLE_SCHEMA))
        self._update_table_if_changed(state, BATTLE_UNITS_TABLE, pl.DataFrame(schema=BATTLE_UNITS_SCHEMA))
        self._update_table_if_changed(
            state,
            "battle_participants",
            pl.DataFrame(schema=BATTLE_PARTICIPANTS_SCHEMA),
        )
        self._update_table_if_changed(state, "occupations", pl.DataFrame(schema=OCCUPATION_SCHEMA))

    def _update_table_if_changed(self, state: GameState, name: str, frame: pl.DataFrame) -> bool:
        current = state.tables.get(name)
        if current is not None and current.equals(frame):
            return False
        state.update_table(name, frame)
        return True

    def _frame_from_rows(self, schema: dict[str, pl.DataType], rows: list[dict[str, Any]]) -> pl.DataFrame:
        if not rows:
            return pl.DataFrame(schema=schema)
        return pl.DataFrame(rows, schema=schema)
