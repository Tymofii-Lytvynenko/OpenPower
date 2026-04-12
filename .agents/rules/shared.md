# Shared Layer (Data Contracts & Constants)

The Shared layer is the **Passive Data Dictionary** of the project. It contains only definitions, types, and constants used to communicate between layers.

## 🎯 Responsibilities
* **Data Contracts:** Defining the structure of `GameAction` (commands) and `GameEvent` (signals).
* **Configuration:** `GameConfig` schemas and path resolution logic (abstracts paths, but doesn't load files).
* **Type Definitions:** Python `Protocols` and `Dataclasses` used for type hinting across the project.
* **Global Constants:** Fixed values like `GAME_EPOCH`, `MAX_PLAYERS`, or `VERSION`.

## 🛡️ The Golden Rule
**No Logic allowed.** `shared` must remain a "leaf node" in the dependency tree.
If it calculates something, move it to `src/core`. If it holds state, move it to `src/server`.

| ✅ Correct Usage | ❌ Incorrect Usage |
| :--- | :--- |
| Defining `class ActionMove(GameAction): ...` | Implementing `SimulationTimer` (Move to `src/core`). |
| Defining `const MAX_TAX_RATE = 1.0` | Calculating actual taxes (Move to `modules`). |
| Defining a Protocol `class IUnit(Protocol): ...` | Importing `Engine` to type-hint a function. |

## 🔗 Relationships
* **Imports from:**
    * Python Standard Library (`typing`, `dataclasses`, `pathlib`).
    * **ABSOLUTELY NOTHING** from `core`, `client`, `server`, `engine`, or `modules`.
* **Used by:**
    * **EVERYONE:** `client`, `server`, `engine`, `core`, and `modules` all depend on `shared` to speak the same language.
* **NEVER imports:**
    * Any other layer. Importing anything else here will cause immediate **Circular Dependency** errors.