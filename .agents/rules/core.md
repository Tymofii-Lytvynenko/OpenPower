# Core Layer (Game Framework & SDK)

The **Core** layer contains the functional building blocks and standardized algorithms used to build the game logic. Unlike `shared` (which is for passive data), `core` contains **active logic** that is safe to share between the Engine and Modules.

Think of this as the **Standard Library (SDK)** for OpenPower modders and engine developers.

## 🎯 Responsibilities
1.  **Simulation Standards:** The authoritative implementation of game time (`SimulationTimer`), identifying strictly how real seconds convert to game ticks.
2.  **Math & Physics:** Deterministic math utilities (e.g., coordinate conversions `Hex -> Pixel`, pathfinding heuristics) ensuring identical results across all modules.
3.  **Base Utilities:** Logging wrappers, ID generators, and performance profilers.
4.  **Component Logic:** Reusable logic blocks that don't fit into a specific System (e.g., a generic `InventoryContainer` logic).

## 🛡️ The Golden Rule
Code in `core` provides **Mechanisms**, not **Policy**.
It gives you the tool to "calculate time," but it doesn't decide "when the game ends."

| ✅ Correct Usage (In Core) | ❌ Incorrect Usage (Move to Modules/Engine) |
| :--- | :--- |
| **Tool:** `SimulationTimer` class that handles the math of time dilation. | **Policy:** A loop that calls `timer.update()` (belongs in `Engine`). |
| **Math:** A function `get_distance_between_hexes(a, b)`. | **Game Rule:** Logic that says "Units cannot move more than 2 hexes" (belongs in `MovementSystem`). |
| **Helper:** A standardized `Logger` class with color coding. | **State:** The variable `current_log_history`. |

## 🔗 Relationship with other layers
* **Imports from:** `src/shared` (It uses the data contracts).
* **Used by:** `src/engine` AND `modules`.
* **NEVER imports:** `src/engine`, `src/client`, `src/server`.