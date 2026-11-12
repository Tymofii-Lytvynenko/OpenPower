<!-- Project policy is maintained here under the amendment procedure below. -->

# OpenPower Engine Project Constitution

**Version:** 1.2.0
**Ratification Date:** 2026-07-22  
**Last Amended Date:** 2026-11-12

---

## Executive Summary

The **OpenPower Engine** is a high-performance, open-source grand strategy game engine built in Python. This Constitution defines the fundamental non-negotiable architectural principles, layer boundary rules, database schema standards, engineering discipline, coding standards, and governance processes governing all code, modules, and contributions across the OpenPower repository.

---

## Core Architectural Principles

### Principle 1: Strict Layer Separation & Passive Client Architecture

Code in OpenPower MUST strictly follow the layer separation hierarchy defined below. No cross-layer violations or illegal imports are permitted under any circumstances.

#### 1.1 Shared Layer (`src/shared`) — Data Contracts & Constants
- **Role**: The **Passive Data Dictionary** of the project. Contains definitions, types, schemas, and global constants (`actions.py`, `events.py`, `config.py`, `economy_meta.py`).
- **Golden Rule**: **No Logic allowed.** `shared` MUST remain a "leaf node" in the dependency tree.
- **Imports Allowed**: Python Standard Library and the established shared-data dependencies `polars`, `numpy`, `pycountry`, and `rtoml`. External libraries do not permit imports from another OpenPower layer.
- **NEVER Imports**: Any other layer (`core`, `client`, `server`, `engine`, `modules`).

#### 1.2 Core Layer (`src/core`) — Game Framework & SDK
- **Role**: Reusable mechanisms, SDK algorithms, math, spatial projections, and base tools (`geo.py`, `cache_service.py`, `map_data.py`, `map_indexer.py`, `paths.py`).
- **Golden Rule**: Code in `core` provides **Mechanisms**, not **Policy**. It gives the tool to calculate time or geometry, but does not make gameplay policy decisions.
- **Imports Allowed**: `src/shared`.
- **NEVER Imports**: `src/engine`, `src/client`, `src/server`, or `modules`.

#### 1.3 Engine Layer (`src/engine`) — Simulation Runner
- **Role**: Content-agnostic machinery orchestrating the execution of simulation systems (`simulator.py`, `mod_manager.py`, `ai_framework.py`).
- **Golden Rule**: The Engine MUST remain **content-agnostic**. It knows *how* to run a system in topological order via `graphlib.TopologicalSorter`, but not *what* a system does.
- **Imports Allowed**: `src/shared`, `src/core`, and the Engine's own components.
- **NEVER Imports**: `src/server`, `src/client`, `src/simulation`, `src/modding`, or `modules`. Runtime mod loading is a narrow dynamic composition point and does not authorize static imports of game content.

#### 1.4 Server Layer (`src/server`) — State & Persistence
- **Role**: Authoritative state container (`GameState`), loading/saving, and Arrow IPC serialization (`session.py`, `state.py`, `server_process.py`, `io/`).
- **Golden Rule**: The Server cares about **Data Integrity**, not Data Processing. It ensures data is valid when loaded, but does not simulate changes over time. Lives in background process.
- **Imports Allowed**: `src/shared`, `src/core`, `src/engine`.
- **NEVER Imports**: `src/client`, `src/simulation`, `src/modding`, or concrete `modules` packages. The server may compose shared, core, and Engine services.

#### 1.5 Client Layer (`src/client`) — Presentation & User Interaction
- **Role**: Visualizing `GameState` using shaders (Arcade/OpenGL) and UI components (ImGui), capturing user input and dispatching semantic `GameActions` (`window.py`, controllers, renderers, views, panels).
- **Golden Rule**: The Client is a **passive observer**. It MUST NEVER modify `GameState` directly. It visualizes IPC data snapshots and dispatches intent (`GameAction`) across IPC.
- **Imports Allowed**: `src/shared`, `src/core`, and the Client's own presentation components. The client receives a read-only `ClientGameStateView` over decoded snapshots.
- **NEVER Imports**: `src/engine`, `src/server`, `src/simulation`, `src/modding`, or `modules`. Application composition in `main.py` or `src/cli.py` starts the local server and connects it to the Client.

#### 1.6 Module Layer (`modules`) — Content & Gameplay Policy
- **Role**: Concrete implementations of `ISystem` (Demographics, Economy, Military, Politics, World AI), static datasets (TSV/TOML), and mod registrations (`registration.py`).
- **Golden Rule**: Code here represents **Policy**. Uses mechanisms from `src/core` to implement game rules inside the simulation process. Has no direct access to UI/Window context.
- **Imports Allowed**: `src/shared`, `src/core`, the module's own package, and only other modules explicitly declared in its `mod.toml` dependencies.
- **NEVER Imports**: `src/engine` (including interfaces; public system contracts live in `src/shared`), `src/server`, `src/client`, `src/simulation`, or `src/modding`.

#### 1.7 Composition and Tooling
- `main.py` and `src/cli.py` are application composition points. `src/modding` and `src/simulation` are tooling and headless composition namespaces; they must not become production-layer dependencies.
- Dynamic imports are permitted only at named composition points for Engine module registration and the versioned client presentation extension. Other dynamic imports are prohibited in production Python code.
- Cross-module imports require an explicit dependency in the importing module's `mod.toml`; module dependency cycles are prohibited.

#### 1.8 Executable Architecture Contracts
- Import Linter enforces transitive layer boundaries, client/server independence, and protected Engine internals. Imports under `TYPE_CHECKING` remain part of the graph.
- Ruff checks Python defects, imports, and selected APIs. OpenPower AST checks enforce manifest dependencies, approved dynamic loaders, client snapshot passivity, and package coverage.
- `python -m tools.architecture_check` is the required local check. The `Architecture / validate` GitHub Actions status is the merge gate.

