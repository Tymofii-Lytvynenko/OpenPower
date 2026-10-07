# Implementation Plan: Dynamic Mod Loader and ECS Runner

**Branch**: `008-dynamic-mod-loader-ecs-runner` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

## Summary

Keep module discovery and contribution aggregation in `ModManager` and execution ordering in the content-agnostic `Engine`. Support the current schema/migration-aware `contribute()` API while also accepting the specified legacy `register()` entry point. Use the standard-library `TopologicalSorter` for dependency validation, then deterministically select each ready system by phase and system ID. Later-loaded mods may replace earlier systems by ID with an explicit warning.

## Technical Context

**Runtime**: Python 3.14; `graphlib.TopologicalSorter`; TOML manifests; importlib-based registration.
**Runtime contributions**: `ModContribution` carries systems, table schemas, and save migrations; legacy `register()` may return systems.
**Execution**: `Engine` owns only system contracts, phases, dependency scheduling, checkpoints, and failure handling.
**Testing**: loader/API tests, deterministic ordering/cycle diagnostics, layer-boundary checks, and an opt-in cold-start benchmark.
**Performance gate**: scan, import, register, and order the active core mod in under 500 ms.

## Constitution Check

- **Content-agnostic engine**: PASS. No gameplay modules are imported by `src/engine/simulator.py`.
- **Layer separation**: PASS. Manifests and registration contribute systems through shared contracts.
- **Composition**: PASS. Mods compose systems/features and engine orders them without inheritance-based module coupling.
- **Empirical verification**: PARTIAL. API, ordering, failure, and cold-start tests pass; full-suite rerun remains open.

## Design Outputs

- [research.md](research.md): current module API, loader compatibility and scheduler design.
- [data-model.md](data-model.md): manifest, contribution, graph and runtime invariants.
- [contracts/mod-runtime.md](contracts/mod-runtime.md): entry point and execution scheduler contracts.
- [quickstart.md](quickstart.md): focused tests and measured cold start.
- [tasks.md](tasks.md): dependency-ordered implementation and verification record.
