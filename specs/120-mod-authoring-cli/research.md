# Research: Mod Authoring CLI

## Existing behavior

- `openpower mod create <mod-id>` accepts an optional display name, dependencies, and
  project root.
- IDs and dependency IDs are normalized and checked against the lower-snake-case rule.
- The scaffold contains `mod.toml`, `registration.py`, `systems.py`, `README.md`, and
  `__init__.py`; an existing module directory is an error.
- `openpower mod validate <mod-id>` discovers the requested module, checks the manifest
  directory and dependency declarations, composes the selected runtime, creates a
  headless `GameSession`, and executes one tick.
- A successful report includes load order, system IDs, table schema names, state tables,
  and handled action type names.
- Existing focused coverage is in `tests/test_modding_cli.py`.

## Decisions recorded

| Decision | Rationale |
| --- | --- |
| Validate through the real runtime | A syntax-only check would miss dependency, schema, action, and scheduler errors. |
| Keep scaffolding small | Authors can add features without inheriting a large framework or hidden registry. |
| Reject an existing target | Prevents accidental data loss from a generated scaffold. |

## Scope boundary

Data merge and precedence rules belong to feature 104. The module loader and system graph
belong to feature 008. This feature specifies the author-facing create and validate
commands that compose those capabilities.
