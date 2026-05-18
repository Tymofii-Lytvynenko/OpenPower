# 🪐 OpenPower Engine

> **Status: Alpha / Active Prototype**
> Asynchronous simulation runner, multi-process IPC, GPU-backed map rendering, declarative AI framework, geo-coordinate military unit movement, and alliance treaty systems are fully functional. Tactical combat, headless server, and multiplayer are in progress.

**OpenPower** is a high-performance, open-source grand strategy game engine built in Python. It utilizes a data-oriented design powered by **Polars** and a multi-process architecture to run intensive world simulation loops asynchronously in a background thread while keeping the **Dear ImGui / Arcade** frontend running at fluid, stutter-free framerates.

---

## 🚀 What Works Today

* **Asynchronous Multi-Process Core:** The main graphics engine/UI and the simulation runner (`Engine`) run in isolated processes, communicating via zero-copy Arrow IPC state transfers.
* **Declarative Polars AI Framework:** A data-oriented AI orchestration engine (`src/engine/ai_framework.py`) powered by Polars lazy execution graphs. Implements functional scorers for financial survival auditing (burn rates, months to bankruptcy) and vectorized military ROI scoring.
* **Geo-Coordinated Military Movement:** Active military system supporting real-time unit movements across the globe. Calculates equirectangular-to-spherical coordinates, tracking path distances and interpolating movement progress smoothly via SLERP (Spherical Linear Interpolation).
* **Interactive Unit Renderer & Atlas:** Billboard-based unit projection batching (`src/client/renderers/unit_batch_renderer.py`) and texture atlas optimization (`src/client/renderers/unit_flag_atlas.py`) that clusters overlapping units into stacks and supports interactive mouse drags to order troop movements.
* **Treaty & Alliance Systems:** Authorization database for military alliances, defensive pacts, and ongoing conflicts (`countries_wars.toml`, `countries_treaties.toml`).
* **Empire Mode Map Overlay:** A superpower-style political map overlay representing diplomatic alliances, defensive treaties, and wars with highly polished, dynamic hues (selected country in green, allies in blue, enemies in red, and neutral states in charcoal).
* **Dynamic Mod Loader:** Scans `modules/` for dynamic system registration, loading world datasets (regions, countries, demographics, resources) from TSV and TOML files on startup.

---

## 🛠️ In Progress & Roadmap

1. **Tactical Combat Resolution:** Active unit combat algorithms, frontline dynamics, and occupation resolution.
2. **Headless Server & Multiplayer:** Headless execution drivers and network communication protocols.
3. **Advanced Diplomacy Systems:** Action vectors for negotiating peace, demanding territory, and forming coalitions.
4. **Mod Data Chaining:** Configuration logic for multi-mod dependency chaining (`mods.json`).

---

## 📂 Project Structure

```text
OpenPower/
├── modules/                   # Game content, assets, and mod systems
│   └── base/                  # Core game module
│       ├── data/              # TSV/TOML datasets (countries, regions, world rules)
│       └── systems/           # Modular gameplay simulation systems
│           ├── demographics/  # Birth, death, and population growth
│           ├── economy/       # Industrial scaling and taxes
│           ├── military/      # Units, building, and movement loops
│           ├── politics/      # Government types and approvals
│           └── world/         # Declarative AI policies and time system
├── src/                       # Engine source code
│   ├── client/                # UI, view controllers, and GPU batch renderers
│   ├── core/                  # Math, coordinate conversions, and static paths
│   │   └── map/
│   │       └── geo.py         # Earth equirectangular & spherical projections
│   ├── engine/                # Content-agnostic ECS simulation driver
│   ├── server/                # State container, Arrow IPC, and session lifecycle
│   └── shared/                # Universal contracts, schemas, actions, and events
├── user_data/                 # Saved games, local session profiles, and logs
├── requirements.txt           # Python dependency specifications
└── main.py                    # Application launcher
```

---

## 💻 Tech Stack

* **Programming Language:** Python 3.10+
* **Data Processing:** Polars (Rust-backed DataFrame engine)
* **Graphics Backend:** Arcade / Modern OpenGL
* **User Interface:** Dear ImGui (via `imgui_bundle`)
* **Serialization & Parsing:** Orjson & RToml
* **Mathematics:** NumPy & Standard Math

---

## 🚦 Getting Started

### Installation
Ensure Python 3.10 or newer is installed on your system.

```bash
# Clone the repository and install dependencies
pip install -r requirements.txt
```

### Execution
Run the engine via the entry point:
```bash
python main.py
```

---

## 📄 License

This project is licensed under the **PolyForm Noncommercial License 1.0.0**. See [LICENSE.md](LICENSE.md) for details.
