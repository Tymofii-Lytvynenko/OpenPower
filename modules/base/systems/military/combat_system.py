from __future__ import annotations

from typing import Any, Iterable

import polars as pl

from modules.base.systems.military.combat_round_resolver import (
    CombatOutcome as CombatOutcome,
    CombatResolutionPolicy as CombatResolutionPolicy,
    CombatRoundResolver,
    normalize_country_tag,
)

from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase
from src.shared.system_state import SYSTEM_STATE_HELPER
from src.shared.events import EventBattleEnded, EventBattleParticipantRejected, EventBattleStarted, EventBattleUpdated, EventNewHour, EventOccupationChanged
from src.shared.actions import ActionAttackUnit, ActionMoveUnit
from src.shared.state import GameState
from modules.base.systems.military.alliance_policy import AlliancePolicy
from modules.base.systems.military.battle_anchor_policy import BattleAnchor, resolve_battle_anchor
from modules.base.systems.military.battle_public_counts import public_battle_counts
from modules.base.systems.military.battle_snapshot_builder import (
    BattleRowRequest,
    BattleSnapshotBuilder,
    BattleStrengthDelta,
)
from modules.base.systems.military.war_index import (
    ConflictContext as ConflictContext,
    WarIndex as WarIndex,
    WarRecord as WarRecord,
)
from modules.base.systems.military.battle_change_detection import battle_snapshot_changed
from modules.base.systems.military.battle_victory_finalizer import (
    BattleEndedEventRequest,
    BattleVictoryFinalizer,
    ConcludedBattleRowRequest,
    ConcludedOccupationUpdateRequest,
    VictoryFinalizationOperations,
    VictoryResolutionBatch as _VictoryResolutionBatch,
)
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
    "anchor_latitude": pl.Float64,
    "anchor_longitude": pl.Float64,
    "anchor_source": pl.Utf8,
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
    "combat_posture": (pl.Utf8, "hold"),
    "combat_strength_modifier": (pl.Float64, 1.0),
    "war_exhaustion_modifier": (pl.Float64, 1.0),
    "combat_casualty_modifier": (pl.Float64, 1.0),
    "combat_defense_modifier": (pl.Float64, 1.0),
    "combat_attack_risk_modifier": (pl.Float64, 1.0),
    "combat_readiness_modifier": (pl.Float64, 1.0),
    "combat_holding_modifier": (pl.Float64, 1.0),
    "combat_counterattack_modifier": (pl.Float64, 1.0),
}


