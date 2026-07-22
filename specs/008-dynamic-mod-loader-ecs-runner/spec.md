# Feature Specification: Dynamic Mod Loader & Content-Agnostic ECS Runner

## User Scenarios & Testing

### Primary User Story
As a mod developer or core engine contributor, I want the engine to dynamically scan module manifests (`mod.toml`), load Python system entry points (`registration.py`), and sort `ISystem` instances into a topological execution graph using Python's `graphlib.TopologicalSorter`, so that game mechanics run in strict dependency order without hardcoding logic into the engine loop.

### Acceptance Scenarios
1. **Mod Manifest Discovery**: **Given** active modules in `modules/` (e.g. `modules/base`), **When** `ModManager.resolve_load_order` scans `mod.toml` files, **Then** dependency trees are validated and sorted topologically (base modules first).
2. **Dynamic System Entry Point Loading**: **Given** resolved active modules, **When** `ModManager.load_systems()` executes, **Then** it dynamically imports `modules.{mod_id}.registration` via `importlib.import_module` and executes `register()` to retrieve `ISystem` instances.
3. **Topological ECS System Execution Order**: **Given** 9 core systems with declared dependencies, **When** `Engine._rebuild_execution_order()` runs using `graphlib.TopologicalSorter`, **Then** the resolved execution sequence is established:
   1. `base.time` (0 deps)
   2. `base.population` (dep: `base.time`)
   3. `base.territory` (dep: `base.time`)
   4. `base.trade` (dep: `base.time`)
   5. `base.economy` (deps: `base.time`, `base.trade`)
   6. `base.budget` (deps: `base.time`, `base.economy`, `base.trade`)
   7. `base.military` (deps: `base.time`, `base.population`, `base.economy`)
   8. `base.ai` (dep: `base.time`)
   9. `base.politics` (dep: `base.population`)

### Edge Cases
- Circular dependencies: `graphlib.CycleError` is trapped and raised with critical error logs identifying the cyclic system IDs.
- Missing `registration.py` or `register()` function: Skipped gracefully with warning log without aborting load order for other active modules.
- Re-registering existing system ID: Warning emitted if a system ID is overwritten by a higher-priority mod.

## Core System Dependency Graph Table

| System ID (`id`) | Implementation Class | Declared Dependencies (`dependencies`) | Resolved Position |
| :--- | :--- | :--- | :--- |
| `base.time` | `TimeSystem` | `[]` | 1 |
| `base.population` | `PopulationSystem` | `["base.time"]` | 2 |
| `base.territory` | `TerritorySystem` | `["base.time"]` | 3 |
| `base.trade` | `TradeSystem` | `["base.time"]` | 4 |
| `base.economy` | `InternalEconomySystem` | `["base.time", "base.trade"]` | 5 |
| `base.budget` | `BudgetSystem` | `["base.time", "base.economy", "base.trade"]` | 6 |
| `base.military` | `MilitarySystem` | `["base.time", "base.population", "base.economy"]` | 7 |
| `base.ai` | `AISystem` | `["base.time"]` | 8 |
| `base.politics` | `PoliticsSystem` | `["base.population"]` | 9 |

## Success Criteria

- **SC-001**: 100% Content-Agnostic Driver: Engine core (`src/engine/simulator.py`) contains zero hardcoded system imports or gameplay rules.
- **SC-002**: Topological Graph Stability: `TopologicalSorter` guarantees deterministic system execution order on every tick.
- **SC-003**: Fast Startup: Scanning manifests, loading Python system modules, and resolving dependency graphs completes under 500ms.

## Assumptions & Dependencies

- **Assumption**: `ModManager` (`src/engine/mod_manager.py`) reads `mod.toml` via `rtoml`.
- **Dependency**: Python 3.10+ standard library `graphlib.TopologicalSorter` builds the execution graph.
