# Implementation Plan: Production, Deployment, and Foreign Orders

**Branch**: `114-production-deployment-and-foreign-orders` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/114-production-deployment-and-foreign-orders/spec.md`

## Summary

Complete the shared pipeline from prioritized domestic production through deployment transit, foreign-order delivery, and used-unit market transfers. Keep queue and contract decisions authoritative in military module systems, use shared movement/access and weapons-trade policies, and preserve ownership, payment, readiness, route, and provenance through the existing state and persistence contracts. The core systems already exist; validate the requirements and change only evidenced gaps.

## Technical Context

**Language/Version**: Python 3.14.1  
**Primary Dependencies**: Polars 1.36.1 and existing OpenPower module/action/event contracts  
**Storage**: Authoritative Polars tables in `GameState` and scenario globals  
**Testing**: pytest and standard-library unittest-compatible suites  
**Target Platform**: Windows desktop client and headless authoritative simulation  
**Project Type**: Desktop strategy game with modular authoritative server simulation  
**Performance Goals**: 50,000 production orders plus 100,000 transit records in <1 second when only due records advance  
**Constraints**: Deterministic outcomes; no client-side authoritative mutation; one inventory/transfer pipeline; at most three measured optimization iterations per failing algorithm, with remaining issues logged and deferred.  
**Scale/Scope**: Production queue, unit deployment/splitting, military movement routes, accepted foreign contracts, used-unit market, seller preferences, AI parity, persistence, and player-facing status.

## Constitution Check

- Gameplay policy remains in `modules/base/systems/military`; shared actions are commands and the client only dispatches them.
- Authoritative records remain Polars tables; queue allocation and routes are deterministic and use existing state/action boundaries.
- Production and transfers reuse existing economy, access, diplomacy, readiness, and save contracts rather than adding parallel authorities.
- No architectural exception or new dependency is required. Re-check after design: PASS.

## Project Structure

```text
modules/base/systems/military/
├── production_policy.py             # Capacity formula and deterministic allocation
├── research_program_system.py       # Design/research and production order lifecycle
├── military_system.py               # Deployment, movement, and arrival
├── foreign_order_system.py          # Seller acceptance, contracts, used listings
├── movement_access.py               # Shared route access
└── route_policy.py                  # Shared route planning
src/client/ui/panels/military/
├── unit_production_panel.py
├── unit_market_panel.py
└── presenter.py
modules/base/schema.py
tests/
├── test_production_capacity_policy.py
├── test_research_program_system.py
├── test_foreign_order_system.py
├── test_military_movement_spec.py
└── test_production_deployment_performance.py
```

**Structure Decision**: Extend existing production, military movement, and foreign-order systems. The used-unit market must continue to operate on `units` and the shared route tables; do not add a separate inventory or transfer mechanism.

## Implementation Sequence

1. Verify capacity formula, queue-priority/preemption semantics, order cost, pause/resume, and exactly-once completion.
2. Verify deployment origin/domain rules, grouping, blocked transit, map/combat availability, arrival readiness, and provenance.
3. Verify seller eligibility/acceptance, default pricing, cancellation costs, embargoes, used listing withdrawal, atomic purchase, and design visibility.
4. Verify AI/action parity and snapshot/save/replay continuation for partial queues and in-transit transfers.
5. Measure the 50,000-order/100,000-transit-record gate. If it fails, spend at most three measured iterations, record each attempt/result, then log and defer if still failing.
6. Complete live UI acceptance for queue ETA/deployment location within 30 seconds when an interactive client is available.

## Complexity Tracking

No constitution violations or additional dependencies are planned.
