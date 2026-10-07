# Mod Runtime Contracts

## Registration entry points

- `contribute()` returns a `ModContribution` with systems, schemas, and migrations.
- If `contribute()` is absent, `register()` may return a system or iterable of systems; it is normalized through the shared mod API.
- Missing `registration.py` or both callables logs a warning and skips only that module's runtime contribution.
- Invalid API version or invalid returned objects fail loudly; they are not converted to empty contributions.

## Load and replacement order

Manifest dependencies load before dependents. A higher-priority later module replaces a prior module's system by exact ID and emits an override warning. Duplicate IDs within the same module fail.

## Engine scheduling

- Engine code remains independent of specific gameplay imports.
- All dependencies must reference registered system IDs.
- The scheduler uses `TopologicalSorter` and resolves currently ready systems deterministically by `(phase, id)`.
- Circular dependencies emit a critical log with the cycle IDs and raise `CycleError` before any system runs.
