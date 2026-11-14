---
trigger: always_on
---

# Modules (Content & Gameplay)

This is the **Game Layer**. Everything that makes "OpenPower" a specific game (and not just a generic engine) lives here.

## 🎯 Responsibilities
* **Gameplay Mechanics:** Concrete implementations of `ISystem` (Politics, Economy, AI).
* **Static Assets:** TSV data tables, map textures, audio, and localization files.
* **System Registration:** Defining entry points (`registration.py`) so the Engine can load the mod.

## 🛡️ The Golden Rule
Code here represents **Policy**. It uses the **Mechanisms** provided by `src/core` to implement game rules.

**Note:** Modules are loaded and executed within the **Simulation Process**. They have no direct access to the UI/Window context. They communicate with the player exclusively through `GameEvents` and by modifying the `GameState`.

| ✅ Correct Usage | ❌ Incorrect Usage |
| :--- | :--- |
| Using `core.SimulationTimer` to calculate consumption. | Writing a custom `while` loop to manage time. |
| Reading `shared.ActionSetTax`. | Modifying `src/engine/simulator.py` to add a feature. |
| Emitting a `shared.EventNewDay`. | Importing `client` code to draw a custom UI panel. |

## 🔗 Relationships
* **Imports from:**
    * `src/shared`: To use Actions, Events, `ISystem`, `SystemAccess`, `ModContribution`, and define data schemas.
    * `src/core`: To use Standard Simulation Tools (Timers, Math) and Utils.
    * Its own package and other modules only when the dependency is declared in this module's `mod.toml`.
* **Used by:**
    * `src/engine`: The Engine dynamically loads these modules within the background process.
* **NEVER imports:**
    * Any `src/engine` module: public system contracts live in `src/shared`; do not touch engine internals.
    * `src/server`, `src/client`, `src/simulation`, or `src/modding`.

Cross-module imports must have a direct manifest dependency; transitive dependencies are not sufficient. Module dependency cycles are rejected.
