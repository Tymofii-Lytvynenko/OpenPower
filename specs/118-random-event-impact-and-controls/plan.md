# Implementation Plan: Random Event Impact and Controls

**Branch**: `118-random-event-impact-and-controls` | **Date**: 2026-10-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/118-random-event-impact-and-controls/spec.md`

## Summary

Extend the existing deterministic daily event roll into a configurable, persistent event lifecycle with explicit definitions, bounded effects, response choices, history, and player/scenario controls. Keep gameplay policy in `modules/base/systems/world`, public action/event data contracts in `src/shared`, persistent tabular state in Polars schemas, and presentation in `src/client`. Preserve the current event trigger contract during migration so existing infrastructure damage behavior and legacy saves continue to work.

## Technical Context

**Language/Version**: Python 3.10+ (repository supports 3.10–3.12)

**Primary Dependencies**: Polars 1.36.1, project-standard Python dataclasses and `DeterministicRuntime`; existing Arcade/ImGui client presentation

**Storage**: Authoritative game-state Polars tables persisted by the existing save writer; snapshots already copy all tables, globals, determinism state, and domain events. Small scenario-level control settings remain in serializable `GameState.globals`; an explicit event seed also initializes a dedicated event RNG and ID sequence stored there, while the default path composes over the campaign deterministic runtime.

**Testing**: pytest; focused deterministic/system/action/persistence tests, existing infrastructure and event-feed regressions, then broader suite

**Target Platform**: Existing desktop client plus headless authoritative simulation process

**Project Type**: Python simulation engine with dynamically registered gameplay module and passive desktop client

**Performance Goals**: Due event rolls and lifecycle records only; honor SC-007 (<1s for 10,000 active instances and 100,000 effect records when only due records advance)

**Constraints**: No second event generator; no parallel population/economy/health model; strict shared/core/engine/server/client/module boundaries; deterministic RNG and stable record ordering; bounded values; reject invalid paid responses atomically; preserve legacy `active_events` saves and the existing `EventRandomEventTriggered` consumer contract

**Scale/Scope**: Ten catalog event types initially, configurable categories and frequency, persistent active/recent instances, response/effect history, one-player and AI control paths; multiplayer remains outside scope

## Constitution Check

- **Layer separation**: PASS. Actions/events are passive types in `src/shared`; simulation policy stays in the registered module; client reads state and sends actions only.
- **Data-oriented state**: PASS. Instance, effect, response, and category-control records use Polars tables; only compact scenario defaults remain in globals.
- **Composition/SOLID**: PASS. Reuse deterministic runtime, existing authority and infrastructure policies, and separate event catalog/effect policy from lifecycle orchestration.
- **Persistence and determinism**: PASS. Tables, globals, RNG state, and journal already flow through save and snapshot contracts; compatibility migration is explicit.
- **Empirical validation**: PASS as a design gate. Focused tests and runnable checks are required; real-client-only UX/performance criteria remain open until measured.

## Project Structure

### Documentation (this feature)

```text
specs/118-random-event-impact-and-controls/
├── plan.md
├── research.md
├── data-model.md
├── contracts/
│   └── random-events.md
├── quickstart.md
└── tasks.md
```

### Source Code (repository root)

```text
src/shared/
├── actions.py                 # scenario controls and event-response commands
└── events.py                  # persistent lifecycle facts
modules/base/
├── schema.py                  # Polars event-instance/effect/response/control tables
├── registration.py            # registered random-event system
└── systems/world/
    ├── random_events_system.py # eligibility, lifecycle, control and response orchestration
    ├── random_event_policy.py  # catalog profiles and bounded effect/response policy
    ├── random_event_effects.py # deterministic bounded aggregation for domain consumers
    └── ai/random_event_policy.py # AI response selection through the same authoritative handler
src/client/ui/panels/service/
├── event_feed_presenter.py    # readable active/recent event details
└── news_panel.py              # read-only controls and response commands
tests/
└── test_random_event_*.py      # focused rules, lifecycle, persistence and presentation checks
```

**Structure Decision**: Extend the existing `modules/base` system, its shared action/event contracts, and the established schema-driven world-state. Keep the event feed presenter as a read-only view-model boundary. Avoid new engine/server abstractions and avoid introducing dependencies.

## Complexity Tracking

No constitution violations. The extra state tables are justified by the existing Polars/Arrow persistence contract and the feature's explicit large-state benchmark; a nested mutable `globals` list would be less efficient and harder to validate.
