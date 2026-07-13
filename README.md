# 🪐 OpenPower Engine

> **Status: Alpha / Active Prototype**
> The project includes an asynchronous simulation runner, headless execution, tactical combat, geo-coordinate movement, mod-layered data loading, and a server-authoritative diplomacy system. Multiplayer remains future work.

**OpenPower** is a high-performance, open-source grand strategy game engine built in Python. It utilizes a data-oriented design powered by **Polars** and a multi-process architecture to run intensive world simulation loops asynchronously in a background thread while keeping the **Dear ImGui / Arcade** frontend running at fluid, stutter-free framerates.

---

## 🚀 What Works Today

* **Asynchronous Multi-Process Core:** The UI and authoritative simulation run in isolated processes, exchanging acknowledged Arrow IPC snapshots with table-level deltas.
* **Declarative Polars AI Framework:** A data-oriented AI orchestration engine (`src/core/ai_framework.py`) powered by Polars lazy execution graphs. Implements functional scorers for financial survival auditing (burn rates, months to bankruptcy) and vectorized military ROI scoring.
* **Geo-Coordinated Military Movement:** Active military system supporting real-time unit movements across the globe. Calculates equirectangular-to-spherical coordinates, tracking path distances and interpolating movement progress smoothly via SLERP (Spherical Linear Interpolation).
* **Interactive Unit Renderer & Atlas:** Billboard-based unit projection batching (`src/client/renderers/unit_batch_renderer.py`) and texture atlas optimization (`src/client/renderers/unit_flag_atlas.py`) that clusters overlapping units into stacks and supports interactive mouse drags to order troop movements.
* **Treaty & Alliance Systems:** Authorization database for military alliances, defensive pacts, and ongoing conflicts (`countries_wars.toml`, `countries_treaties.toml`).
* **Empire Mode Map Overlay:** A political map overlay representing diplomatic alliances, defensive treaties, and wars with highly polished, dynamic hues (selected country in green, allies in blue, enemies in red, and neutral states in charcoal).
* **Versioned Mod Runtime:** Resolves `modules/` manifests and composes systems, table schemas, layered data, and sequential save migrations through a strict Mod API.
* **Deterministic Simulation Contracts:** Fixed-step ticks, persisted RNG/ID state, command sequencing, atomic rollback, and a durable domain-event journal support replayable debugging.

---

See [Modding API](docs/MODDING.md) for concise module registration and
[Runtime Architecture](docs/ARCHITECTURE.md) for extension and debugging contracts.
The executable reference module lives in `modules/energy_crisis`.

```powershell
openpower mod validate energy_crisis
openpower sim run --mods energy_crisis --days 30 --seed 42 --player UKR --actions modules/energy_crisis/scenarios/policy_response.json
openpower sim compare --mods energy_crisis --days 30 --seed 42 --player UKR --actions modules/energy_crisis/scenarios/policy_response.json
```

## 🛠️ In Progress & Roadmap

1. **Multiplayer transport:** Dedicated remote-session hosting, authentication, and reconnection.
2. **Combat depth:** More unit roles, logistics, frontlines, and battle strategy controls.
3. **Diplomacy balancing:** UI feedback and data balancing for treaty maintenance, market effects, and AI choices.

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
├── pyproject.toml             # Project metadata and dependencies
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

#### Recommended (Editable Install)

```bash
pip install -e .
```

#### Development Dependencies

```bash
pip install -e .[dev]
```

### Execution

Run via the installed entrypoint:

```bash
openpower
```

Or directly:

```bash
python main.py
```

---

## 📄 License

This project is licensed under the **PolyForm Noncommercial License 1.0.0**. See [LICENSE.md](LICENSE.md) for details.
