from graphlib import CycleError, TopologicalSorter
from typing import Any, Dict, List

from src.engine.interfaces import ICheckpointedSystem, ISystem
from src.shared.system_state import validate_runtime_state_contract
from src.shared.actions import GameAction
from src.shared.state import GameState


class Engine:
    """
    The core logic driver.
    Orchestrates systems using a Dependency Graph to determine execution order.
    """

    def __init__(self, dev_mode: bool = False):
        self.dev_mode = dev_mode
        # Map: "base.economy" -> InternalEconomySystem instance
        self.systems_map: Dict[str, ISystem] = {}

        # The finalized, sorted list used in the loop
        self.execution_order: List[ISystem] = []

        # Dirty flag to trigger rebuild on next tick if systems changed
        self._is_dirty = False

    def register_systems(self, systems: List[ISystem]) -> None:
        """
        Registers a batch of systems and validates their runtime-state contract up front.
        """
        for system in systems:
            validate_runtime_state_contract(system)
            if system.id in self.systems_map:
                print(f"[Engine] Warning: System '{system.id}' is being overwritten!")
            self.systems_map[system.id] = system

        self._is_dirty = True

    def _ensure_execution_order(self) -> None:
        if self._is_dirty:
            self._rebuild_execution_order()

    def _validate_runtime_state_contracts(self) -> None:
        for system in self.systems_map.values():
            validate_runtime_state_contract(system)

    def _rebuild_execution_order(self) -> None:
        """
        Uses Topological Sort to resolve dependencies.
        """
        print("[Engine] Building dependency graph...")
        sorter = TopologicalSorter()

        for sys_id, system in self.systems_map.items():
            sorter.add(sys_id, *system.dependencies)

        try:
            sorted_ids = list(sorter.static_order())
            self.execution_order = [
                self.systems_map[sys_id]
                for sys_id in sorted_ids
                if sys_id in self.systems_map
            ]

            order_names = [system.id for system in self.execution_order]
            print(f"[Engine] Graph resolved. Execution Order: {order_names}")
            self._is_dirty = False

        except CycleError as exc:
            print(f"[Engine] CRITICAL ERROR: Circular dependency detected! {exc}")
            raise exc
        except Exception as exc:
            print(f"[Engine] Error building system graph: {exc}")
            raise exc

    def restore_system_state(self, state: GameState) -> None:
        """
        Restores checkpointed mutable system internals from GameState.
        """
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
        """
        Writes checkpointed mutable system internals back into GameState.
        """
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

    def step(self, state: GameState, actions: List[GameAction], delta_time: float) -> None:
        """
        Runs one tick of the simulation using the sorted graph.
        """
        self._ensure_execution_order()
        self._validate_runtime_state_contracts()

        state.events.clear()
        state.globals["tick"] = state.globals.get("tick", 0) + 1
        state.current_actions = actions

        import traceback
        from src.shared.events import EventSystemError

        for system in self.execution_order:
            try:
                system.update(state, delta_time)
            except Exception as exc:
                tb_text = traceback.format_exc()
                print(f"[Engine] Error in system '{system.id}': {exc}\n{tb_text}")

                state.events.append(
                    EventSystemError(
                        system_id=system.id,
                        error_message=str(exc),
                        traceback_text=tb_text,
                    )
                )

                if self.dev_mode:
                    raise exc

        self._validate_runtime_state_contracts()
