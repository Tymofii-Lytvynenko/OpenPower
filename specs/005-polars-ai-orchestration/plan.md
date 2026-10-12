# Implementation Plan: Declarative Polars AI Orchestration

**Branch**: `005-polars-ai-orchestration` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification at `specs/005-polars-ai-orchestration/spec.md`

## Summary

Use a protocol-driven registry of independent AI policy scorers that return Polars LazyFrames. Normalize and combine candidate decisions, apply scope/conflict/quota resolution deterministically, collect once, and translate winning rows into semantic game actions. Keep generic execution mechanics in `src/core/ai_framework.py` and gameplay policies in `modules/base/systems/world/ai/`.

## Technical Context

**Language/Version**: Python (repository runtime in `pyproject.toml`)

**Primary Dependencies**: Polars LazyFrames, shared semantic `GameAction` contracts.

**Storage**: Read-only `AITableContext` snapshots over existing `GameState.tables`; decision projections are transient.

**Testing**: pytest for policy formulas, action resolution, deterministic ranking/scope, integration, and opt-in performance measurement.

**Target Platform**: Headless simulation worker and desktop game server runtime.

**Project Type**: Layered Python game engine.

**Performance Goals**: Evaluate survival-tax and military-ROI scorers for 220 countries in under 2 ms for the specified controlled benchmark.

**Constraints**: Core contains only generic mechanisms; policies stay in modules; inputs are snapshots and AI emits actions without direct state writes; candidate ranking, conflict resolution, cadence, delegation, and order are deterministic.

**Scale/Scope**: 200+ countries, multiple independent domains, lazy candidate frames, one combined materialization, and bounded action emission.

## Constitution Check

**Before research**

- Layering: PASS — generic framework is in `src/core/ai_framework.py` (mechanism-only); policies are in `modules/base/systems/world/ai/`; `AISystem` is module orchestration.
- Data-oriented design: PASS — country-wide decisions are expressed with Polars LazyFrames and collected into typed decision tables.
- Modularity/SOLID: PASS — scorers implement a small protocol and register compositionally; action resolvers are policy-owned.
- Passive client/state: PASS — AI reads context tables and emits `GameAction` objects; it does not mutate `GameState.tables`.
- Empirical verification: PASS WITH ENVIRONMENT QUALIFICATION for scorer-only SC-001 — the current controlled run passes at 1.53 ms with one Polars thread. The separately measured complete ranking/action path is 8.40 ms and its 6.40 ms gap is recorded; production retains Polars automatic sizing.

**After design**: same checks apply. No core/engine move or new dependency is proposed.

## Design and Research

See [research.md](research.md), [data-model.md](data-model.md), [contracts/ai-decision-pipeline.md](contracts/ai-decision-pipeline.md), and [quickstart.md](quickstart.md).

### Implementation locations

```text
src/core/ai_framework.py                  # Generic candidate protocol, deterministic resolve, one collect
modules/base/systems/world/ai_system.py   # Context construction and policy registry
modules/base/systems/world/ai/
├── budget_policy.py                      # Survival tax/budget scoring
├── military_policies.py                  # ROI and procurement scoring
└── common.py                             # Shared LazyFrame transformations

tests/test_ai_framework.py
tests/test_budget_ai_policy.py
tests/test_ai_system.py
tests/test_ai_performance.py
```

**Structure Decision**: Use the existing reusable core mechanism and module policy boundary rather than the outdated engine-layer path named in the assumption.

## Complexity Tracking

No constitution exception is approved. Performance results are recorded with thread policy because the target is close to the backend's per-collect overhead.
