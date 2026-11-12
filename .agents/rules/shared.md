

# Shared Layer (Data Contracts & Constants)

The Shared layer is the **Passive Data Dictionary** of the project. It contains only definitions, types, and constants used to communicate between layers.

## 🎯 Responsibilities
* **Data Contracts:** Defining the structure of `GameAction` (commands) and `GameEvent` (signals) used across the IPC boundary.
* **Simulation State Container:** `GameState`, `TimeData`, and `GAME_EPOCH` live here so all layers (engine, modules, client, server) can reference the type without circular dependencies.
* **Configuration:** `GameConfig` schemas and path resolution logic (abstracts paths, but doesn't load files).
* **Type Definitions:** Python `Protocols` and `Dataclasses` used for type hinting across the project.
* **Metadata Dictionaries:** Mapping keys to human-readable info (e.g., `RESOURCE_MAPPING` in `economy_meta.py`).
* **Global Constants:** Fixed values like `GAME_EPOCH`, `MAX_PLAYERS`, or `VERSION`.

## 🛡️ The Golden Rule
**No Logic allowed.** `shared` must remain a "leaf node" in the dependency tree.
If it calculates something, move it to `src/core`. If it holds state at runtime, note that `GameState` is a *container definition*, not runtime state (the instance lives in `src/server`).

| ✅ Correct Usage | ❌ Incorrect Usage |
| :--- | :--- |
| Defining `class ActionMove(GameAction): ...` | Implementing `SimulationTimer` (Move to `src/core`). |
| Defining `class GameState(dataclass): ...` | Calculating actual taxes (Move to `modules`). |
| Defining `const GAME_EPOCH = datetime(2001, 1, 1)` | Importing `Engine` to type-hint a function. |
| Defining a Protocol `class IUnit(Protocol): ...` | Storing the live game instance (Move to `src/server`). |

## 🔗 Relationships
* **Imports from:**
    * Python Standard Library (`typing`, `dataclasses`, `pathlib`, `datetime`).
    * Established shared-data dependencies `polars`, `numpy`, `pycountry`, and `rtoml`.
    * **ABSOLUTELY NOTHING** from `core`, `client`, `server`, `engine`, `simulation`, `modding`, or `modules`.
* **Used by:**
    * **EVERYONE:** `client`, `server`, `engine`, `core`, and `modules` all depend on `shared` to speak the same language.
* **NEVER imports:**
    * Any other OpenPower layer. Import Linter includes imports under `TYPE_CHECKING` when checking this rule.
