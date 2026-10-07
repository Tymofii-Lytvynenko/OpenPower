# Implementation Plan: Internal Economy, Budget & Trade Simulation Systems

**Branch**: `004-internal-economy-budget-trade` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification at `specs/004-internal-economy-budget-trade/spec.md`

## Summary

Complete the economic simulation as a deterministic, data-oriented pipeline over the existing country, population, production, ledger, stockpile, and budget tables. Preserve the current module/system boundaries and public table schemas; optimize the 200+ nation tick without changing the specified formulas or policy behavior. After three bounded optimization iterations, the repository's controlled 220-country/36-resource benchmark most recently measured the sum of system medians at 8.22 ms, so SC-003 remains open and is recorded for follow-up.

## Technical Context

**Language/Version**: Python (repository runtime; see `pyproject.toml`)

**Primary Dependencies**: Polars DataFrames/LazyFrames and NumPy for existing aligned-matrix calculation paths; Polars tables remain the authoritative state and serialization contract.

**Storage**: In-memory `GameState.tables`; Arrow-compatible Polars frames are persisted through the existing save/IPC boundary.

**Testing**: pytest, including economy specification/parity tests and opt-in performance benchmarks.

**Target Platform**: Existing OpenPower desktop/headless simulation runtime.

**Project Type**: Python game engine with modular gameplay systems.

**Performance Goals**: Full economy update for 200+ countries below 5 ms per simulation tick (SC-003); preserve deterministic, stable aggregation behavior (SC-002).

**Constraints**: Keep gameplay formulas and compatibility fallbacks intact; do not move gameplay policy into engine/core; keep Polars schemas authoritative; handle treaty and regional trade constraints; no silent fallback on malformed data.

**Scale/Scope**: 36 resource types, 200+ countries, economic demand/production, global clearing, stockpiles, trade network, and fiscal updates.

## Constitution Check

**Before research**

- Layering: PASS — behavior remains in `modules/base/systems/economy`; no client, server, or engine internals are introduced.
- Data contracts: PASS WITH VERIFICATION — all state written by this feature remains Polars frames and must preserve the canonical columns and keys in `DATA_SCHEMA.md`.
- Data-oriented processing: PASS WITH GUARDS — aligned NumPy arrays may be temporary calculation buffers in the existing fast paths; state inputs/outputs remain Polars tables. Preserve deterministic monetary reductions and route constrained or irregular cases through policy-aware fallbacks.
- Modularity/SOLID: PASS — keep demand, trade policy, and budget calculations in focused composable helpers/systems rather than growing engine orchestration.
- Empirical verification: PASS WITH DEFERRED PERFORMANCE ISSUE — correctness tests pass, but SC-003 is not satisfied by the latest 8.22 ms measurement after the three allowed optimization iterations. The issue and all attempts are recorded; no more optimization is done in this implementation pass.

**After design**: same gates apply. No schema migration or cross-layer dependency is proposed. Performance is not considered complete until the same repeatable benchmark reaches <5 ms without gameplay drift. The benchmark sums three per-system medians after a warm-up and five measured sequential ticks; retain that contract when comparing changes.

## Design and Research

See [research.md](research.md) for technology choices, evidence, and unresolved performance work; [data-model.md](data-model.md) for table contracts; and [contracts/economic-tick.md](contracts/economic-tick.md) for tick invariants.

### Implementation locations

```text
modules/base/systems/economy/
├── internal_economy_system.py     # Demand, internal production, and ledger integration
├── consumption_fast_path.py       # Existing formula-oriented demand helper; parity-gated
├── trade_system.py                # Clearing, stockpile decay, and trade projections
├── budget_system.py               # Fiscal revenue, upkeep, debt interest, and balance
└── treaty_trade_policy.py         # Bilateral/regional trade constraints

src/shared/
├── economy_meta.py                # Resource catalog and shared economic constants
├── numeric.py                     # Stable sums used by economic aggregation
└── state.py                       # Authoritative GameState table boundary

tests/
├── test_economy_specification.py  # Formula, table, and parity coverage
├── test_treaty_trade_policy.py    # Constrained trade behavior
└── test_*economy*performance.py   # Controlled opt-in measurement, if present
```

**Structure Decision**: Extend existing module-layer systems and focused policy/helpers; do not add another project or move economy policy into shared/core/engine. Tests stay in the repository's existing top-level `tests/` layout.

## Complexity Tracking

No constitution exception is approved. The measured performance miss is tracked as required work, not a reason to weaken determinism, schema, or policy constraints.
