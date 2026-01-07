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
            # Add node and its edges (dependencies)
            sorter.add(sys_id, *system.dependencies)

        try:
            # 2. Resolve order (returns generator of IDs)
            sorted_ids = list(sorter.static_order())
            
            # 3. Map IDs back to Instances
            # Note: sorted_ids may contain IDs of dependencies that aren't registered 
            # (if a mod declares a dependency on a missing system). We filter those out.
            self.execution_order = [
                self.systems_map[sys_id] 
                for sys_id in sorted_ids 
                if sys_id in self.systems_map
            ]
            
            # Debug output
            order_names = [s.id for s in self.execution_order]
            print(f"[Engine] Graph resolved. Execution Order: {order_names}")
            
            self._is_dirty = False

        except CycleError as e:
            # Critical error: A depends on B, and B depends on A
            print(f"[Engine] CRITICAL ERROR: Circular dependency detected in systems! {e}")
            # In production, you might want to crash explicitly or load a safe-mode fallback
            raise e
        except Exception as e:
            print(f"[Engine] Error building system graph: {e}")
            raise e

    def step(self, state: GameState, actions: List[GameAction], delta_time: float):
        """
        Runs one tick of the simulation using the sorted graph.
        """
        # Rebuild graph if new systems were registered (e.g. hot-reloading)
        if self._is_dirty:
            self._rebuild_execution_order()

        # 1. Update Global Time
        state.globals["tick"] = state.globals.get("tick", 0) + 1
        
        # 2. Run All Systems in Strict Order
        for system in self.execution_order:
            try:
                system.update(state, delta_time)
            except Exception as e:
                print(f"[Engine] Error in system '{system.id}': {e}")