class CombatSystem(ISystem):
    access = SystemAccess(
        reads=frozenset({'countries', 'regions', 'units', 'countries_wars', 'countries_treaties', 'battles', 'unit_readiness_transitions', 'unit_capability_projections', 'battle_casualty_records', 'battle_public_counts'}),
        writes=frozenset({'regions', 'units', 'battles', 'battle_units', 'battle_participants', 'battle_casualty_records', 'occupations', 'battle_public_counts'}),
        handles=frozenset({ActionAttackUnit, ActionMoveUnit}),
        phase=SystemPhase.COMBAT,
    )
    runtime_state_contract = {
        "_policy": SYSTEM_STATE_HELPER,
        "_readiness": SYSTEM_STATE_HELPER,
        "_alliances": SYSTEM_STATE_HELPER,
        "_victory_finalizer": SYSTEM_STATE_HELPER,
        "_combat_round_resolver": SYSTEM_STATE_HELPER,
        "_battle_snapshot_builder": SYSTEM_STATE_HELPER,
    }

    def __init__(self):
        self._policy = CombatResolutionPolicy()
        self._readiness = ReadinessPolicy()
        self._combat_round_resolver = CombatRoundResolver(
            policy=self._policy,
            readiness=self._readiness,
        )
        self._battle_snapshot_builder = BattleSnapshotBuilder(self._readiness)
        self._alliances = AlliancePolicy()
        self._victory_finalizer = BattleVictoryFinalizer(
            VictoryFinalizationOperations(
                battle_row_lookup=self._battle_row,
                concluded_battle_row_builder=self._concluded_battle_row,
                battle_ended_event_factory=self._battle_ended_event,
                concluded_occupation_updater=self._update_concluded_occupation,
            )
        )
        self._capability_index: dict[str, dict[str, Any]] = {}

    @property
    def _capability_index(self) -> dict[str, dict[str, Any]]:
        return self._combat_round_resolver.capability_index

    @_capability_index.setter
    def _capability_index(self, value: dict[str, dict[str, Any]]) -> None:
        self._combat_round_resolver.set_capability_index(value)

    def _apply_combat_round(
        self,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
        mode: str,
    ) -> str | None:
        return self._combat_round_resolver.apply_combat_round(local_units, conflict, mode)

    def _total_strength(
        self,
        local_units: list[dict[str, Any]],
        eligible_tags: Iterable[str],
    ) -> int:
        return self._combat_round_resolver.total_strength(local_units, eligible_tags)

    def _casualty_modifier(
        self,
        local_units: list[dict[str, Any]],
        eligible_tags: Iterable[str],
    ) -> float:
        return self._combat_round_resolver._casualty_modifier(local_units, eligible_tags)

    def _side_damage_factor(
        self,
        local_units: list[dict[str, Any]],
        attacking_tags: Iterable[str],
        defending_tags: Iterable[str],
    ) -> float:
        return self._combat_round_resolver._side_damage_factor(
            local_units,
            attacking_tags,
            defending_tags,
        )

    def _capability_damage_factor(
        self,
        unit: dict[str, Any],
        defenders: list[dict[str, Any]],
    ) -> float:
        return self._combat_round_resolver._capability_damage_factor(unit, defenders)

    def _raw_strength(
        self,
        local_units: list[dict[str, Any]],
        eligible_tags: Iterable[str],
    ) -> int:
        return self._combat_round_resolver.raw_strength(local_units, eligible_tags)

    @property
    def id(self) -> str:
        return "base.combat"

    @property
    def dependencies(self) -> list[str]:
        return ["base.military", "base.diplomacy"]

    def _prepare_battle_regions(self, regions, unit_rows):
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

        return stationary_units, region_rows, original_controllers

    def _battle_iteration_key(self, region_id: int, stationary_units, wars) -> tuple[int, str, int]:
        owners = {
            self._clean_tag(row.get("owner"))
            for row in stationary_units[region_id]
            if self._clean_tag(row.get("owner"))
        }
        conflict = wars.active_battle_for_region(owners)
        if conflict is not None:
            return (0, self._battle_id(region_id, conflict.war_id), region_id)
        return (1, f"region-{region_id:010d}", region_id)


    def _expand_battle_participants(self, state, wars, conflict, local_units, region_id, present_owners):
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
        return conflict

    @staticmethod
    def _cancel_contact_readiness(state: GameState, local_units) -> None:
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


    def update(self, state: GameState, delta_time: float) -> None:
        if REGIONS_TABLE not in state.tables or UNITS_TABLE not in state.tables:
            self._reset_battle_tables(state)
            return

        regions = self._ensure_regions_table(state.get_table(REGIONS_TABLE))
        units = self._ensure_units_table(state.get_table(UNITS_TABLE))
        projection_table = state.tables.get("unit_capability_projections")
        self._combat_round_resolver.load_capability_projections(projection_table)
        wars = WarIndex.from_table(state.tables.get(COUNTRIES_WARS_TABLE))
        existing_battles = self._existing_active_battle_ids(state.tables.get(BATTLE_TABLE))
        should_resolve = (not state.time.is_paused) and any(isinstance(event, EventNewHour) for event in state.events)
        assaulting_unit_ids = {
            action.attacker_unit_id if isinstance(action, ActionAttackUnit) else action.unit_id
            for action in state.current_actions
            if isinstance(action, (ActionAttackUnit, ActionMoveUnit))
        }

        unit_rows = units.to_dicts()
        casualty_table = state.tables.get("battle_casualty_records")
        casualty_rows = [] if casualty_table is None else casualty_table.to_dicts()
        stationary_units, region_rows, original_controllers = self._prepare_battle_regions(regions, unit_rows)

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
        # Stable battle-ID ordering keeps multi-region event sequences replayable
        # even when numeric region IDs do not share the same lexical order.
        for region_id in sorted(stationary_units, key=lambda region_id: self._battle_iteration_key(region_id, stationary_units, wars)):
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
                conflict = self._expand_battle_participants(
                    state, wars, conflict, local_units, region_id, present_owners,
                )
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

                self._cancel_contact_readiness(state, local_units)

                prior_row = self._battle_row(state.tables.get(BATTLE_TABLE), battle_id)
                anchor = resolve_battle_anchor(local_units, region_row, prior_row)
                previous_a = self._combat_round_resolver.total_strength(local_units, conflict.side_a_members)
                previous_b = self._combat_round_resolver.total_strength(local_units, conflict.side_b_members)
                battle_metadata[battle_id] = {
                    "war_id": conflict.war_id,
                    "mode": battle_mode,
                    "side_a_tags": conflict.side_a_tags,
                    "side_b_tags": conflict.side_b_tags,
                    "prior_row": prior_row,
                    "anchor": anchor,
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
                    pre_round_strength = {
                        str(row.get("id") or ""): max(0, int(row.get("strength") or 0))
                        for row in local_units
                    }
                    victor = self._combat_round_resolver.apply_combat_round(local_units, conflict, battle_mode)
                    self._combat_round_resolver.record_round_casualties(
                        casualty_rows, battle_id, int(prior_row.get("round") or 0) + 1,
                        local_units, conflict, pre_round_strength, int(state.time.total_minutes),
                    )
                    if victor is not None:
                        victorious_battles[battle_id] = victor
                        victorious_sides[battle_id] = "SIDE_A" if victor in conflict.side_a_members else "SIDE_B"
                    post_a = self._combat_round_resolver.total_strength(local_units, conflict.side_a_members)
                    post_b = self._combat_round_resolver.total_strength(local_units, conflict.side_b_members)
                    if post_a <= 0 and post_b <= 0:
                        victorious_battles[battle_id] = ""
                        victorious_sides[battle_id] = ""

                side_a_strength = self._combat_round_resolver.total_strength(local_units, conflict.side_a_members)
                side_b_strength = self._combat_round_resolver.total_strength(local_units, conflict.side_b_members)
                battle_metadata[battle_id]["side_a_strength"] = side_a_strength
                battle_metadata[battle_id]["side_b_strength"] = side_b_strength
                if side_a_strength > 0 and side_b_strength > 0:
                    status = self._battle_snapshot_builder.lifecycle_status(
                        prior_row,
                        BattleStrengthDelta(
                            round_resolved=resolve_this_tick,
                            previous_a=previous_a,
                            previous_b=previous_b,
                            current_a=side_a_strength,
                            current_b=side_b_strength,
                        ),
                    )
                    round_number = int(prior_row.get("round") or 0) + (1 if resolve_this_tick else 0)
                    current_balance = float(side_a_strength / max(1, side_a_strength + side_b_strength))
                    battle_changed = (
                        not prior_row
                        or resolve_this_tick
                        or battle_snapshot_changed(
                            prior_row,
                            status=status,
                            mode=battle_mode,
                            side_a_tags=conflict.side_a_tags,
                            side_b_tags=conflict.side_b_tags,
                            side_a_strength=side_a_strength,
                            side_b_strength=side_b_strength,
                            balance=current_balance,
                        )
                        or self._battle_snapshot_builder.battle_units_changed(
                            state.tables.get(BATTLE_UNITS_TABLE),
                            battle_id,
                            local_units,
                            conflict,
                        )
                    )
                    if battle_changed:
                        battle_row = self._battle_snapshot_builder.build_battle_row(
                            BattleRowRequest(
                                battle_id=battle_id,
                                war_id=conflict.war_id,
                                mode=battle_mode,
                                region_id=region_id,
                                side_a_tags=conflict.side_a_tags,
                                side_b_tags=conflict.side_b_tags,
                                side_a_strength=side_a_strength,
                                side_b_strength=side_b_strength,
                                now=int(state.time.total_minutes),
                                side_a_losses=int(prior_row.get("side_a_losses") or 0)
                                + (max(0, previous_a - side_a_strength) if resolve_this_tick else 0),
                                side_b_losses=int(prior_row.get("side_b_losses") or 0)
                                + (max(0, previous_b - side_b_strength) if resolve_this_tick else 0),
                                status=status,
                                round_number=round_number,
                                prior_row=prior_row,
                                anchor=anchor,
                            )
                        )
                    else:
                        battle_row = prior_row
                    battle_rows.append(battle_row)
                    battle_unit_rows.extend(
                        self._battle_snapshot_builder.build_battle_units(
                            battle_id=battle_id,
                            local_units=local_units,
                            conflict=conflict,
                            total_strength=side_a_strength + side_b_strength,
                        )
                    )
                    participant_rows.extend(self._battle_snapshot_builder.build_participants(
                        battle_id, local_units, conflict,
                    ))
                    if battle_changed or float(prior_row.get("balance") or -1.0) != current_balance:
                        state.events.append(self._battle_snapshot_builder.build_updated_event(
                            battle_row, conflict, int(state.time.total_minutes),
                        ))
                else:
                    winner = self._combat_round_resolver.winning_country(local_units, conflict)
                    if winner:
                        victorious_battles[battle_id] = winner
                        victorious_sides[battle_id] = "SIDE_A" if winner in conflict.side_a_members else "SIDE_B"
            else:
                occupation_rows = self._update_uncontested_region(
                    region_id, region_row, local_units, wars, occupation_rows,
                    int(state.time.total_minutes),
                )

        # Finish victories after scanning every region to preserve event order.
        occupation_rows = self._finalize_victories(
            state,
            _VictoryResolutionBatch(
                victorious_battles, victorious_sides, active_battle_ids, battle_regions,
                battle_metadata, battle_rows, unit_rows, region_rows, occupation_rows,
            ),
        )

        unit_rows = [row for row in unit_rows if int(row.get("strength") or 0) > 0]
        self._update_table_if_changed(state, UNITS_TABLE, self._frame_from_rows(units.schema, unit_rows))
        self._publish_controller_changes(state, regions, region_rows, original_controllers)
        self._update_table_if_changed(state, BATTLE_TABLE, self._frame_from_rows(BATTLE_SCHEMA, battle_rows))
        self._update_table_if_changed(state, BATTLE_UNITS_TABLE, self._frame_from_rows(BATTLE_UNITS_SCHEMA, battle_unit_rows))
        alive_ids = {str(row.get("id")) for row in unit_rows}
        self._update_table_if_changed(
            state, "battle_public_counts", public_battle_counts(
                battle_rows, [row for row in battle_unit_rows if str(row.get("unit_id")) in alive_ids], unit_rows,
            ),
        )
        self._update_table_if_changed(
            state,
            "battle_participants",
            self._frame_from_rows(BATTLE_PARTICIPANTS_SCHEMA, participant_rows),
        )
        self._publish_casualties(state, casualty_rows, casualty_table)
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

    def _finalize_victories(
        self,
        state: GameState,
        batch: _VictoryResolutionBatch,
    ) -> list[dict[str, Any]]:
        return self._victory_finalizer.finalize(state, batch)

    def _replace_occupation(self, occupation_rows, region_id, controller, local_units, now):
        previous = next(
            (row for row in occupation_rows if int(row.get('region_id') or 0) == region_id),
            None,
        )
        updated = self._occupation_row(region_id, controller, local_units, now, previous)
        retained = [row for row in occupation_rows if int(row.get('region_id') or 0) != region_id]
        retained.append(updated)
        return retained

    def _update_uncontested_region(
        self, region_id, region_row, local_units, wars, occupation_rows, now,
    ):
        for unit in local_units:
            unit["engagement_mode"] = ""
        occupier = self._occupation_candidate(
            local_units=local_units,
            current_controller=self._clean_tag(region_row.get("controller")),
            wars=wars,
        )
        if occupier is not None:
            region_row["controller"] = occupier
            occupation_rows = self._replace_occupation(
                occupation_rows, region_id, occupier, local_units, now,
            )

        return occupation_rows

    def _concluded_battle_row(
        self,
        request: ConcludedBattleRowRequest,
    ) -> dict[str, Any]:
        prior_row = request.prior_row
        battle_id = request.battle_id
        region_id = request.region_id
        metadata = request.metadata
        now = request.now
        victor_side = request.victor_side
        concluded_row = dict(prior_row)
        if not concluded_row:
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
                now=now,
                side_a_losses=max(0, previous_a - side_a_strength) if bool(metadata.get("round_resolved")) else 0,
                side_b_losses=max(0, previous_b - side_b_strength) if bool(metadata.get("round_resolved")) else 0,
                status="concluded",
                round_number=round_number,
                anchor=metadata.get("anchor"),
            )
        else:
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
        concluded_row["updated_at_minute"] = now
        concluded_row["concluded_at_minute"] = now
        concluded_row["victor_side"] = victor_side
        return concluded_row

    def _update_concluded_occupation(
        self,
        request: ConcludedOccupationUpdateRequest,
    ) -> list[dict[str, Any]]:
        region_id = request.region_id
        victor = request.victor
        unit_rows = request.unit_rows
        region_rows = request.region_rows
        occupation_rows = request.occupation_rows
        now = request.now
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
            occupation_rows = self._replace_occupation(
                occupation_rows, region_id, victor_tag, garrison_units, now,
            )
        else:
            for occupation in occupation_rows:
                if int(occupation.get("region_id") or 0) == region_id:
                    occupation["contested"] = True
                    occupation["occupation_status"] = "contested"
                    occupation["updated_at_minute"] = now

        return occupation_rows

    @staticmethod
    def _battle_updated_event(row: dict[str, Any], conflict: ConflictContext, now: int) -> EventBattleUpdated:
        return BattleSnapshotBuilder.build_updated_event(row, conflict, now)

    @staticmethod
    def _battle_ended_event(
        request: BattleEndedEventRequest,
    ) -> EventBattleEnded:
        # Outcomes are emitted after scanning every region. The loop's last
        # local_units/conflict belongs to another battle when several end
        # together; recipient and side metadata must come from this result.
        concluded_row = request.concluded_row
        side_a_countries = WarIndex._normalize_side(concluded_row.get("attacker_side"))
        side_b_countries = WarIndex._normalize_side(concluded_row.get("defender_side"))
        return EventBattleEnded(
            battle_id=request.battle_id,
            victor_tag=request.victor,
            victor_side=str(concluded_row.get("victor_side") or ""),
            region_id=request.region_id,
            concluded_at_minute=request.now,
            side_a_losses=int(concluded_row.get("side_a_losses") or 0),
            side_b_losses=int(concluded_row.get("side_b_losses") or 0),
            participant_countries=tuple(sorted(side_a_countries | side_b_countries)),
            side_a_country_ids=tuple(sorted(side_a_countries)),
            side_b_country_ids=tuple(sorted(side_b_countries)),
        )

    def _publish_controller_changes(self, state, regions, region_rows, original_controllers) -> None:
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
                state.events.append(EventOccupationChanged(
                    region_id=region_id,
                    previous_controller=str(original_controllers.get(region_id) or ""),
                    controller=controller,
                    source="battle_resolution",
                    at_minute=int(state.time.total_minutes),
                ))
                self._set_region_controller(all_region_rows, region_id, controller)
            updated_regions = self._frame_from_rows(regions.schema, all_region_rows)
        self._update_table_if_changed(state, REGIONS_TABLE, updated_regions)

    def _publish_casualties(self, state, casualty_rows, casualty_table) -> None:
        if casualty_rows != ([] if casualty_table is None else casualty_table.to_dicts()):
            casualty_schema = {
                "id": pl.Utf8, "battle_id": pl.Utf8, "unit_id": pl.Utf8,
                "country_id": pl.Utf8, "side": pl.Utf8, "unit_type": pl.Utf8,
                "losses": pl.Int64, "round": pl.Int32, "created_at_minute": pl.Int64,
            }
            updated_casualties = pl.DataFrame(sorted(casualty_rows, key=lambda row: str(row.get("id") or "")), schema=casualty_schema) if casualty_rows else pl.DataFrame(schema=casualty_schema)
            self._update_table_if_changed(state, "battle_casualty_records", updated_casualties)

    def _ensure_regions_table(self, regions: pl.DataFrame) -> pl.DataFrame:
        if "controller" not in regions.columns:
            return regions.with_columns(pl.col("owner").alias("controller"))
        return regions

    def _ensure_units_table(self, units: pl.DataFrame) -> pl.DataFrame:
        for column, (_, default_value) in UNIT_REQUIRED_COLUMNS.items():
            if column not in units.columns:
                units = units.with_columns(pl.lit(default_value).alias(column))

        if "equipment_quantity" not in units.columns:
            # Match the unit-table migration so legacy group strength remains a usable quantity.
            units = units.with_columns(
                pl.col("strength").cast(pl.Int64, strict=False).fill_null(0).alias("equipment_quantity")
            )

        casted_columns = []
        for column, (dtype, _) in UNIT_REQUIRED_COLUMNS.items():
            casted_columns.append(pl.col(column).cast(dtype).alias(column))

        return units.with_columns(casted_columns)

    def _stationary_units_by_region(self, unit_rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in sorted(unit_rows, key=lambda unit: str(unit.get("id") or "")):
            # Tactical withdrawals remain attached to their battle until the route lifecycle resolves.
            if bool(row.get("is_moving", False)) and str(row.get("unit_lifecycle") or "") not in {"battle_retreating", "battle_disengaging"}:
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
        return self._battle_snapshot_builder.lifecycle_status(
            prior_row,
            BattleStrengthDelta(
                round_resolved=round_resolved,
                previous_a=previous_a,
                previous_b=previous_b,
                current_a=current_a,
                current_b=current_b,
            ),
        )

    def _battle_units_changed(
        self,
        battle_units: pl.DataFrame | None,
        battle_id: str,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
    ) -> bool:
        return self._battle_snapshot_builder.battle_units_changed(
            battle_units,
            battle_id,
            local_units,
            conflict,
        )


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
        anchor: BattleAnchor | None = None,
    ) -> dict[str, Any]:
        return self._battle_snapshot_builder.build_battle_row(
            BattleRowRequest(
                battle_id=battle_id,
                war_id=war_id,
                mode=mode,
                region_id=region_id,
                side_a_tags=side_a_tags,
                side_b_tags=side_b_tags,
                side_a_strength=side_a_strength,
                side_b_strength=side_b_strength,
                now=now,
                side_a_losses=side_a_losses,
                side_b_losses=side_b_losses,
                status=status,
                round_number=round_number,
                prior_row=prior_row,
                anchor=anchor,
            )
        )

    def _build_battle_units(
        self,
        battle_id: str,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
        total_strength: int,
    ) -> list[dict[str, Any]]:
        return self._battle_snapshot_builder.build_battle_units(
            battle_id,
            local_units,
            conflict,
            total_strength,
        )

    def _build_participants(
        self,
        battle_id: str,
        local_units: list[dict[str, Any]],
        conflict: ConflictContext,
    ) -> list[dict[str, Any]]:
        return self._battle_snapshot_builder.build_participants(
            battle_id,
            local_units,
            conflict,
        )

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
            "garrison_strength": int(self._combat_round_resolver.raw_strength(local_units, {occupier})),
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
                (owner, self._combat_round_resolver.total_strength(local_units, {owner}))
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
        return normalize_country_tag(value)

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
