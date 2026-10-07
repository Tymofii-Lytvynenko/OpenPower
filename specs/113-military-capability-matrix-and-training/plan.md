# Implementation Plan: Military Capability Matrix and Training

**Branch**: `113-military-capability-matrix-and-training` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification at `specs/113-military-capability-matrix-and-training/spec.md`

## Summary

Complete the data-driven military role and capability model around the existing unit, research, production, readiness, tactical-combat, intelligence, and persistence contracts. Preserve the current table-oriented simulation and two-side combat lifecycle. The remaining audit gaps are foreign force estimates exposed from authorized, freshness-aware intelligence; explicit training-site eligibility and persistence details; and bounded, interaction-aware battle projections. Add a controlled incremental-update benchmark for SC-007, with no more than three measured algorithm-optimization iterations; if the gate remains unmet after the third, document the attempts and defer it while functional work continues.

## Technical Context

**Language/Version**: Python 3.10+ (repository runtime currently uses Python 3.14 for the local test environment).

**Primary Dependencies**: Polars 1.36.1 for authoritative state tables, NumPy only for temporary numeric buffers when justified, pytest, Arcade/OpenGL, and imgui-bundle for the existing desktop client.

**Storage**: `GameState.tables` with canonical Polars schemas registered by `modules/base/schema.py`; existing save/load, IPC snapshots, and replay preserve state tables.

**Testing**: `.venv\Scripts\python.exe -m pytest` for focused unit/integration tests. Controlled opt-in performance tests use deterministic fixtures and report the SC-007 threshold separately from correctness.

**Target Platform**: Existing Windows desktop and headless simulation runtime.

**Project Type**: Modular Python game engine with server-authoritative gameplay systems and passive desktop UI.

**Performance Goals**: SC-007 requires updating 50,000 units and 10,000 designs with 5% changed records in under 1 second. Performance work is subordinate to feature correctness and limited to three measured algorithm-optimization iterations per gate.

**Constraints**: Keep policy in `modules/base`, schemas/actions in `src/shared` or registered module schemas as appropriate, and presentation in `src/client`; do not mutate `GameState` from the client. Preserve deterministic battle identity, side membership, readiness, occupation, ownership, and existing research progression. Never expose authoritative foreign-unit records through an intelligence estimate. Use explicit unknown/estimated states instead of zero-valued authoritative fallbacks.

**Scale/Scope**: 50,000 units, 10,000 designs, four unit domains, four training levels, multiple research groups, allied intelligence sharing, and existing save/snapshot/replay flows.

## Constitution Check

- **Layer separation**: PASS. Capability/training and estimate policy remains in module systems; UI displays projections and sends actions only.
- **Authoritative schemas**: PASS WITH VERIFICATION. All persisted records must use the repository's registered Polars schemas and stable keys.
- **Data-oriented processing**: PASS WITH OPEN GATE. Keep Polars frames authoritative; any measured temporary arrays are calculation-only and must retain deterministic fallbacks.
- **Modularity/SOLID**: PASS. Keep role catalog, training lifecycle, intelligence estimate projection, combat projection, and panel presentation in focused components.
- **Commenting**: PASS. New comments are English and explain rationale/root cause rather than restating code.
- **Empirical verification**: PASS WITH LIVE-CLIENT GATE OPEN. The latest combined AI, capability, training, design, combat-invariant, intelligence-projection, presenter, IPC, engine-replay, schema-migration, and layer-boundary run passed 108 tests, one opt-in benchmark skipped by default, and 40 subtests. The quickstart automated checks passed; SC-007 passed at 705.466 ms median / 916.620 ms p95. Live-client acceptance remains open.

## Design and Implementation Locations

```text
modules/base/systems/military/
├── capability_catalog.py          # Canonical role metadata and bounded projections
├── capability_system.py           # Training lifecycle, facility eligibility, and combat-facing projections
├── combat_system.py               # Existing two-side resolver consumes projections
├── covert_operations_system.py    # Authoritative intelligence collection and findings
└── research_program_system.py     # Existing research, design, and production contracts

modules/base/schema.py             # Registered Polars schemas and primary keys
src/shared/actions.py              # Semantic training/design commands
src/client/ui/panels/military/
├── presenter.py                   # Passive view-model projection and authorization filtering
├── unit_list_panel.py             # Unit and authorized foreign-estimate presentation
└── unit_design_panel.py           # Design capabilities, prerequisites, costs, and counters

tests/
├── test_capability_catalog.py
├── test_military_capability_system.py
├── test_research_program_system.py
├── test_combat_system.py
├── test_military_presenter.py
└── test_military_capability_performance.py  # Controlled SC-007 fixture, if runtime permits
```

**Structure Decision**: Extend existing module-layer policies and the established military presenter/panels. Reuse covert findings and treaty-effect authorization for shared intelligence rather than exposing the authoritative `units` table to the client. Keep training locations and estimates in registered state tables or existing persisted observation records, not module globals or UI-owned mutable state. Training requires an enabled, staffed, domain-compatible facility in the unit's current region; eligible local facilities are selected by stable facility ID, avoiding a second movement policy while the unit is taken off-map for training. No new engine runner or inheritance hierarchy is needed.

## Complexity Tracking

No constitution exception is approved. SC-007 remains an empirical gate, not a reason to weaken correctness, privacy, determinism, or gameplay semantics. Profile first; allow at most three measured algorithm-optimization iterations and record every attempted change and result. If still over 1 second after iteration three, leave SC-007 open and continue other specification work.
