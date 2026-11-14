

# Client Layer (Frontend)

The Client is responsible for the **Presentation** and **User Interaction** layers of the application. It acts as the "Player's Terminal."

## 🎯 Responsibilities
* **Rendering:** Visualizing the `GameState` using shaders (Arcade/OpenGL) and UI components (ImGui).
* **Input Handling:** Capturing raw mouse/keyboard events and converting them into semantic `GameActions`.
* **View Management:** Managing screen transitions and states (MainMenu, GameView, EditorView).
* **Audio:** Triggering sounds and music based on `GameEvents` emitted by the Engine.
* **Process Communication:** Using `ClientSessionProxy` to communicate with the background Simulation Process.

## 🛡️ The Golden Rule
The Client is a **passive observer**. It must never modify the `GameState` directly. It visualizes data from the Server and sends intent (`GameAction`) to the Session.

**Note:** The Client lives in the **Main Thread/Process**. It receives snapshots of the `GameState` via IPC (Inter-Process Communication). Any data shown in the UI is a copy, not the original simulation data.

| ✅ Correct Usage | ❌ Incorrect Usage |
| :--- | :--- |
| Reading `state.get_table("regions")` for map coloring. | Writing `state.tables["regions"][id] = value`. |
| Dispatching an `ActionSetTax` command. | Calculating tax revenue logic inside a UI button. |
| Using `core.math` to interpolate unit movement. | Implementing pathfinding logic (belongs in Engine/Modules). |
| Rendering the read-only `ClientGameStateView` supplied by `ClientSessionProxy`. | Calling `GameState.update_table()` or mutating snapshot tables/globals. |

## 🔗 Relationships
* **Imports from:**
    * `src/shared`: To use Actions, Events, Config, and shared contracts.
    * `src/core`: To use universal math utils, color generators, or `list_available_saves`.
    * Its own client components.
* **Used by:** The application composition point (`main.py`), which connects the Client proxy to the local server.
* **NEVER imports:**
    * `src/engine`: The Client should not know how the simulation loop works.
    * `src/server`: server startup and lifecycle belong to application composition, not Client code.
    * `src/simulation`, `src/modding`, and `modules`: the Client consumes a versioned presentation contribution through its own API and must not import gameplay implementation.

Import Linter checks transitive dependencies. Client snapshot views are read-only; UI-only settings belong in `ClientPresentationState`.
