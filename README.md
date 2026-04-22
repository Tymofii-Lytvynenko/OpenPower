# OpenPower Engine

> **🏗️ Status: Alpha (In Active Development)**
> OpenPower is currently in the **prototype phase**. Core systems are functional, but networking and advanced AI are still being integrated.

**OpenPower** is a high-performance, open-source Grand Strategy Game (GSG) engine built in Python. It leverages **Data-Oriented Design** and **Multiprocessing** to simulate deep, complex worlds with thousands of actors without sacrificing UI responsiveness.

## 🚀 Key Features

*   **Multiprocess Simulation:** The simulation engine runs on a dedicated background CPU core, completely isolated from the UI rendering thread. This ensures zero frame drops during heavy calculations.
*   **Zero-Copy State Management:** Uses **Polars (Rust-backed DataFrames)** and **Arrow IPC** to transfer authoritative game state between processes with sub-millisecond overhead.
*   **Advanced Map Rendering:**
    *   **GPU-Accelerated:** Custom shaders for rendering thousands of regions with dynamic political and economic overlays.
    *   **Color-as-ID Pipeline:** High-speed map interaction using OpenCV and GPU picking.
*   **Modular ECS-Lite:** Systems (Economy, Politics, AI) are fully modular, dependency-aware, and support topological execution ordering.
*   **Professional UI:** Integration of **Dear ImGui** for a dockable, high-density dashboard experience.

## 📂 Project Structure

```text
OpenPower/
├── modules/                # Game Content & Mods
│   └── base/               # The core game module
│       ├── data/           # TSV/TOML/Parquet data files
│       └── systems/        # Gameplay logic (Economy, Population, etc.)
├── user_data/              # Local saves, logs, and user configs
├── src/
│   ├── client/             # Frontend (Arcade, Shaders, ImGui)
│   │   ├── client_session.py # Proxy that talks to the background server
│   │   ├── renderers/      # GPU-specific map & flag rendering
│   │   ├── ui/             # Panel managers & Composers
│   │   └── window.py       # Main Application Window
│   ├── engine/             # The "CPU" of the game
│   │   ├── mod_manager.py  # Dynamically loads systems from modules/
│   │   └── simulator.py    # Executes the System Dependency Graph
│   ├── server/             # Backend (State & Persistence)
│   │   ├── server_process.py # The background process entry point
│   │   ├── session.py      # Simulation lifecycle host
│   │   └── state.py        # Central Polars state container
│   └── shared/             # Common contracts (Actions, Events, Metadata)
└── main.py                 # Application Entry Point
```

## 🛠️ Tech Stack

*   **Logic:** Python 3.10+
*   **Data:** [Polars](https://pola.rs/) (Arrow-based DataFrames)
*   **Graphics:** [Arcade](https://api.arcade.academy/) (OpenGL 3.3+)
*   **Interface:** [ImGui Bundle](https://github.com/pthom/imgui_bundle) (Dear ImGui)
*   **Serialization:** [Orjson](https://github.com/ijl/orjson) & [RToml](https://github.com/samuelcolvin/rtoml)


## 🚀 Getting Started

### 1. Requirements
Ensure you have Python 3.10 or newer installed.

### 2. Installation
```bash
pip install -r requirements.txt
```

### 3. Run the Engine
```bash
python main.py
```

## 📜 License
This project is licensed under the **PolyForm Noncommercial License 1.0.0** - see [LICENSE.md](LICENSE.md) for details.