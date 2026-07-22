from __future__ import annotations

import copy
import heapq
import traceback
from dataclasses import dataclass
from graphlib import CycleError
from typing import Any, Dict, Iterable, List

from src.shared.actions import GameAction
from src.shared.events import EventSystemError
from src.shared.state import GameState
from src.shared.system_interfaces import ICheckpointedSystem, ISystem, system_access
from src.shared.system_state import (
    SYSTEM_STATE_HELPER,
    runtime_state_contract,
    validate_runtime_state_contract,
)


@dataclass(frozen=True)
class SystemFailure:
    system_id: str
    error_message: str
    traceback_text: str


@dataclass(frozen=True)
class EngineStepResult:
    success: bool
    tick: int
    failures: tuple[SystemFailure, ...] = ()


class Engine:
    """Deterministic simulation scheduler with strict dependency validation."""

    def __init__(self, dev_mode: bool = False):
        self.dev_mode = dev_mode
        self.systems_map: Dict[str, ISystem] = {}
        self.execution_order: List[ISystem] = []
        self._is_dirty = False

    def register_systems(self, systems: Iterable[ISystem]) -> None:
        for system in systems:
            validate_runtime_state_contract(system)
            system_id = str(system.id).strip()
            if not system_id:
                raise RuntimeError("Simulation system id cannot be empty.")
            if system_id in self.systems_map:
                raise RuntimeError(f"Duplicate simulation system id '{system_id}'.")
            if not isinstance(system.dependencies, list):
                raise TypeError(f"System '{system_id}' dependencies must be a list.")
            system_access(system)
            self.systems_map[system_id] = system
        self._is_dirty = True

    @property
    def handled_action_types(self) -> frozenset[type[GameAction]]:
        """Return the actions that have an explicit simulation consumer."""

        handled: set[type[GameAction]] = set()
        for system in self.systems_map.values():
            handled.update(system_access(system).handles)
        return frozenset(handled)

    def _ensure_execution_order(self) -> None:
        if self._is_dirty:
            self._rebuild_execution_order()

    def _validate_runtime_state_contracts(self) -> None:
        for system in self.systems_map.values():
            validate_runtime_state_contract(system)

    def _rebuild_execution_order(self) -> None:
        print("[Engine] Building dependency graph...")
        dependencies = {
            system_id: set(system.dependencies)
            for system_id, system in self.systems_map.items()
        }
        missing = {
            system_id: sorted(required - self.systems_map.keys())
            for system_id, required in dependencies.items()
            if required - self.systems_map.keys()
        }
        if missing:
            details = ", ".join(
                f"{system_id} -> {dependency_ids}"
                for system_id, dependency_ids in sorted(missing.items())
            )
            raise RuntimeError(f"Simulation graph has missing dependencies: {details}")

        dependents: dict[str, set[str]] = {system_id: set() for system_id in dependencies}
        indegree = {system_id: len(required) for system_id, required in dependencies.items()}
        for system_id, required in dependencies.items():
            for dependency_id in required:
                dependents[dependency_id].add(system_id)

        ready: list[tuple[int, str]] = []
        for system_id, count in indegree.items():
            if count == 0:
                heapq.heappush(ready, (system_access(self.systems_map[system_id]).phase, system_id))

        sorted_ids: list[str] = []
        while ready:
            _, system_id = heapq.heappop(ready)
            sorted_ids.append(system_id)
            for dependent_id in sorted(dependents[system_id]):
                indegree[dependent_id] -= 1
                if indegree[dependent_id] == 0:
                    heapq.heappush(
                        ready,
                        (system_access(self.systems_map[dependent_id]).phase, dependent_id),
                    )

        if len(sorted_ids) != len(self.systems_map):
            unresolved = sorted(system_id for system_id, count in indegree.items() if count)
            raise CycleError("Circular simulation dependency detected", unresolved)

        self.execution_order = [self.systems_map[system_id] for system_id in sorted_ids]
        print(f"[Engine] Graph resolved. Execution Order: {sorted_ids}")
        self._is_dirty = False

    def restore_system_state(self, state: GameState) -> None:
        self._ensure_execution_order()
        self._validate_runtime_state_contracts()
        for system in self.execution_order:
            if not isinstance(system, ICheckpointedSystem):
                continue
            raw_state = state.system_state.get(system.id, {})
            if not isinstance(raw_state, dict):
                raise TypeError(
                    f"Checkpoint payload for system '{system.id}' must be a dict, "
                    f"got {type(raw_state).__name__}."
                )
            system.import_persistent_state(raw_state)

    def snapshot_system_state(self, state: GameState) -> None:
        self._ensure_execution_order()
        self._validate_runtime_state_contracts()
        captured: dict[str, dict[str, Any]] = {
            system_id: payload
            for system_id, payload in state.system_state.items()
            if system_id not in self.systems_map
        }
        for system in self.execution_order:
            if not isinstance(system, ICheckpointedSystem):
                continue
            payload = system.export_persistent_state()
            if payload:
                captured[system.id] = payload
        state.system_state = captured

    def step(
        self,
        state: GameState,
        actions: List[GameAction],
        delta_time: float,
    ) -> EngineStepResult:
        self._ensure_execution_order()
        self._validate_runtime_state_contracts()

        state_checkpoint = state.create_checkpoint()
        runtime_checkpoint = self._snapshot_mutable_system_state()
        next_tick = int(state.globals.get("tick", 0)) + 1
        state.events.clear()
        state.globals["tick"] = next_tick
        state.current_actions = list(actions)

        for system in self.execution_order:
            try:
                system.update(state, float(delta_time))
            except Exception as exc:
                failure = SystemFailure(
                    system_id=system.id,
                    error_message=str(exc),
                    traceback_text=traceback.format_exc(),
                )
                print(
                    f"[Engine] Error in system '{system.id}': {exc}\n"
                    f"{failure.traceback_text}"
                )
                state.restore_checkpoint(state_checkpoint)
                self._restore_mutable_system_state(runtime_checkpoint)
                state.events = [
                    EventSystemError(
                        system_id=failure.system_id,
                        error_message=failure.error_message,
                        traceback_text=failure.traceback_text,
                    )
                ]
                state.current_actions = list(actions)
                if self.dev_mode:
                    raise
                return EngineStepResult(
                    success=False,
                    tick=int(state.globals.get("tick", 0)),
                    failures=(failure,),
                )

        self._validate_runtime_state_contracts()
        return EngineStepResult(success=True, tick=next_tick)

    def _snapshot_mutable_system_state(self) -> dict[str, dict[str, Any]]:
        snapshots: dict[str, dict[str, Any]] = {}
        for system in self.execution_order:
            contract = runtime_state_contract(system)
            snapshots[system.id] = {
                name: copy.deepcopy(getattr(system, name))
                for name, policy in contract.items()
                if policy != SYSTEM_STATE_HELPER and hasattr(system, name)
            }
        return snapshots

    def _restore_mutable_system_state(self, snapshots: dict[str, dict[str, Any]]) -> None:
        for system_id, values in snapshots.items():
            system = self.systems_map[system_id]
            for name, value in values.items():
                setattr(system, name, value)
