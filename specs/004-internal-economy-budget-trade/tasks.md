# Tasks: Internal Economy, Budget & Trade Simulation

**Input**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/economic-tick.md`

**Tests**: Required by the specification and the implementation request. Existing evidence: economy specification tests and the opt-in benchmark; the latter currently fails its target.

## Phase 1: Foundational contracts

- [X] T001 [P] Record the canonical 220-country × 36-resource benchmark contract and current failing baseline in `tests/test_economy_performance.py` and `specs/004-internal-economy-budget-trade/research.md`.
- [X] T002 [P] Keep deterministic grouped monetary reductions in `src/shared/numeric.py` and cover cancellation/null/multiple-key cases in `tests/test_economy_specification.py`.
- [X] T003 Add differential tests for input permutation, invalid/non-finite values, and penalty-boundary behavior before broadening any aligned fast path in `tests/test_economy_specification.py`.

## Phase 2: User Story 1 — Dynamic demand and consumption pooling

**Goal**: Derive country demand from global wealth anchoring, solvent population, elasticities, resource dependencies, and the GDP consumption pool.

**Independent Test**: Compare country/resource ledger output with the specification formulas and the compatible Polars calculation path.

- [X] T004 [US1] Implement the world GDP-per-capita anchor, bounded wealth index, propensity-to-consume pool, dependency-ordered demand, and normalization in `modules/base/systems/economy/internal_economy_system.py` and `modules/base/systems/economy/consumption_fast_path.py`.
- [X] T005 [P] Verify poor/rich demand, basic-food floor, authoritative GDP handling, and optimized/compatibility parity in `tests/test_economy_specification.py`.
- [X] T006 [US1] Add edge tests for empty/zero population, clipped wealth-index extremes, cyclic or missing resource dependencies, and malformed numeric inputs in `tests/test_economy_specification.py`.

## Phase 3: User Story 2 — Global clearing and physical resource behavior

**Goal**: Clear imports/exports using global supply-demand ratios, carry stockpiles only for storable goods, apply physical decay and capacity penalties, and preserve treaty/regional restrictions.

**Independent Test**: Differentially compare fast and general paths for country budgets, production, stockpiles, and trade network; assert flow bounds and exact decay/penalty rules.

- [X] T007 [US2] Implement global clearing, stockpile updates, resource decay, unsold-service penalties, and constrained-trade fallbacks in `modules/base/systems/economy/trade_system.py` and `modules/base/systems/economy/treaty_trade_policy.py`.
- [X] T008 [P] Verify catalog coverage, non-storable service metadata, and unconstrained fast-path parity in `tests/test_economy_specification.py`.
- [X] T009 [US2] Add behavior tests for zero denominators, import/export ratio caps, each storage/decay class, service evaporation/layoffs, and the 50%-warehouse penalty boundary in `tests/test_economy_specification.py`.
- [X] T010 [US2] Add parity tests showing treaty and regional constraints select the general policy-aware path and preserve allocated flows in `tests/test_treaty_trade_policy.py`.

## Phase 4: User Story 3 — Fiscal revenue, upkeep, and balance

**Goal**: Credit income tax and tourism levies, debit military upkeep and interest, and update treasury deterministically while preserving other budget sectors.

**Independent Test**: Assert exact fiscal line items and closing reserves for controlled single-country fixtures.

- [X] T011 [US3] Implement income-tax/tourism revenue, military upkeep, debt interest, and reserve updates in `modules/base/systems/economy/budget_system.py`.
- [X] T012 [P] Verify the specified income-tax, 20% tourism levy, configured debt-interest, and negative-reserve calculations in `tests/test_economy_specification.py`.
- [X] T013 [US3] Add exact military-upkeep and repeated-tick/no-drift acceptance tests, including zero and negative balance boundaries, in `tests/test_economy_specification.py`.

## Phase 5: Performance and final verification

- [X] T014 Profile trade and internal-economy stage allocations/materializations on the fixed benchmark fixture; record stage-level evidence in `specs/004-internal-economy-budget-trade/research.md`.
- [X] T015 Reduce repeated identifier conversion, joins, sorting, and table materialization without changing event ordering or deterministic sums in `modules/base/systems/economy/`.
- [X] T016 Run parity and determinism tests for every changed calculation path in `tests/test_economy_specification.py` and `tests/test_treaty_trade_policy.py`.
- [X] T017 **Follow-up performance issue recorded; the <5 ms target remains open and no further optimization is permitted in this pass.** Three optimization iterations are exhausted. Attempt 1 cached canonical post-sort market indices (9.43 ms combined); attempt 2 cached population-row alignment while refreshing population values every tick (9.45 ms combined); attempt 3 moved fast-path numeric validation to NumPy arrays (final same-revision runs: 8.44 ms, 8.54 ms, and 8.22 ms; latest breakdown 3.48 ms trade, 3.40 ms economy, 1.33 ms budget, one Polars thread). An intermediate repeated-Polars-validation variant measured 14.63 ms and was replaced within attempt 3. Parity tests pass; SC-003 is explicitly deferred to a future dedicated optimization pass.
- [X] T018 Run the full regression suite after the current economy, diplomacy, schema, and test changes; latest result: 684 passed, 16 skipped, 116 warnings, 190 subtests passed in 162.89 s. The opt-in SC-003 benchmark remains separately failing at 8.22 ms after the three allowed optimization iterations.

## Dependencies & Execution Order

- T001–T003 establish measurement and deterministic-input contracts.
- User stories 1–3 can be tested independently, but market clearing depends on the resource ledger from US1, and the fiscal tick consumes the trade outputs from US2.
- T014–T017 depend on the correctness/parity checks in US1–US3; do not optimize by removing policy effects or fusing state-dependent heartbeat iterations.
- Completion requires every unchecked task to be resolved with tests/evidence. T017's follow-up issue is recorded and closed for this implementation pass; this does not claim that SC-003's <5 ms target was met.
