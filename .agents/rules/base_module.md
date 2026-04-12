# Modules (Content & Gameplay)

This is the **Game Layer**. Everything that makes "OpenPower" a specific game (and not just a generic engine) lives here.

## 🎯 Responsibilities
* **Gameplay Mechanics:** Concrete implementations of `ISystem` (Politics, Economy, AI).
* **Static Assets:** TSV data tables, map textures, audio, and localization files.
* **System Registration:** Defining entry points (`registration.py`) so the Engine can load the mod.

## 🛡️ The Golden Rule
Code here represents **Policy**. It uses the **Mechanisms** provided by `src/core` to implement game rules.

| ✅ Correct Usage | ❌ Incorrect Usage |
| :--- | :--- |
| Using `core.SimulationTimer` to calculate consumption. | Writing a custom `while` loop to manage time. |
| Reading `shared.ActionSetTax`. | Modifying `src/engine/simulator.py` to add a feature. |
| Emitting a `shared.EventNewDay`. | Importing `client` code to draw a custom UI panel. |

## 🔗 Relationships
* **Imports from:**
    * `src/shared`: To use Actions, Events, and define data schemas.
    * `src/core`: To use Standard Simulation Tools (Timers, Math) and Utils.
    * `src/engine` (Interfaces only): To implement `ISystem`.
* **Used by:**
    * `src/engine`: The Engine dynamically loads these modules.
* **NEVER imports:**
    * `src/engine` (Internals): Do not touch the loop logic.
    * `src/server`: Do not manually save files or touch the session.
    * `src/client`: Do not implement UI logic in the simulation.