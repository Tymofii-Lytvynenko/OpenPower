"""Authoritative covert-cell lifecycle, mission preparation, and resolution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import polars as pl

from modules.base.systems.military.covert_cell_control import editable_cell, set_cell_activity
from modules.base.systems.military.covert_mission_control import control_prepared_mission
from modules.base.systems.military.covert_mission_profiles import MISSION_PROFILES as MISSION_PROFILES
from modules.base.systems.military.covert_mission_start import plan_mission_start
from modules.base.systems.military.covert_mission_resolution import (
    MissionResolutionServices,
    resolve_mission,
)
from modules.base.systems.military.covert_mission_effects import (
    MissionEffectServices,
    apply_mission_effect,
)
from modules.base.systems.military.covert_schedule import (
    UpdateScheduleServices,
    update_schedule,
)
from modules.base.systems.military.covert_intelligence_snapshot import (
    IntelligenceSnapshotServices,
    build_intelligence_snapshot,
    target_regional_telecom_capacity,
)
from modules.base.systems.military.covert_mobilization_signals import (
    mobilization_observers,
    record_mobilization_signals,
)
from modules.base.systems.military.covert_incidents import mission_incident
from modules.base.systems.military import covert_metrics
from modules.base.systems.military.region_travel_time import RegionTravelTime
from modules.base.systems.military.region_route_snapshot import RegionRouteSnapshot
from modules.base.systems.military.authority_policy import player_controls_country
from modules.base.systems.military.covert_policy import (
    SKILL_LEVELS,
    skill_profile,
)
from modules.base.systems.military.movement_access import MovementAccessPolicy
from modules.base.systems.military.route_policy import MilitaryRoutePlanner, RoutePlan
from src.shared.actions import (
    ActionRetargetCovertCell,
    ActionSetCovertCellActivity,
    ActionExecuteCovertMission,
    ActionCancelCovertMission,
    ActionCreateCovertCell,
    ActionRetireCovertCell,
    ActionSetCovertCellAssignment,
    ActionStartCovertMission,
    ActionTrainCovertCell,
)
from src.shared.events import (
    DomainGameEvent,
    EventMessageCreated,
    EventCovertMissionReady,
)
from src.shared.state import GameState
from src.shared.system_interfaces import ISystem, SystemAccess, SystemPhase


@dataclass
class EventCovertMissionResolved(DomainGameEvent):
    mission_id: str
    result: str
    discovered: bool
    at_minute: int


@dataclass(frozen=True, slots=True)
class _CellDeploymentPlan:
    route: RoutePlan | None
    origin: dict[str, Any] | None
    destination: dict[str, Any] | None
    travel_minutes: int
    rejection_reason: str = ""


@dataclass(frozen=True, slots=True)
class CovertCellCreationQuote:
    setup_cost: float
    daily_upkeep: float
    deployment_minutes: int | None
    rejection_reason: str = ""


@dataclass
class _CovertUpdateBatch:
    cells: list[dict[str, Any]]
    missions: list[dict[str, Any]]
    country_rows: list[dict[str, Any]]
    routes: list[dict[str, Any]]
    travel_time: RegionTravelTime
    routing: RegionRouteSnapshot


@dataclass(frozen=True)
class _CovertMissionOutcome:
    result: str
    discovered: bool
    attributed_country_id: str
    confidence: float
    output: dict[str, Any]


@dataclass
class _CovertMissionBatch:
    inventory: _CovertUpdateBatch
    country_by_id: dict[str, dict[str, Any]]
    cell_by_id: dict[str, dict[str, Any]]
    relation_rows: list[dict[str, Any]]
    governments: list[dict[str, Any]]
    incidents: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    existing_findings: int
    security_cell_counts: pl.DataFrame | None
    espionage_cell_counts: pl.DataFrame | None
    population_by_country: pl.DataFrame | None


class CovertOperationsSystem(ISystem):
    access = SystemAccess(
        reads=frozenset({"countries", "regions", "region_adjacency", "countries_wars", "country_governments", "units", "treaty_effects", "covert_cells", "covert_cell_routes", "covert_missions", "covert_findings", "covert_incidents", "messages", "countries_relations", "regional_production", "domestic_production", "resource_ledger"}),
        writes=frozenset({"countries", "country_governments", "units", "regional_production", "domestic_production", "covert_cells", "covert_cell_routes", "covert_missions", "covert_findings", "covert_incidents", "messages", "countries_relations"}),
        handles=frozenset({ActionRetargetCovertCell, ActionSetCovertCellActivity, ActionExecuteCovertMission, ActionCancelCovertMission, ActionCreateCovertCell, ActionTrainCovertCell, ActionStartCovertMission, ActionRetireCovertCell, ActionSetCovertCellAssignment}),
        phase=SystemPhase.MILITARY + 3,
    )

    @property
    def id(self) -> str:
        return "base.covert_operations"

    @property
    def dependencies(self) -> list[str]:
        return ["base.time", "base.diplomacy", "base.military_programs"]

    def _update_schedule(self, state: GameState) -> tuple[int, float, bool] | None:
        return update_schedule(
            state,
            services=UpdateScheduleServices(finite_number=self._finite),
        )

    def update(self, state: GameState, delta_time: float) -> None:
        schedule = self._update_schedule(state)
        if schedule is None:
            return
        now, elapsed_days, upkeep_boundary = schedule

        cells = state.get_table("covert_cells").to_dicts()
        routes = state.get_table("covert_cell_routes").to_dicts()
        missions = state.get_table("covert_missions").to_dicts()
        findings_frame = state.get_table("covert_findings")
        findings: list[dict[str, Any]] = []
        incidents = state.get_table("covert_incidents").to_dicts()
        countries = state.tables.get("countries")
        country_rows = [] if countries is None else countries.to_dicts()
        original_country_rows = [dict(row) for row in country_rows]
        governments_frame = state.tables.get("country_governments")
        governments = [] if governments_frame is None else governments_frame.to_dicts()
        original_governments = [dict(row) for row in governments]
        relations = state.tables.get("countries_relations")
        relation_rows = [] if relations is None else relations.to_dicts()
        original_relation_rows = [dict(row) for row in relation_rows]
        # Scope the lazy index to this update so later ticks see map changes and
        # idle updates do not scan regions merely to populate a cache.
        travel_time = RegionTravelTime(state.tables.get("regions"))
        routing = RegionRouteSnapshot(state.tables.get("regions"), state.tables.get("region_adjacency"))
        batch = _CovertUpdateBatch(cells, missions, country_rows, routes, travel_time, routing)
        self._process_actions(state, batch)
        cells, missions = batch.cells, batch.missions

        country_by_id = {self._tag(row.get("id")): row for row in country_rows}
        cell_by_id = {str(row.get("id")): row for row in cells}
        self._record_mobilization_signals(state, cells, country_by_id, findings, now)
        self._advance_cells(state, batch, country_by_id, now, elapsed_days, upkeep_boundary)

        security_cell_counts, espionage_cell_counts, population_by_country = (
            self._resolution_metrics(state, cells, missions, now)
        )

        mission_batch = _CovertMissionBatch(
            batch, country_by_id, cell_by_id, relation_rows, governments, incidents,
            findings, findings_frame.height, security_cell_counts, espionage_cell_counts,
            population_by_country,
        )
        self._advance_missions(state, mission_batch, now)

        self._write(state, "covert_cells", cells)
        self._write(state, "covert_cell_routes", routes)
        self._write(state, "covert_missions", missions)
        if findings:
            new_findings = pl.DataFrame(findings, schema=findings_frame.schema)
            combined_findings = pl.concat([findings_frame, new_findings], how="vertical")
            self._write_frame_if_changed(state, "covert_findings", combined_findings)
        self._write(state, "covert_incidents", incidents)
        if countries is not None and country_rows != original_country_rows:
            state.update_table("countries", pl.DataFrame(country_rows, schema=countries.schema))
        if governments_frame is not None and governments != original_governments:
            state.update_table("country_governments", pl.DataFrame(governments, schema=governments_frame.schema))
        if relations is not None and relation_rows != original_relation_rows:
            state.update_table("countries_relations", pl.DataFrame(relation_rows, schema=relations.schema))

    def _execution_participants(
        self, state: GameState, batch: _CovertMissionBatch, mission: dict, now: int,
    ) -> tuple[dict, dict] | None:
        cell = batch.cell_by_id.get(str(mission.get('cell_id')))
        target = batch.country_by_id.get(self._tag(mission.get('target_country_id')))
        if cell is None or target is None or cell.get('status') not in {'active', 'idle', 'preparing'}:
            mission.update(
                status='cancelled',
                result='Mission conditions invalid at execution.',
                updated_at_minute=now,
            )
            return None
        target_regions = state.tables.get('regions')
        target_id = self._tag(target.get('id'))
        if target_regions is not None and (not self._has_target_region(target_regions, target_id)):
            mission.update(
                status='cancelled',
                result='Target access or ownership is no longer valid.',
                updated_at_minute=now,
            )
            return None
        return cell, target

    def _advance_missions(self, state: GameState, batch: _CovertMissionBatch, now: int) -> None:
        for mission in batch.inventory.missions:
            if mission.get('status') == 'cleanup':
                self._advance_mission_cleanup(mission, batch.cell_by_id, now)
                continue
            if mission.get('status') not in {'preparation', 'executing'}:
                continue
            if mission.get('status') == 'preparation':
                self._advance_mission_preparation(state, mission, batch.cell_by_id, batch.country_by_id, now)
                continue
            if now < int(mission.get('resolves_at_minute') or 0):
                continue
            participants = self._execution_participants(state, batch, mission, now)
            if participants is None:
                continue
            cell, target = participants
            self._execute_mission(state, batch, mission, cell, target, now)

    def _execute_mission(
        self, state: GameState, batch: _CovertMissionBatch, mission: dict,
        cell: dict, target: dict, now: int,
    ) -> None:
        (result, discovered, attributed, confidence, output) = self._resolve(
            state,
            cell,
            mission,
            target,
            batch.inventory.cells,
            batch.relation_rows,
            batch.security_cell_counts,
            batch.espionage_cell_counts,
            batch.population_by_country,
        )
        owner_id = self._tag(mission.get('owner_country_id'))
        framed_id = self._tag(mission.get('framed_country_id'))
        attributed_country_id = framed_id if attributed and framed_id else owner_id if attributed else ''
        attributed_to_owner = bool(attributed_country_id and attributed_country_id == owner_id)
        mission.update(
            status='cleanup',
            result=result,
            discovered_by_target=discovered,
            attributed_to_owner=attributed_to_owner,
            attributed_country_id=attributed_country_id,
            confidence=confidence,
            output_json=json.dumps(output, sort_keys=True, separators=(',', ':')),
            updated_at_minute=now,
            cleanup_until_minute=now + max(1, int(self._finite(state.globals.get('covert_cleanup_minutes', 60)))),
        )
        cell['status'] = 'debriefing'
        cell['readiness'] = max(0.0, self._finite(cell.get('readiness')) - 0.2)
        if result in {'success', 'partial_success'} or attributed_country_id:
            self._apply_mission_effect(
                state,
                mission,
                target,
                output,
                batch.governments,
                batch.relation_rows,
                attributed_country_id,
                partial=result == 'partial_success',
                outcome=result,
            )
            mission['output_json'] = json.dumps(output, sort_keys=True, separators=(',', ':'))
        outcome = _CovertMissionOutcome(result, discovered, attributed_country_id, confidence, output)
        self._record_mission_incident(mission, outcome, batch.incidents, now)
        state.events.append(EventCovertMissionResolved(str(mission['id']), result, discovered, now))
        self._publish_messages(
            state,
            mission,
            result,
            discovered,
            attributed_to_owner,
            attributed_country_id=attributed_country_id,
        )
        self._record_mission_finding(mission, outcome, batch.findings, batch.existing_findings, now)


    def _record_mission_incident(self, mission, outcome: _CovertMissionOutcome, incidents, now) -> None:
        incident_id = self._next_id('covert-incident', incidents)
        incidents.append(mission_incident(mission, outcome, incident_id, now))

    def _record_mission_finding(self, mission, outcome: _CovertMissionOutcome, findings, existing_count, now) -> None:
        if mission.get('mission_type', '').endswith('espionage') and outcome.output and (outcome.result in {'success', 'partial_success'}):
            findings.append(
                {
                    'id': self._next_id('finding', existing_count + len(findings)),
                    'owner_country_id': mission['owner_country_id'],
                    'target_country_id': mission['target_country_id'],
                    'category': 'military' if 'military' in mission['mission_type'] else 'civilian',
                    'value_json': json.dumps(outcome.output, sort_keys=True, separators=(',', ':')),
                    'confidence': outcome.confidence,
                    'freshness': self._finite(outcome.output.get('information_freshness', 1.0)),
                    'discovered_at_minute': now,
                    'expires_at_minute': now + 365 * 24 * 60,
                },
            )

    def _advance_cells(self, state, batch: _CovertUpdateBatch, country_by_id, now, elapsed_days, upkeep_boundary) -> None:
        for cell in batch.cells:
            if cell.get('status') in {'transit', 'transit_blocked'}:
                self._advance_cell_transit(state, cell, batch.routes, now, batch.travel_time, batch.routing)
            elif cell.get('status') == 'training':
                self._advance_training(state, cell, elapsed_days)
            owner = self._tag(cell.get('country_id'))
            if upkeep_boundary and cell.get('status') in {'active', 'idle'} and (owner in country_by_id):
                upkeep = max(0.0, self._finite(cell.get('upkeep')))
                balance = self._finite(country_by_id[owner].get('money_reserves'))
                if upkeep and balance >= upkeep:
                    country_by_id[owner]['money_reserves'] = balance - upkeep
                elif upkeep:
                    cell['status'] = 'dormant'
                    cell['last_known_status'] = 'dormant: upkeep unpaid'

    def _process_actions(self, state: GameState, batch: _CovertUpdateBatch) -> None:
        for action in state.current_actions:
            if isinstance(action, ActionCreateCovertCell):
                batch.cells = self._create_cell(
                    state,
                    batch.cells,
                    batch.country_rows,
                    batch.routes,
                    action,
                    batch.travel_time,
                    batch.routing,
                )
            elif isinstance(action, ActionTrainCovertCell):
                self._train_cell(state, batch.cells, batch.country_rows, action)
            elif isinstance(action, ActionStartCovertMission):
                batch.missions = self._start_mission(state, batch.cells, batch.country_rows, batch.missions, action)
            elif isinstance(action, ActionSetCovertCellAssignment):
                self._set_assignment(state, batch.cells, action)
            elif isinstance(action, (ActionRetargetCovertCell, ActionSetCovertCellActivity)):
                reason = (
                    self._retarget_cell(state, batch.cells, batch.missions, batch.routes, action, batch.travel_time, batch.routing)
                    if isinstance(action, ActionRetargetCovertCell)
                    else set_cell_activity(state, batch.cells, batch.missions, action)
                )
                if reason:
                    self._reject(state, action, reason)
                else:
                    state.journal.append_command_result(
                        dict(
                            tick=int(state.globals.get('tick', 0)),
                            player_id=str(action.player_id),
                            action_type=type(action).__name__,
                            status='applied',
                            cell_id=str(action.cell_id),
                            reason='Covert cell updated.',
                        ),
                    )
            elif isinstance(action, ActionRetireCovertCell):
                self._retire_cell(state, batch.cells, action, batch.missions)
            elif isinstance(action, (ActionExecuteCovertMission, ActionCancelCovertMission)):
                reason = control_prepared_mission(state, batch.cells, batch.missions, action)
                if reason:
                    self._reject(state, action, reason)

    def _resolution_metrics(self, state, cells, missions, now):
        security_cell_counts = None
        espionage_cell_counts = None
        population_by_country = None
        if any(
            mission.get("status") == "executing"
            and now >= int(mission.get("resolves_at_minute") or 0)
            for mission in missions
        ):
            # Build mission coverage counts once in Polars instead of rescanning
            # the complete covert-cell roster for every resolving mission.
            cell_frame = pl.DataFrame(cells, schema=state.get_table("covert_cells").schema)
            security_cell_counts, espionage_cell_counts = self._cell_metric_frames(cell_frame)
            population_by_country = self._population_metric_frame(state.tables.get("regions"))

        return security_cell_counts, espionage_cell_counts, population_by_country

    @staticmethod
    def _advance_mission_cleanup(mission, cell_by_id, now) -> None:
        if now >= int(mission.get("cleanup_until_minute") or 0):
            mission.update(status="resolved", updated_at_minute=now)
            cleanup_cell = cell_by_id.get(str(mission.get("cell_id")))
            if cleanup_cell is not None:
                cleanup_cell["status"] = "captured" if mission.get("result") == "captured" else "active"
                cleanup_cell["mission_type"] = ""

    def _advance_mission_preparation(self, state, mission, cell_by_id, country_by_id, now) -> None:
        cell = cell_by_id.get(str(mission.get("cell_id")))
        target = country_by_id.get(self._tag(mission.get("target_country_id")))
        if cell is None or target is None or cell.get("status") != "preparing":
            discovered = bool(cell and cell.get("status") == "captured")
            mission.update(
                status="cancelled", result="captured" if discovered else "cancelled",
                discovered_by_target=discovered, updated_at_minute=now,
            )
            if discovered:
                self._publish_messages(state, mission, "captured", True, False)
            return
        required_minutes = max(1.0, self._finite(mission.get("preparation_required")))
        elapsed_minutes = max(0, now - int(mission.get("created_at_minute") or 0))
        mission["preparation_progress"] = min(1.0, elapsed_minutes / required_minutes)

        if now < int(mission.get("resolves_at_minute") or 0):
            return
        if mission.get("requires_execution_confirmation"):
            mission.update(status="ready", updated_at_minute=now)
            cell.update(status="ready", last_known_status="mission ready to execute")
            state.events.append(EventCovertMissionReady(self._tag(mission.get("owner_country_id")),
                str(cell["id"]), str(mission["id"]), now))
            return
        mission.update(
            status="executing",
            resolves_at_minute=now + max(1, int(self._finite(state.globals.get("covert_execution_minutes", 1)))),
        )
        return

    def _has_target_region(self, regions: pl.DataFrame, target_id: str) -> bool:
        columns = [column for column in ("owner", "controller") if column in regions.columns]
        if not columns:
            return False
        matches = [
            pl.col(column).cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase() == target_id
            for column in columns
        ]
        return not regions.filter(pl.any_horizontal(matches)).is_empty()

    _cell_metric_frames = staticmethod(covert_metrics.cell_metric_frames)
    _metric_count = staticmethod(covert_metrics.metric_count)
    _metric_value = staticmethod(covert_metrics.metric_value)
    _population_metric_frame = staticmethod(covert_metrics.population_metric_frame)

    def _mobilization_observers(self, cells, target_id):
        return mobilization_observers(
            cells,
            target_id,
            normalize_tag=self._tag,
            finite_number=self._finite,
        )

    def _record_mobilization_signals(self, state, cells, countries_by_id, findings, now):
        record_mobilization_signals(
            state,
            cells,
            countries_by_id,
            findings,
            now,
            normalize_tag=self._tag,
            finite_number=self._finite,
            regional_telecom_capacity=self._target_regional_telecom_capacity,
            country_population=self._country_population,
        )

    def quote_cell_creation(
        self,
        state: GameState,
        owner_tag: str,
        target_tag: str,
        training_level: str = "Recruit",
    ) -> CovertCellCreationQuote:
        owner, target = self._tag(owner_tag), self._tag(target_tag)
        level = str(training_level or "Recruit")
        setup_cost, daily_upkeep = self._cell_creation_economics(state, level)
        if level not in SKILL_LEVELS:
            return CovertCellCreationQuote(setup_cost, daily_upkeep, None, "Invalid training level.")
        countries = state.tables.get("countries")
        known_countries = (
            {self._tag(row.get("id")) for row in countries.iter_rows(named=True)}
            if countries is not None else set()
        )
        if owner not in known_countries or target not in known_countries:
            return CovertCellCreationQuote(setup_cost, daily_upkeep, None, "Country is unavailable.")
        deployment = self._plan_cell_deployment(state, owner, target)
        return CovertCellCreationQuote(
            setup_cost,
            daily_upkeep,
            None if deployment.rejection_reason else deployment.travel_minutes,
            deployment.rejection_reason,
        )

    def _cell_creation_economics(self, state: GameState, training_level: str) -> tuple[float, float]:
        setup_cost = max(0.0, self._finite(state.globals.get("covert_cell_creation_cost", 10.0)))
        base_upkeep = max(0.0, self._finite(state.globals.get("covert_cell_upkeep", 0.25)))
        return setup_cost, base_upkeep * skill_profile(training_level).upkeep_multiplier

    def _plan_cell_deployment(
        self,
        state: GameState,
        owner: str,
        target: str,
        travel_time: RegionTravelTime | None = None,
        routing: RegionRouteSnapshot | None = None,
    ) -> _CellDeploymentPlan:
        if owner == target:
            return _CellDeploymentPlan(None, None, None, 0)
        travel_time = travel_time or RegionTravelTime(state.tables.get("regions"))
        routing = routing or RegionRouteSnapshot(
            state.tables.get("regions"), state.tables.get("region_adjacency")
        )
        origin = self._country_home_region(state, owner, routing)
        destination = self._country_home_region(state, target, routing)
        if origin is None or destination is None:
            return _CellDeploymentPlan(
                None, origin, destination, 0,
                "A valid origin or target deployment region is unavailable.",
            )
        route = self._plan_cell_route(state, owner, target, origin, destination, travel_time, routing)
        if not route.is_valid:
            return _CellDeploymentPlan(
                route, origin, destination, 0,
                route.rejection_reason or "No legal covert transit route is available.",
            )
        travel_minutes = sum(
            travel_time.estimate_minutes(left, right)
            for left, right in zip(route.region_ids, route.region_ids[1:])
        )
        return _CellDeploymentPlan(route, origin, destination, travel_minutes)

    def _create_cell(self, state, cells, countries, routes, action, travel_time: RegionTravelTime, routing: RegionRouteSnapshot):
        owner, target = self._tag(action.country_tag), self._tag(action.target_country_tag)
        if not owner or owner not in {self._tag(row.get("id")) for row in countries} or not self._authorized(state, action.player_id, owner):
            self._reject(state, action, "The issuer cannot create a cell for this country.")
            return cells
        if not target or target not in {self._tag(row.get("id")) for row in countries}:
            self._reject(state, action, "The target country does not exist.")
            return cells
        training_level = str(action.training_level or "Recruit")
        if training_level not in SKILL_LEVELS:
            self._reject(state, action, "The selected training level is invalid.")
            return cells
        active_count = sum(1 for row in cells if self._tag(row.get("country_id")) == owner and row.get("status") not in {"retired", "lost"})
        limit = max(1, int(self._finite(state.globals.get("covert_cell_capacity", 8))))
        cost, upkeep = self._cell_creation_economics(state, training_level)
        country = next(row for row in countries if self._tag(row.get("id")) == owner)
        if active_count >= limit or self._finite(country.get("money_reserves")) < cost:
            self._reject(state, action, "Cell capacity is full or the country cannot fund recruitment.")
            return cells
        deployment = self._plan_cell_deployment(state, owner, target, travel_time, routing)
        if deployment.rejection_reason:
            self._reject(state, action, deployment.rejection_reason)
            return cells
        country["money_reserves"] = self._finite(country.get("money_reserves")) - cost
        transit = owner != target
        profile = skill_profile(training_level)
        new_id = self._next_id("cell", cells)
        now = int(state.time.total_minutes)
        cells.append({
            "id": new_id, "country_id": owner, "target_country_id": target,
            "cell_name": str(action.cell_name or f"Cell {active_count + 1}"),
            "readiness": 0.5 if not transit else 0.0, "mission_type": "",
            "status": "transit" if transit else "active", "origin_country_id": owner,
            "location_country_id": owner, "assignment": "unassigned", "skill_level": training_level,
            "training_target": "", "training_progress": 0.0, "training_required": 0.0,
            "training_completes_at_minute": 0,
            "concealment": profile.concealment,
            "base_upkeep": upkeep / max(profile.upkeep_multiplier, 1e-9),
            "upkeep": upkeep,
            "communications_ready": True, "available_at_minute": now + deployment.travel_minutes,
            "last_known_status": "in transit" if transit else "recruited",
        })
        if (
            transit and deployment.route is not None
            and deployment.origin is not None and deployment.destination is not None
        ):
            first_leg_minutes = travel_time.estimate_minutes(
                deployment.route.region_ids[0], deployment.route.region_ids[1]
            )
            routes.append({
                "cell_id": new_id, "owner_country_id": owner,
                "source_region_id": int(deployment.origin.get("id") or 0),
                "destination_region_id": int(deployment.destination.get("id") or 0),
                "route_region_ids": list(deployment.route.region_ids), "route_index": 0,
                "arrival_at_minute": now + first_leg_minutes,
                "status": "in_transit", "rejection_reason": "", "updated_at_minute": now,
            })
        return cells

    def _retarget_cell(self, state, cells, missions, routes, action, travel_time, routing):
        cell, reason = editable_cell(state, cells, missions, action)
        if reason:
            return reason
        owner, target = self._tag(cell.get("country_id")), self._tag(action.target_country_tag)
        countries = state.tables.get("countries")
        if countries is None or not target or not any(self._tag(r.get("id")) == target for r in countries.iter_rows(named=True)):
            return "The assigned country is unavailable."
        if target == self._tag(cell.get("target_country_id")):
            return ""
        location = self._tag(cell.get("location_country_id"))
        if not cell.get("communications_ready"):
            return "The cell must restore communications before reassignment."
        previous_route = next((r for r in routes if str(r.get("cell_id")) == str(cell["id"]) and r.get("status") == "arrived"), None)
        # Prefer the recorded arrival region. A changed capital must not teleport
        # a deployed cell; only legacy coarse-location saves use the home region.
        origin = (routing.region_by_id.get(int(previous_route.get("destination_region_id") or 0))
                  if previous_route else self._country_home_region(state, location, routing))
        if origin is not None and self._tag(origin.get("owner")) != location:
            return "The recorded deployment location changed ownership."
        destination = self._country_home_region(state, target, routing)
        if origin is None or destination is None:
            return "A valid current location or destination region is unavailable."
        now = int(state.time.total_minutes)
        if location == target:
            cell.update(target_country_id=target, assignment="unassigned", last_known_status=str(cell["status"]))
            return ""
        plan = self._plan_cell_route(state, owner, target, origin, destination, travel_time, routing)
        if not plan.is_valid or len(plan.region_ids) < 2:
            return plan.rejection_reason or "No legal route exists to the assigned country."
        duration = sum(travel_time.estimate_minutes(a, b) for a, b in zip(plan.region_ids, plan.region_ids[1:]))
        first_leg = travel_time.estimate_minutes(plan.region_ids[0], plan.region_ids[1])
        if now + duration > 9_223_372_036_854_775_807 or now + first_leg > 9_223_372_036_854_775_807:
            return "The covert transit date exceeds the supported range."
        # Preflight the complete route before replacing an old arrived route or
        # changing the assignment. Rejection leaves both records intact.
        route = next((r for r in routes if str(r.get("cell_id")) == str(cell["id"])), None)
        updated = dict(cell_id=str(cell["id"]), owner_country_id=owner,
            source_region_id=int(origin["id"]), destination_region_id=int(destination["id"]),
            route_region_ids=list(plan.region_ids), route_index=0, arrival_at_minute=now + first_leg,
            status="in_transit", rejection_reason="", updated_at_minute=now)
        if route is None:
            routes.append(updated)
        else:
            route.update(updated)
        cell.update(target_country_id=target, status="transit", assignment="unassigned", mission_type="",
                    communications_ready=True, available_at_minute=now + duration, last_known_status="in transit")
        return ""

    def _advance_cell_transit(self, state, cell, routes, now, travel_time: RegionTravelTime, routing: RegionRouteSnapshot):
        cell_id = str(cell.get("id") or "")
        route = next((row for row in routes if str(row.get("cell_id") or "") == cell_id), None)
        if route is None:
            # Legacy saves used a single configured transit deadline and have no route record.
            if now >= int(cell.get("available_at_minute") or 0):
                self._arrive_cell(cell, now)
            return
        if now < int(route.get("arrival_at_minute") or 0):
            return
        regions = state.tables.get("regions")
        if regions is None:
            self._block_cell_transit(cell, route, "The region map is unavailable.", now)
            return
        route_ids = [int(value) for value in route.get("route_region_ids") or []]
        route_index = max(0, int(route.get("route_index") or 0))
        current_region_id = route_ids[route_index] if route_index < len(route_ids) else 0
        destination_id = int(route.get("destination_region_id") or 0)
        owner = self._tag(cell.get("country_id"))
        target = self._tag(cell.get("target_country_id"))
        planner = MilitaryRoutePlanner()
        access = MovementAccessPolicy()
        access_context = access.for_country(state, owner)
        if current_region_id <= 0 or destination_id <= 0:
            self._block_cell_transit(cell, route, "The current or destination region is invalid.", now)
            return
        if current_region_id == destination_id:
            route.update(status="arrived", rejection_reason="", updated_at_minute=now)
            self._arrive_cell(cell, now)
            return

        if str(route.get("status") or "") == "blocked":
            plan = self._plan_cell_route_from_region(state, planner, access, owner, target, current_region_id, destination_id, routing, travel_time)
            if not plan.is_valid or len(plan.region_ids) < 2:
                self._block_cell_transit(cell, route, plan.rejection_reason or "No legal route remains for the cell.", now)
                return
            route.update(
                route_region_ids=list(plan.region_ids), route_index=0,
                arrival_at_minute=now + travel_time.estimate_minutes(plan.region_ids[0], plan.region_ids[1]),
                status="in_transit", rejection_reason="", updated_at_minute=now,
            )
            cell.update(status="transit", communications_ready=True, last_known_status="in transit")
            return

        due_at = int(route.get("arrival_at_minute") or 0)
        while now >= due_at:
            next_index = route_index + 1
            if next_index >= len(route_ids):
                self._block_cell_transit(cell, route, "The remaining route is incomplete.", now)
                return
            next_region_id = route_ids[next_index]
            next_region = routing.region_by_id.get(next_region_id)
            final = next_region_id == destination_id
            if next_region is None or not self._cell_region_access(access_context, owner, target, next_region, final):
                plan = self._plan_cell_route_from_region(state, planner, access, owner, target, current_region_id, destination_id, routing, travel_time)
                if not plan.is_valid or len(plan.region_ids) < 2:
                    self._block_cell_transit(cell, route, plan.rejection_reason or "The next route segment lost access rights.", now)
                    return
                route.update(
                    route_region_ids=list(plan.region_ids), route_index=0,
                    arrival_at_minute=now + travel_time.estimate_minutes(plan.region_ids[0], plan.region_ids[1]),
                    status="in_transit", rejection_reason="", updated_at_minute=now,
                )
                return
            route_index = next_index
            current_region_id = next_region_id
            if final:
                route.update(route_index=route_index, status="arrived", rejection_reason="", updated_at_minute=now)
                self._arrive_cell(cell, now)
                return
            next_next_id = route_ids[route_index + 1] if route_index + 1 < len(route_ids) else destination_id
            due_at += travel_time.estimate_minutes(current_region_id, next_next_id)
            route.update(route_index=route_index, arrival_at_minute=due_at, updated_at_minute=now)

    def _plan_cell_route_from_region(self, state, planner, access, owner, target, source_id, destination_id, routing: RegionRouteSnapshot, travel_time: RegionTravelTime):
        access_context = access.for_country(state, owner)
        prepared_graph = routing.prepared_graph
        travel_time.use_edge_distance_index(prepared_graph.edge_distance_km)
        return planner.plan(
            source_id, destination_id, prepared_graph.region_by_id.values(), None,
            lambda region, final: self._cell_region_access(access_context, owner, target, region, final),
            segment_cost=lambda left, right: travel_time.estimate_minutes(int(left.get("id") or 0), int(right.get("id") or 0)),
            prepared_graph=prepared_graph,
        )

    def _plan_cell_route(self, state, owner, target, origin, destination, travel_time: RegionTravelTime, routing: RegionRouteSnapshot):
        return self._plan_cell_route_from_region(
            state, MilitaryRoutePlanner(), MovementAccessPolicy(), owner, target,
            int(origin.get("id") or 0), int(destination.get("id") or 0),
            routing, travel_time,
        )

    def _cell_region_access(self, access_context, owner, target, region, final):
        if final and self._tag(region.get("owner")) == target:
            return True
        return access_context.can_station(region) if final else access_context.can_transit(region)

    def _country_home_region(self, state, country, routing: RegionRouteSnapshot):
        regions = state.tables.get("regions")
        if regions is None or regions.is_empty() or "owner" not in regions.columns:
            return None
        governments = state.tables.get("country_governments")
        government = next((row for row in governments.to_dicts() if self._tag(row.get("country_id")) == country), None) if governments is not None else None
        capital = int(government.get("capital_region_id") or 0) if government else 0
        return routing.home_region(country, capital)

    def _block_cell_transit(self, cell, route, reason, now):
        route.update(status="blocked", rejection_reason=reason, updated_at_minute=now)
        cell.update(status="transit_blocked", communications_ready=False, last_known_status=f"transit blocked: {reason}")

    def _arrive_cell(self, cell, now):
        cell.update(
            location_country_id=str(cell.get("target_country_id") or ""),
            status="active", communications_ready=True, available_at_minute=now,
            last_known_status="active",
        )

    def _train_cell(self, state, cells, countries, action):
        cell = next((row for row in cells if str(row.get("id")) == str(action.cell_id)), None)
        if cell is None or cell.get("status") not in {"active", "idle"} or not self._authorized(state, action.player_id, self._tag(cell.get("country_id"))):
            self._reject(state, action, "The cell is missing, unavailable, or outside the issuer's authority.")
            return
        level = str(cell.get("skill_level") or "Recruit")
        if level not in SKILL_LEVELS or level == SKILL_LEVELS[-1]:
            self._reject(state, action, "The cell is already at maximum skill or has an invalid skill state.")
            return
        points = max(0.0, min(100.0, self._finite(action.training_points)))
        if points <= 0.0:
            self._reject(state, action, "Training must allocate a positive number of points.")
            return
        next_level = SKILL_LEVELS[SKILL_LEVELS.index(level) + 1]
        configured = state.globals.get("covert_training_points_per_level", 100.0)
        required = max(1.0, self._finite(configured))
        cost = points * max(0.0, self._finite(state.globals.get("covert_training_cost_per_point", 0.1)))
        owner = self._tag(cell.get("country_id"))
        country = next((row for row in countries if self._tag(row.get("id")) == owner), None)
        if country is None or self._finite(country.get("money_reserves")) < cost:
            self._reject(state, action, "The owner cannot fund this training allocation.")
            return
        country["money_reserves"] = self._finite(country.get("money_reserves")) - cost
        cell["status"] = "training"
        cell["training_target"] = next_level
        cell["training_required"] = required
        cell["training_progress"] = min(required, self._finite(cell.get("training_progress")) + points)
        duration = max(1, int(self._finite(state.globals.get("covert_training_minutes_per_level", 1440))))
        cell["training_completes_at_minute"] = int(state.time.total_minutes) + duration

    def _advance_training(self, state, cell, elapsed_days):
        daily_points = max(0.0, self._finite(state.globals.get("covert_training_points_per_day", 20.0)))
        cell["training_progress"] = min(
            self._finite(cell.get("training_required")),
            self._finite(cell.get("training_progress")) + daily_points * elapsed_days,
        )
        if (
            int(state.time.total_minutes) >= int(cell.get("training_completes_at_minute") or 0)
            and self._finite(cell.get("training_progress")) >= self._finite(cell.get("training_required"))
        ):
            self._complete_training(cell)

    def _complete_training(self, cell):
        target = str(cell.get("training_target") or "")
        previous_profile = skill_profile(cell.get("skill_level"))
        if target in SKILL_LEVELS:
            cell["skill_level"] = target
        cell.update(status="active", training_target="", training_required=0.0, training_progress=0.0, training_completes_at_minute=0)
        profile = skill_profile(cell.get("skill_level"))
        current_upkeep = max(0.0, self._finite(cell.get("upkeep")))
        base_upkeep = max(0.0, self._finite(cell.get("base_upkeep")))
        if base_upkeep == 0.0 and current_upkeep > 0.0:
            base_upkeep = current_upkeep / max(previous_profile.upkeep_multiplier, 1e-9)
        cell["base_upkeep"] = base_upkeep
        cell["upkeep"] = base_upkeep * profile.upkeep_multiplier
        cell["concealment"] = profile.concealment
        cell["readiness"] = min(1.0, 0.5 + SKILL_LEVELS.index(str(cell.get("skill_level") or "Recruit")) * 0.16)

    def _start_mission(self, state, cells, countries, missions, action):
        result = plan_mission_start(
            state,
            cells,
            countries,
            missions,
            action,
            normalize_tag=self._tag,
            finite_number=self._finite,
            is_authorized=self._authorized,
        )
        if result.plan is None:
            self._reject(state, action, result.rejection_reason)
            return missions

        plan = result.plan
        cell = next(row for row in cells if str(row.get("id")) == str(plan.cell_id))
        owner_row = next(row for row in countries if self._tag(row.get("id")) == plan.owner_id)
        owner_row["money_reserves"] = (
            self._finite(owner_row.get("money_reserves")) - plan.execution_cost
        )
        now = int(state.time.total_minutes)
        new_id = self._next_id("mission", missions)
        cell["status"] = "preparing"
        cell["mission_type"] = plan.mission_type
        cell["assignment"] = plan.assignment
        missions.append({
            "id": new_id, "cell_id": cell["id"], "owner_country_id": plan.owner_id,
            "target_country_id": plan.target_id, "framed_country_id": plan.cover_id,
            "mission_type": plan.mission_type, "target_sector": plan.target_sector,
            "complexity": plan.complexity, "target_resource_id": plan.target_resource_id,
            "target_unit_category": plan.target_unit_category,
            "status": "preparation", "preparation_progress": 0.0,
            "requires_execution_confirmation": plan.requires_execution_confirmation,
            "preparation_required": float(plan.preparation_minutes), "created_at_minute": now,
            "resolves_at_minute": now + plan.preparation_minutes,
            "cleanup_until_minute": 0,
            "execution_cost": plan.execution_cost, "risk": plan.risk, "result": "", "discovered_by_target": False,
            "attributed_to_owner": False, "confidence": 0.0, "output_json": "{}",
            "updated_at_minute": now,
        })
        return missions

    def _resolve(
        self,
        state,
        cell,
        mission,
        target,
        all_cells,
        relation_rows,
        security_cell_counts: pl.DataFrame | None = None,
        espionage_cell_counts: pl.DataFrame | None = None,
        population_by_country: pl.DataFrame | None = None,
    ):
        return resolve_mission(
            state,
            cell,
            mission,
            target,
            all_cells,
            relation_rows,
            security_cell_counts,
            espionage_cell_counts,
            population_by_country,
            services=MissionResolutionServices(
                normalize_tag=self._tag,
                finite_number=self._finite,
                metric_count=self._metric_count,
                metric_value=self._metric_value,
                country_population=self._country_population,
                relation_value=self._relation_value,
                target_regional_telecom_capacity=self._target_regional_telecom_capacity,
                table_value_by_key=self._table_value_by_key,
                intelligence_snapshot=self._intelligence_snapshot,
            ),
        )

    def _target_regional_telecom_capacity(self, state, cell, target):
        """Use the cell's exact deployed region, falling back to its target capital."""
        return target_regional_telecom_capacity(
            state,
            cell,
            target,
            services=self._intelligence_snapshot_services(),
        )

    def _table_value_by_key(self, frame, key_column, key, value_column, default=None):
        if frame is None or not {key_column, value_column}.issubset(frame.columns):
            return default
        matches = frame.filter(
            pl.col(key_column).cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase()
            == str(key or "").strip().upper()
        ).select(value_column).head(1)
        return matches.item() if not matches.is_empty() else default

    def _intelligence_snapshot(
        self,
        state,
        target,
        mission,
        confidence,
        confidence_factors=None,
        population_by_country: pl.DataFrame | None = None,
    ):
        return build_intelligence_snapshot(
            state,
            target,
            str(mission.get("mission_type")),
            confidence,
            confidence_factors,
            population_by_country,
            services=self._intelligence_snapshot_services(),
        )

    def _intelligence_snapshot_services(self) -> IntelligenceSnapshotServices:
        return IntelligenceSnapshotServices(
            normalize_tag=self._tag,
            finite_number=self._finite,
            table_value_by_key=self._table_value_by_key,
            metric_value=self._metric_value,
            country_population=self._country_population,
        )

    def _apply_mission_effect(self, state, mission, target, output, governments, relations, attributed_country_id, partial=False, outcome="success"):
        apply_mission_effect(
            state,
            mission,
            target,
            output,
            governments,
            relations,
            attributed_country_id,
            partial=partial,
            outcome=outcome,
            services=MissionEffectServices(
                normalize_tag=self._tag,
                finite_number=self._finite,
                sabotage_unit_candidates=self._sabotage_unit_candidates,
                write_frame_if_changed=self._write_frame_if_changed,
                adjust_relations=self._adjust_relations,
            ),
        )

    def _sabotage_unit_candidates(self, state, units: pl.DataFrame, target_id: str, category: str) -> pl.DataFrame:
        country_units = units.filter(
            (pl.col("owner").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase() == target_id)
            & (pl.col("strength").cast(pl.Int64, strict=False).fill_null(0) > 0)
        )
        expected_domain = {
            "ground": "land",
            "air": "air",
            "naval": "naval",
            "strategic": "strategic",
        }.get(category)
        if category and expected_domain is None:
            return country_units.head(0)
        if expected_domain:
            if "domain" in country_units.columns:
                country_units = country_units.filter(
                    pl.col("domain").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_lowercase()
                    == expected_domain
                )
            else:
                designs = state.tables.get("unit_designs")
                if designs is None or not {"id", "domain"}.issubset(designs.columns) or "design_id" not in country_units.columns:
                    return country_units.head(0)
                eligible_designs = designs.filter(
                    pl.col("domain").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_lowercase()
                    == expected_domain
                ).get_column("id").cast(pl.Utf8, strict=False).fill_null("").to_list()
                country_units = country_units.filter(
                    pl.col("design_id").cast(pl.Utf8, strict=False).fill_null("").is_in(eligible_designs)
                )

        return (
            country_units
            .with_columns(pl.col("id").cast(pl.Utf8, strict=False).fill_null("").alias("_sort_id"))
            .sort("_sort_id")
            .select("id", pl.col("strength").cast(pl.Int64, strict=False).fill_null(0))
            .head(1)
        )

    def _publish_messages(self, state, mission, result, discovered, attributed, attributed_country_id=None):
        table = state.tables.get("messages")
        if table is None:
            return
        owner = self._tag(mission.get("owner_country_id"))
        target = self._tag(mission.get("target_country_id"))
        accused = self._tag(attributed_country_id) or (owner if attributed else "")
        title = str(mission.get("mission_type") or "Covert operation").replace("_", " ").title()
        owner_body = f"{title} against {target}: {result}. Attribution: {accused or 'unconfirmed'}."
        recipients = [(owner, owner_body)]
        if discovered:
            target_body = f"A covert incident was detected. Attribution: {accused or 'unknown'}. Details: {title}; outcome: {result}."
            recipients.append((target, target_body))
        if discovered and accused and accused not in {owner, target}:
            recipients.append((accused, "Your country was implicated in a detected covert operation."))
        additions = []
        for index, (recipient, body) in enumerate(recipients, start=1):
            message_id = self._next_id("covert-message", table.height + index - 1)
            additions.append({
                "id": message_id, "country_id": recipient, "category": "covert",
                "subject": f"{title} {result.replace('_', ' ')}", "body": body,
                "is_read": False, "created_at": str(int(state.time.total_minutes)),
            })
            state.events.append(EventMessageCreated(message_id, recipient, "covert"))
        state.update_table("messages", pl.concat([table, pl.DataFrame(additions, schema=table.schema)], how="vertical"))

    def _country_population(self, state, country):
        regions = state.tables.get("regions")
        if regions is None or not {"owner"}.issubset(regions.columns):
            return 0.0
        population_column = next((name for name in ("population", "total_population") if name in regions.columns), None)
        if population_column is None:
            return 0.0
        value = regions.filter(
            pl.col("owner").cast(pl.Utf8, strict=False).fill_null("").str.strip_chars().str.to_uppercase() == country
        ).select(pl.col(population_column).cast(pl.Float64, strict=False).fill_null(0.0).sum())
        return self._finite(value.item() if not value.is_empty() else 0.0)

    def _relation_value(self, rows, left, right):
        values = [
            self._finite(row.get("value")) for row in rows
            if (self._tag(row.get("source")), self._tag(row.get("target"))) in {(left, right), (right, left)}
        ]
        return sum(values) / len(values) if values else 0.0

    def _adjust_relations(self, rows, left, right, delta):
        if not left or not right:
            return
        pairs = {(left, right), (right, left)}
        touched = set()
        for row in rows:
            pair = (self._tag(row.get("source")), self._tag(row.get("target")))
            if pair in pairs:
                row["value"] = min(100.0, max(-100.0, self._finite(row.get("value")) + delta))
                touched.add(pair)
        template = rows[0] if rows else {"source": "", "target": "", "value": 0.0}
        for source, target in sorted(pairs - touched):
            rows.append({**template, "source": source, "target": target, "value": min(100.0, max(-100.0, delta))})

    def _set_assignment(self, state, cells, action):
        cell = next((row for row in cells if str(row.get("id")) == str(action.cell_id)), None)
        if cell is None or cell.get("status") not in {"active", "idle", "dormant"} or not self._authorized(state, action.player_id, self._tag(cell.get("country_id"))):
            self._reject(state, action, "The cell is missing, unavailable, or outside the issuer's authority.")
            return
        assignment = str(action.assignment or "unassigned").strip().lower()
        allowed = {"unassigned", "domestic_security", "espionage", "sabotage", "dormant"}
        if assignment not in allowed:
            self._reject(state, action, "The requested cell assignment is not supported.")
            return
        cell["assignment"] = assignment
        if assignment == "dormant":
            cell["status"] = "dormant"
        elif cell.get("status") == "dormant":
            cell["status"] = "active"

    def _retire_cell(self, state, cells, action, missions):
        cell = next((row for row in cells if str(row.get("id")) == str(action.cell_id)), None)
        if cell is None or not self._authorized(state, action.player_id, self._tag(cell.get("country_id"))) or cell.get("status") in {"captured", "lost", "retired"}:
            self._reject(state, action, "The cell cannot be retired by this issuer.")
            return
        cell.update(status="retired", assignment="unassigned", mission_type="", last_known_status="retired")
        # A retired cell must not leave a prepared mission executable after load.
        for mission in missions:
            if str(mission.get("cell_id")) == str(cell["id"]) and mission.get("status") in {"preparation", "ready", "executing"}:
                mission.update(status="cancelled", result="cancelled", updated_at_minute=int(state.time.total_minutes))

    def _reject(self, state, action, reason):
        state.journal.append_command_result({
            "tick": int(state.globals.get("tick", 0)),
            "player_id": str(action.player_id),
            "action_type": type(action).__name__,
            "cell_id": str(getattr(action, "cell_id", "") or ""),
            "status": "rejected",
            "reason": reason,
        })

    def _authorized(self, state, player_id, country):
        return player_controls_country(state, player_id, country)

    def _write(self, state, name, rows):
        frame = state.get_table(name)
        result = pl.DataFrame(rows, schema=frame.schema) if rows else pl.DataFrame(schema=frame.schema)
        self._write_frame_if_changed(state, name, result)

    def _write_frame_if_changed(self, state, name, result):
        current = state.get_table(name)
        if current.equals(result):
            # Unchanged idle-tick snapshots must not look like new state to IPC consumers.
            return
        state.update_table(name, result)

    def _next_id(self, prefix, rows):
        count = rows if isinstance(rows, int) else len(rows)
        return f"{prefix}-{count + 1:08d}"

    def _tag(self, value):
        return str(value or "").strip().upper()

    def _finite(self, value):
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        return result if result == result and abs(result) != float("inf") else 0.0
