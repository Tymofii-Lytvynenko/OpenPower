# Tasks: UN Recognition and Regional Economic Access

**Input**: [spec.md](spec.md)

## Phase 1: Authoritative contracts

- [X] T001 Add typed case, captured voter, vote, and per-country regional recognition tables in `modules/base/schema.py`.
- [X] T002 Add the authorized vote action and durable lifecycle events in `src/shared/actions.py` and `src/shared/events.py`.
- [X] T003 Add deterministic voter eligibility, AI decision, and regional access policies in `modules/base/systems/world/recognition_policy.py`.

## Phase 2: Recognition lifecycle

- [X] T004 Open one case from each completed, still-controlled annexation and capture the eligible voter roster and configured deadline in `modules/base/systems/world/recognition_system.py`.
- [X] T005 Validate and replace votes atomically; resolve only after the deadline using a strict majority of the captured roster.
- [X] T006 Run AI votes through the same roster/result policy, publish lifecycle records, and withdraw pending/passed recognition after ownership or control reversal.
- [X] T007 Add readable case, vote-count, country-status, and vote-action projections to the diplomacy UI.
- [X] T008 Add deterministic lifecycle, eligibility, authority, majority, reversal, access-policy, and presenter tests.

## Phase 3: Remaining specification coverage

- [X] T009 Carry explicit regional production provenance into regional trade flows and enforce recognition before foreign access; do not infer regional output from national aggregates.
- [X] T010 Show claimant, former owner, case status, vote counts, recognized-country count, and selected-country status in the region inspector.
- [X] T011 Add save/load, snapshot, and deadline-resolution continuation tests for cases, votes, and statuses.
- [X] T012 Add the 1,000-case / 10,000-status incremental processing benchmark from SC-009.
- [X] T013 Run the focused and full repository validation matrix and record environment evidence.

## Dependency order

```text
T001 + T002 + T003 -> T004 -> T005 + T006 -> T007 + T008
T004 + T005 + T006 -> T009 + T010 + T011 + T012 -> T013
```

## Current evidence

- T009 is implemented with an optional typed `regional_production` table loaded only from explicit country/resource/region records. Bilateral flows retain `source_region_id`; active recognition cases gate those source-tagged flows before market reconciliation. No regional output is apportioned from national totals.
- Focused recognition/diplomacy/schema/UI/persistence/trade matrix: **51 passed** on 2026-10-07 (Windows, project virtual environment, 9.47 s).
- SC-009 scale benchmark: **1,000 pending cases + 10,000 votes + 10,000 statuses in 0.035 s** on 2026-10-06 (Windows, project virtual environment).
- Focused recognition matrix: **51 passed in 11.19 s**, including the opt-in recognition benchmark at **0.052 s**; a fresh standalone controlled run measured **0.061 s**. The historical repository-wide suite reported **524 passed, 4 opt-in benchmarks skipped, 173 subtests passed in 151.51 s**; all four then-skipped scale gates passed separately. Latest repository-wide suite: **917 passed, 25 skipped, 116 warnings, 239 subtests passed in 832.53 s** (2026-10-07). SC-009 is below its 250 ms budget; no optimization iteration was needed. Interactive visual acceptance remains a manual gate.

## Phase 4: Convergence

- [X] T014 Clarify FR-010, FR-011, FR-012, and SC-005 to bound enforcement to explicit source-region provenance and document how regional bilateral/treaty resource allocations and derived revenue use recognition access.
- [X] T015 Clarify AC-10 and FR-016 to match the council's eligible-voter deadline, current-vote, replacement, and resolved-status presentation in `src/client/ui/panels/politics/treaties_live.py`.
