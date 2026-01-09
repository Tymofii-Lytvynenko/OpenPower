from typing import List, Dict
from graphlib import TopologicalSorter, CycleError
from src.server.state import GameState
from src.shared.actions import GameAction
from src.engine.interfaces import ISystem

class Engine:
    """
    The core logic driver. 
    Orchestrates systems using a Dependency Graph to determine execution order.
    """
    
    def __init__(self):
        # Map: "base.economy" -> EconomySystem instance
        self.systems_map: Dict[str, ISystem] = {}
        
        # The finalized, sorted list used in the loop
        self.execution_order: List[ISystem] = []
        
        # Dirty flag to trigger rebuild on next tick if systems changed
        self._is_dirty = False

    def register_systems(self, systems: List[ISystem]):
        """
        Registers a batch of systems and marks the graph for rebuild.
        """
        for system in systems:
            if system.id in self.systems_map:
                print(f"[Engine] Warning: System '{system.id}' is being overwritten!")
            self.systems_map[system.id] = system
        
        self._is_dirty = True

    def _rebuild_execution_order(self):
        """
        Uses Topological Sort to resolve dependencies.
        """
        print("[Engine] Building dependency graph...")
        sorter = TopologicalSorter()
        
        # 1. Build the graph structure
        for sys_id, system in self.systems_map.items():
            sorter.add(sys_id, *system.dependencies)

        try:
            # 2. Resolve order
            sorted_ids = list(sorter.static_order())
            
            # 3. Map IDs back to Instances
            self.execution_order = [
                self.systems_map[sys_id] 
                for sys_id in sorted_ids 
                if sys_id in self.systems_map
            ]
            
            order_names = [s.id for s in self.execution_order]
            print(f"[Engine] Graph resolved. Execution Order: {order_names}")
            self._is_dirty = False

        except CycleError as e:
            print(f"[Engine] CRITICAL ERROR: Circular dependency detected! {e}")
            raise e
        except Exception as e:
            print(f"[Engine] Error building system graph: {e}")
            raise e

    def step(self, state: GameState, actions: List[GameAction], delta_time: float):
        """
        Runs one tick of the simulation using the sorted graph.
        """
        if self._is_dirty:
            self._rebuild_execution_order()

        # 1. Reset Frame State
        # Events are transient; they only exist for the duration of the current tick.
        state.events.clear()

        # 2. Inject Inputs
        state.globals["tick"] = state.globals.get("tick", 0) + 1
        state.current_actions = actions
        
        # 3. Run All Systems in Strict Order
        # TimeSystem will likely run first (if dep graph is correct), generating events.
        # Economy/Politics systems will run later, consuming those events.
        for system in self.execution_order:
            try:
                system.update(state, delta_time)
            except Exception as e:
                # In production, we might want to isolate the crash so the whole server doesn't die.
                print(f"[Engine] Error in system '{system.id}': {e}")