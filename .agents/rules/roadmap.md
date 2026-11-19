# OpenPower MVP Roadmap

This document tracks the progress of the Minimum Viable Product (MVP) features for the OpenPower engine.

## First Playable Readiness — 2026-11-18

- The direct no-scenario freeplay launch, representative time/economy/politics/military/diplomacy loop, rejection feedback, and freeplay save/resume are implemented and pass their local automated acceptance checks.
- English is the accepted first-release language. Network multiplayer and editor work are outside the single-player First Playable scope.
- Native map appearance and interaction, target-hardware/long-run performance, graphical module combinations, historical source-by-source fact checking, and participant-based visual acceptance still need external evidence.
- See [the audit closure record](../../docs/first-playable-audit-closure.md) and [the detailed verification record](../../specs/122-freeplay-core-loop-and-system-polish/research.md).

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
    - [x] **Territory:** Owner and controller changes are processed for annex, occupy, and set-owner actions; broader occupation and political-progression depth remains in progress.
    - [x] **AI:** Functional `DeclarativeAIFramework` using Polars lazy evaluation. Implements financial survival scoring and military ROI scoring. Produces `ActionUpdateBudget` and `ActionBuildUnit` intents every real second.
    - [x] **Military:** Unit spawning, geo-coordinated movement, combat resolution, and occupation actions are implemented. Broader battle and campaign depth remains in progress.
    - [x] **Diplomacy:** Registered systems process treaty proposals and lifecycle, treaty effects, war actions, and structured peace deals. Balancing and full gameplay coverage remain in progress.

- [ ] **Upcoming Features (In Progress)**
    - [ ] **AI System:** Country-level strategic agents using a decision-making framework.
    - [ ] **Diplomacy:** Further balance treaty effects, trade agreements, and war/peace feedback across complete player flows.
    - [x] **Advanced Economy:** Trade network, consumption ledger, stockpiles, and budget flow are in place.
    - [x] **Headless Server:** The simulation runs in a separate server process without an OpenGL context.
    - [ ] **Military:** Expand combat depth with more unit roles, logistics, frontlines, and battle strategy controls.

## 🎯 Target Milestones
1.  **Milestone 1 (Stable Core):** Core simulation, IPC, loading, map rendering, economy, budget, politics, and population are functional in single-player. AI and military remain partial.
2.  **Milestone 2 (World Content):** Full world map and balanced starting data are being assembled; content volume is present, but balance and coverage still need verification.
3.  **Milestone 3 (Multiplayer Beta):** Network bridge for multi-client synchronization remains future work.
