# Server Layer (State & Persistence)

The Server is the "Source of Truth" and handles the lifecycle of the data. It acts as the Host (even in single-player).

## 🎯 Responsibilities
* **State Container:** Holding the authoritative `GameState` instance.
* **Persistence (I/O):** Loading static assets (TSV) and saving/loading user sessions (Parquet/JSON).
* **Session Lifecycle:** Assembling the game (connecting Engine, Loader, and State) via `GameSession`.
* **Atomic Writes:** Ensuring save files are written safely to disk to prevent corruption.

## 🛡️ The Golden Rule
The Server cares about **Data Integrity**, not Data Processing. It ensures data is valid when loaded, but it does not simulate changes over time.

| ✅ Correct Usage | ❌ Incorrect Usage |
| :--- | :--- |
| Parsing TSV files into Polars DataFrames. | Storing textures or Arcade objects in `GameState`. |
| Sanity checking data (e.g., `tax_rate` is 0.0-1.0). | Increasing population count inside the loader. |
| Initializing the `Engine` instance. | Listening for keyboard inputs directly. |

## 🔗 Relationships
* **Imports from:**
    * `src/shared`: Contracts and Config.
    * `src/core`: File utils, ID generators.
    * `src/engine`: To instantiate the simulation driver.
* **Used by:**
    * `src/client`: The Client requests the `GameState` snapshot for rendering.
* **NEVER imports:**
    * `src/client`: The Server must not know about the UI.