---

### Principle 2: Data-Oriented Simulation & Database Schemas

1. **Polars Data-Oriented Engine**:
   - High-performance world datasets (regions, countries, demographics, resources, military units) MUST be structured and processed as Polars DataFrames and zero-copy Apache Arrow IPC streams.

2. **Authoritative Table Schemas (DATA_SCHEMA.md)**:
   - **`regions` Table**: Primary key `id` (Int32 derived from hex `#RRGGBB`). Must include `hex`, `name`, `owner`, `iso_region`, `type`, `macro_region`, `area_km2`, `center_x`, `center_y`, `latitude`, `longitude`, `pop_14`, `pop_15_64`, `pop_65`.
   - **`countries` Table**: Primary key `id` (ISO 3-letter string). Must include `money_reserves`, `personal_income_tax_rate`, `industrial_growth_rate`, `gvt_stability`, `gvt_corruption`, `gvt_approval`, `military_count`, `human_dev`, `poverty_rate`, `fertility_rate`, `life_expectancy`, `budget_*` ratios.
   - **`units` Table**: Primary key `id` (`{CountryTag}-{UnitType}-{Index:03d}`). Must include `owner`, `unit_type`, `strength`, `current_region_id`, `latitude`, `longitude`, `source_region_id`, `target_region_id`, `departed_at_minute`, `arrival_at_minute`, `movement_progress`, `is_moving`.
   - **`countries_relations` Table**: Directed matrix (`source`, `target`, `value` from -100 to 100).
   - **`countries_treaties` Table**: Treaty registry (`id`, `name`, `type`, `members`).
   - **`countries_wars` Table**: Active belligerents (`side_a`, `side_b`).
   - **`domestic_production` Table**: Commodity production (`country_id`, `game_resource_id`, `domestic_production`, `is_legal`, `is_gov_controlled`, `tax_rate`).

---

### Principle 3: Modular, Reusable, and SOLID Design ("Composition over Inheritance")

1. **Modularity & Composition**:
   - Developers MUST apply "composition over inheritance" and SOLID design principles across all layers.
   - Systems MUST be designed around single-responsibility interfaces (`ISystem`). Gameplay features MUST be added via dynamic module registration (`registration.py`) rather than modifying engine core loops.

---

### Principle 4: Professional Self-Documenting Code & Commenting Guidelines

1. **Self-Documenting Code**:
   - Code MUST be clear and self-documenting. Comments MUST explain the "why" (rationale, bug fix background, unidiomatic optimizations) and NEVER duplicate the code ("what").

2. **Explicit Commenting Rules (User Global Rules)**:
   - **If you can't write a clear comment, refactor the code**: Difficulty commenting signals unclear implementation.
   - **Explain unidiomatic code**: Non-standard idioms or performance optimizations MUST include explanatory comments and links to relevant specifications or documentation.
   - **External Links & Attribution**: Provide links to original sources for adapted code, documentation, issue trackers, or specifications.
   - **Bug Fix Annotation**: Fixes MUST include inline commentary explaining the nature of the bug, root cause, and rationale for the fix.
   - **Incomplete Markers**: Mark unfinished implementations using standard `TODO` or `FIXME` tags with actionable descriptions.

---

### Principle 5: Empirical Verification & Anti-Masking Discipline

1. **Empirical Verification**:
   - No task, feature, or bug fix MAY be declared complete without concrete, empirical runtime verification (successful build outputs, test execution, or clean log inspection).

2. **Anti-Masking & Root Cause Remediation**:
   - Developers and AI agents MUST NEVER mask runtime failures, swallow exceptions silently, return dummy fallback data, or delete failing tests to achieve superficial compliance.
   - Root causes MUST be traced upstream and fixed at the source data contract.

---

## Governance & Amendment Policy

1. **Amendment Procedure**:
   - Any change to this Constitution MUST follow a formal amendment proposal detailing the change, justification, and impact across all project layers.

2. **Versioning Policy**:
   - Semantic Versioning (`MAJOR.MINOR.PATCH`) MUST be applied to Constitution updates:
     - **MAJOR**: Backward-incompatible architectural changes, layer redefinitions, or removal/redefinition of core principles.
     - **MINOR**: Addition of new principles, layer rules, data schemas, or expanded guidelines.
     - **PATCH**: Non-semantic refinements, wording clarifications, or typo fixes.

3. **Compliance Review**:
   - Every proposal, feature specification, and implementation plan MUST include an explicit Constitution Check to ensure 100% alignment before execution.

---

## Formal Amendment 1.2.0 — Strict Architecture Contracts

**Date:** 2026-11-12
**Change:** Align the layer import rules with the audited OpenPower graph; remove Engine-to-Server and Modules-to-Engine dependencies; isolate the Client from Engine, Server, simulation tools, modding tools, and gameplay modules; require declared cross-module dependencies; and permit only the audited shared-data libraries listed in Principle 1.1. Add executable Import Linter, Ruff, and AST enforcement.

**Justification:** The previous text allowed dependencies already contradicted by the Engine rules and the actual runtime boundary. It also limited `src/shared` to the standard library despite established Polars, NumPy, pycountry, and rtoml usage. The amendment states the intended contracts directly and leaves the existing shared table/data behavior intact.

**Impact:** Save migration ownership now follows the lower-layer direction; the Client receives module-provided presentation helpers through a versioned shared API and a read-only snapshot view; test tooling is composed under `src/simulation`; and CI blocks future boundary regressions. No save format or simulation rules change.
