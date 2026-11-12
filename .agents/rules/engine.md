

# Engine Layer (Simulation Runner)

The Engine is the generic machinery that orchestrates the execution of the simulation. It is the "CPU" of the game world.

## 🎯 Responsibilities
* **ECS Orchestration:** Managing the System Dependency Graph and executing `ISystem.update()` in topological order.
* **Simulation Loop:** Driving the `step()` cycle (Process Inputs -> Update Systems -> Dispatch Events).
* **Mod Discovery:** Scanning `modules/` via `ModManager` to register systems dynamically.

## 🛡️ The Golden Rule
The Engine must remain **content-agnostic**. It knows *how* to run a system, but not *what* the system does.

**Note:** The Engine runs inside the **Simulation Process**. It is designed to be highly deterministic and performance-focused, processing ticks independently of the UI frame rate.

| ✅ Correct Usage | ❌ Incorrect Usage |
| :--- | :--- |
| Calling `system.update(state, dt)` generically. | Hardcoding logic like `if system.id == "economy": ...`. |
| Using `core.profiler` to measure tick duration. | Importing `arcade` or `imgui` (No UI allowed). |
| Sorting systems based on `dependencies`. | Defining gameplay rules (e.g., population growth). |

## 🔗 Relationships
* **Imports from:**
    * `src/shared`: To handle Actions, Events, and `GameState` (now lives in `src.shared.state`).
    * `src/core`: To use `SimulationTimer`, generic Algorithms, and Logging.
* **Used by:**
    * `src/server`: The Session instantiates and owns the Engine within the background process.
* **NEVER statically imports:**
    * `src/server`, `src/client`, `src/simulation`, `src/modding`, or `modules`.
    * `ModManager` may dynamically load only the module registration entry point at the audited composition site. This does not permit static dependencies on gameplay modules.

The engine's default save migration belongs in `src/core`; server-facing compatibility exports must not reverse the dependency direction.
