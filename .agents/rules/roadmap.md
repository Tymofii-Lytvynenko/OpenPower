# OpenPower MVP Roadmap

This document tracks the progress of the Minimum Viable Product (MVP) features for the OpenPower engine.

## 🚦 System Status

- [x] **Core Architecture**
    - [x] Multiprocessing IPC bridge (Main Process <-> Simulation Process).
    - [x] Zero-Copy Arrow IPC serialization for Polars DataFrames.
    - [x] Background simulation loop with target TPS (Ticks Per Second).
    - [x] Main UI boots a separate server process and polls readiness/progress.

- [x] **Data Management**
    - [x] Dynamic Module/Mod discovery.
    - [x] Loading of TSV (Polars), Parquet, and TOML data for the base module.
    - [x] Static asset registry and path resolution.
    - [ ] Active mod data chaining from `mods.json` is still stubbed.

- [x] **Map & Graphics Engine**
    - [x] GPU-accelerated region rendering (Shaders).
    - [x] Dynamic political and economic map modes.
    - [x] High-speed pixel-perfect picking for region interaction.
    - [x] Client-side map data loading is integrated into the window/proxy flow.

- [ ] **Gameplay Systems (Base Module)**
    - [x] **Time:** Precise tick-to-date conversion and simulation speed control.
    - [x] **Economy:** Resource production, trade network, internal ledger, taxation, and money reserves.
    - [x] **Budget:** National budget calculations with revenue and expense tracking.
    - [x] **Politics:** Basic stability drift from approval/corruption metrics.
    - [x] **Population:** Basic population tracking per region.
    - [x] **Territory:** System entry point exists, but the mechanic is not yet substantively implemented.
    - [ ] **AI:** Present only as a stub; no real strategic decision-making yet.
    - [ ] **Military:** Partial build/manpower scaffolding exists; combat and movement are not implemented.
    - [ ] **Diplomacy:** No treaty, war, or peace system implemented yet.

- [ ] **Upcoming Features (In Progress)**
    - [ ] **AI System:** Country-level strategic agents using a decision-making framework.
    - [ ] **Diplomacy:** Formal treaties, trade agreements, and war/peace declarations.
    - [x] **Advanced Economy:** Trade network, consumption ledger, stockpiles, and budget flow are in place.
    - [ ] **Headless Server:** Ability to run the simulation process without an OpenGL context.
    - [ ] **Military:** Unit spawning, movement, and combat resolution.

## 🎯 Target Milestones
1.  **Milestone 1 (Stable Core):** Core simulation, IPC, loading, map rendering, economy, budget, politics, and population are functional in single-player. AI and military remain partial.
2.  **Milestone 2 (World Content):** Full world map and balanced starting data are being assembled; content volume is present, but balance and coverage still need verification.
3.  **Milestone 3 (Multiplayer Beta):** Network bridge for multi-client synchronization remains future work.
