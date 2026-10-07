# Mod Loading Contract

## Startup order

1. Read requested roots from `mods.json` (default to `base`).
2. Discover module manifests and resolve transitive dependencies into a deterministic topological chain.
3. Reject missing prerequisites, dependency cycles, invalid dependency metadata, incompatible engine-version bounds, or unsupported module API versions before world-state allocation or registration import.
4. Apply the validated chain consistently to data directories, assets/localization, and runtime contributions.
5. Merge table data by stable row identity with later non-null values taking precedence; preserve unrelated rows and columns.

## Failure diagnostics

Errors identify the module ID and the failing condition (missing dependency, cycle member, malformed bounds, engine-version mismatch, API mismatch, schema conflict, or duplicate same-module system ID). A rejected configuration must not return a partially initialized runtime or substitute an empty world.

## Determinism

Given identical manifests and requested roots, the resolved chain and merged keyed tables must be identical regardless of filesystem iteration order or operating system.
