# Engine Layer (Simulation Runner)

The Engine is the generic machinery that orchestrates the execution of the simulation. It is the "CPU" of the game world.

## 🎯 Responsibilities
* **ECS Orchestration:** Managing the System Dependency Graph and executing `ISystem.update()` in topological order.
* **Simulation Loop:** Driving the `step()` cycle (Process Inputs -> Update Systems -> Dispatch Events).
* **Mod Discovery:** Scanning `modules/` via `ModManager` to register systems dynamically.

## 🛡️ The Golden Rule
The Engine must remain **content-agnostic**. It knows *how* to run a system, but not *what* the system does.

| ✅ Correct Usage | ❌ Incorrect Usage |
| :--- | :--- |
| Calling `system.update(state, dt)` generically. | Hardcoding logic like `if system.id == "economy": ...`. |
| Using `core.profiler` to measure tick duration. | Importing `arcade` or `imgui` (No UI allowed). |
| Sorting systems based on `dependencies`. | Defining gameplay rules (e.g., population growth). |

## 🔗 Relationships
* **Imports from:**
    * `src/shared`: To handle Actions and Events.
    * `src/core`: To use `SimulationTimer`, generic Algorithms, and Logging.
    * `src/server`: To manipulate the `GameState` object during the tick.
* **Used by:**
    * `src/server`: The Session instantiates and owns the Engine.
* **NEVER imports:**
    * `src/client`: The Engine must run even on a headless server.
    * `modules`: No hard dependencies on specific content (e.g., "base" mod).