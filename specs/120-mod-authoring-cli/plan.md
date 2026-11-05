# Implementation Plan: Mod Authoring and Runtime Validation CLI

**Branch**: `120-mod-authoring-cli` | **Date**: 2026-10-21 | **Spec**: [spec.md](spec.md)

**Input**: Existing `openpower mod create` and `openpower mod validate` behavior in
`src/cli.py`, `src/modding/`, and the module authoring guide.

## Summary

Record the current module authoring workflow. The CLI creates a minimal module using a
validated ID and then validates modules by composing their dependencies through the
runtime, constructing a headless session, and executing one startup tick.

## Technical Context

**Language/Version**: Python 3.10+

**Primary Dependencies**: Python standard library, project mod runtime, argparse

**Storage**: Generated Python and TOML files under `modules/<mod-id>/`

**Testing**: Existing focused coverage is in `tests/test_modding_cli.py`; this
documentation update does not execute it.

**Target Platform**: Local OpenPower development environments

**Project Type**: Python desktop game engine and CLI tooling

**Performance Goals**: Validation completes one real headless startup tick; no separate
latency target is defined.

**Constraints**: The scaffold must not overwrite an existing module. Validation must use
the same discovery and runtime composition path as normal sessions.

**Scale/Scope**: One module scaffold or validation request per command invocation.

## Constitution Check

- **Composition**: Modules declare systems, schemas, and migrations through the mod API.
- **Layer ownership**: CLI tooling delegates to `src/modding`; gameplay policy stays in
  modules and runtime validation delegates to the server session.
- **Failure visibility**: Invalid input or runtime failure is returned to the author with
  a failing command result.
- **Status**: Aligned with the current module and runtime boundaries.

## Project Structure

```text
src/
├── cli.py
├── modding/
│   ├── scaffold.py
│   └── validation.py
├── shared/mods.py
└── shared/mod_api.py

modules/<mod-id>/
├── mod.toml
├── registration.py
├── systems.py
└── README.md

tests/test_modding_cli.py
```

**Structure Decision**: The small authoring workflow remains in `src/modding` and the
CLI remains a thin command parser/dispatcher. Generated content lives under the target
project's `modules/` directory.

## Complexity Tracking

No constitution exception or additional architectural layer is required.
