# OpenPower Engine

> **Status: Alpha / Prototype**
> Core simulation, loading, IPC, map rendering, and base gameplay systems are functional. AI, diplomacy, headless mode, and multiplayer are still in progress.

**OpenPower** is an open-source grand strategy game engine built in Python. It uses a data-oriented architecture with multiprocessing so the simulation can run in a background process while the UI stays responsive.

## What Works Today

- **Multiprocess simulation:** The main UI runs separately from the simulation process.
- **IPC state transfer:** Game state is transferred with Arrow IPC / Polars data frames.
- **Dynamic module loading:** The engine loads gameplay content from `modules/` through mod manifests and registration entry points.
- **Base world loading:** Regions, countries, and other world data are loaded from TSV and TOML files.
- **Map rendering:** The client includes GPU-backed map rendering, political overlays, and region picking.
- **Core gameplay systems:** Time, population, politics, trade, internal economy, and budget systems are present.

## In Progress

- **AI:** Present as a stub; strategic decision-making is not implemented yet.
- **Military:** Build and manpower scaffolding exists, but combat and movement are not implemented.
- **Diplomacy:** Treaty, war, and peace systems are not implemented yet.
- **Headless server:** The simulation still expects the current client/server flow.
- **Mod data chaining:** `mods.json` integration is still stubbed in config.

## Project Structure

```text
OpenPower/
├── modules/              # Game content and mods
│   └── base/             # Core game module
│       ├── data/         # TSV/TOML/Parquet data files
│       └── systems/      # Gameplay systems
├── user_data/            # Local saves, logs, and user configs
├── src/
│   ├── client/           # Frontend, rendering, and UI
│   ├── engine/           # Simulation orchestration
│   ├── server/           # State, persistence, and session lifecycle
│   └── shared/           # Shared contracts, config, actions, and events
└── main.py               # Application entry point
```

## Tech Stack

- **Logic:** Python 3.10+
- **Data:** Polars
- **Graphics:** Arcade / OpenGL
- **Interface:** Dear ImGui via imgui_bundle
- **Serialization:** Orjson and RToml

## Getting Started

### Requirements

Install Python 3.10 or newer.

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run

```bash
python main.py
```

## Roadmap Snapshot

1. **Stable core:** Mostly in place. Simulation, loading, rendering, and the economy stack work.
2. **World content:** The base world dataset exists, but balance and coverage still need verification.
3. **Multiplayer beta:** Not implemented yet.

## License

This project is licensed under the **PolyForm Noncommercial License 1.0.0**. See [LICENSE.md](LICENSE.md) for details.
