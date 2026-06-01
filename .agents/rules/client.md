

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
| Calling `spawn_local_server(config)` from `MainWindow` or a loading task. | Constructing `ClientSessionProxy` directly or importing `run_server_process`. |

## 🔗 Relationships
* **Imports from:**
    * `src/shared`: To use Actions, Events, Config, and `GameState` (for type hints and `from_ipc`).
    * `src/core`: To use universal math utils, color generators, or `list_available_saves`.
    * `src/server` (**Launcher only**): `MainWindow` and loading tasks may call `spawn_local_server` from `src.server.launcher`. This is the **only** permitted server import in the client layer.
* **Used by:** The entry point (`main.py`).
* **NEVER imports:**
    * `src/engine`: The Client should not know how the simulation loop works.
    * `src/server` (internals): No imports of `GameSession`, `DataLoader`, `SaveWriter`, `DataExporter`, `server_process`, `state_bootstrap`, or any `src/server/io` module.
    * `modules`: The Client must not depend on specific game content code.