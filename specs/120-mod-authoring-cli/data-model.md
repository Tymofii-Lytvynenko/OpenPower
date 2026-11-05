# Data Model: Mod Authoring CLI

## Module identity

A module ID is trimmed and must match `^[a-z][a-z0-9_]*$`. It is used as the package
directory name and manifest ID. The display name defaults to a title-cased form of the
ID. Dependency IDs are validated by the same rule and de-duplicated while preserving
order.

## Generated module files

```text
modules/<mod-id>/
├── __init__.py
├── mod.toml
├── registration.py
├── systems.py
└── README.md
```

The manifest records identity, version `0.1.0`, API version, minimum engine version, and
dependencies. The starter system exposes its ID, access declaration, dependencies, and
update method. The registration function returns a mod API contribution.

## Validation report

`ModValidationReport` is immutable and records the normalized module ID, active load order,
resolved system IDs, table schema names, initialized state table names, and handled action
type names. A report exists only after a successful runtime startup tick.
