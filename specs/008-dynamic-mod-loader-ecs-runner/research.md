# Research: Dynamic Mod Loader and ECS Runner

## Codebase findings

1. `src/shared/mods.py` already discovers TOML manifests, expands transitive dependencies, and reports missing/cyclic dependencies deterministically.
2. `ModManager` imports `<module>.registration` and aggregates `ModContribution` objects containing systems, schemas, and migrations. The base module uses `contribute()`; older modules described by the feature may expose only `register()`.
3. Missing registration files were silently skipped, while missing callables raised. The feature contract calls for warning-and-skip for either absent entry point.
4. `Engine` already validates missing dependencies and system access contracts, but hand-implemented Kahn traversal rather than using the specified standard-library `TopologicalSorter`.
5. Heap ordering by `(SystemPhase, system_id)` provides a deterministic choice among systems that are currently ready. This stable policy can remain around `TopologicalSorter`'s dependency readiness.
6. The engine rejects duplicate IDs if passed directly. Mod load order is base-to-expansion, so `ModManager` can implement the documented higher-priority replacement rule before registration while direct engine misuse remains strict.
7. A cold local scan/import/register/graph pass measured 179.678 ms with 30 registered base systems, under the 500 ms success threshold.

## Decisions

- Prefer `contribute()` because it preserves schemas and migrations; accept `register()` as a compatibility entry point and normalize its returned system(s) through the same strict shared mod API.
- Warn and skip only when the registration file or callable entry point is absent. Invalid API versions, invalid contribution values, and duplicate same-mod declarations remain explicit errors.
- Resolve each ready set using `(phase, system_id)` heap order. This makes output independent of dict/set/hash iteration while preserving phase preference among unblocked systems.
- Let a later mod replace an earlier system with the same ID and log both module IDs. Keep duplicate IDs within one module as an error.
- Use `TopologicalSorter.prepare/get_ready/done` for graph lifecycle and preserve `CycleError` with sorted cycle IDs in both the raised error and critical log.
