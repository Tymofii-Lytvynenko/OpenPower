# Data Model: Mod Runtime and ECS Graph

## Mod manifest

`ModManifest` contains module ID, display name, version, API version, declared dependencies, and module path. Requested modules are expanded through dependency manifests and returned dependency-first in stable order.

## Runtime contribution

`ModContribution` is an immutable aggregate of system instances, table schema contracts, and save migrations. `contribute()` returns this complete value. Legacy `register()` may return one or more systems and is normalized into a contribution with no schemas/migrations.

## Execution graph

Graph keys are unique system IDs; each value is the set of required predecessor IDs. Missing dependencies fail before scheduling. `TopologicalSorter` supplies ready nodes; the engine chooses among them by phase then ID. A cycle produces a `CycleError` naming cycle participants and no partial execution order.

## Override behavior

Modules load in dependency order. A later module's system with an existing ID replaces that earlier entry in the aggregate and emits a warning; one module cannot declare the same ID twice.
