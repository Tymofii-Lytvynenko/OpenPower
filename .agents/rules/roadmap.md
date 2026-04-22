# OpenPower MVP Roadmap

This document tracks the progress of the Minimum Viable Product (MVP) features for the OpenPower engine.

## 🗺️ System Status

- [x] **Core Architecture**
    - [x] Multiprocessing IPC bridge (Main Process <-> Simulation Process).
    - [x] Zero-Copy Arrow IPC serialization for Polars DataFrames.
    - [x] Background simulation loop with target TPS (Ticks Per Second).

- [x] **Data Management**
    - [x] Dynamic Module/Mod discovery.
    - [x] Parallel loading of TSV (Polars), Parquet, and TOML data.
    - [x] Static asset registry and path resolution.

- [x] **Map & Graphics Engine**
    - [x] GPU-accelerated region rendering (Shaders).
    - [x] Dynamic political and economic map modes.
    - [x] High-speed pixel-perfect picking for region interaction.

- [x] **Gameplay Systems (Base Module)**
    - [x] **Time:** Precise tick-to-date conversion and simulation speed control.
    - [x] **Economy:** Resource production (TOML-based), taxation, and money reserves.
    - [x] **Territory:** Region ownership, annexation, and core/non-core mechanics.
    - [x] **Population:** Basic population tracking per region.

- [ ] **Upcoming Features (In Progress)**
    - [ ] **AI System:** Country-level strategic agents using a decision-making framework.
    - [ ] **Diplomacy:** Formal treaties, trade agreements, and war/peace declarations.
    - [ ] **Advanced Economy:** Global trade network simulation and market prices.
    - [ ] **Headless Server:** Ability to run the simulation process without an OpenGL context.
    - [ ] **Military:** Unit spawning, movement, and combat resolution.

## 🎯 Target Milestones
1.  **Milestone 1 (Stable Core):** All systems functional in single-player with basic AI.
2.  **Milestone 2 (World Content):** Full world map (195+ countries, 3000+ regions) with balanced starting data.
3.  **Milestone 3 (Multiplayer Beta):** Network bridge for multi-client synchronization.
