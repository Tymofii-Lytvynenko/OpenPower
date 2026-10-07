# Implementation Plan: UN Recognition and Regional Economic Access

**Branch**: `105-un-recognition-economic-access` | **Date**: 2026-10-07 | **Spec**: [spec.md](spec.md)

**Input**: Recognition, voting, and region-sourced economic-access requirements in this directory.

## Summary

Use the existing annexation-claim lifecycle to open one authoritative, time-bounded recognition case for each completed annexation that remains owned and controlled by its claimant. Persist cases, captured UN voter rosters, replaceable votes, and per-country outcomes in typed `GameState` tables. Keep eligibility, AI choices, majority rules, and access checks in small base-module policies; publish lifecycle events and read-only projections through existing diplomacy and region interfaces. Preserve source-region provenance for explicitly regional production and trade, and never infer a region's output from national totals.

## Technical Context

**Language/Version**: Python 3.14 runtime in the configured workspace.
**Primary Dependencies**: Polars, pytest, existing OpenPower simulation and client layers.
**Storage**: Schema-registered Polars tables in `GameState`; existing snapshot, Arrow IPC, and save-game serialization.
**Testing**: Focused recognition, regional trade, diplomacy, persistence, schema, and performance tests; repository-wide pytest; rendered UI remains a manual acceptance gate.
**Target Platform**: Headless authoritative simulation and the existing desktop client.
**Project Type**: Modular desktop strategy game with an authoritative simulation process.
**Performance Goals**: SC-009 processes 1,000 open cases and 10,000 stored votes/status rows in under 250 ms on the daily update path. The opt-in benchmark is already below the limit; do not optimize without a measured regression.
**Constraints**: Preserve deterministic ordered-action processing, client passivity, schema-driven persistence, and existing treaty/economy behavior. Regional restrictions apply to flows carrying explicit source-region provenance; national aggregates must not be apportioned. Multiplayer and editor-only functionality are out of scope.
**Scale/Scope**: One recognition case per completed annexation claim, a roster captured at opening, a configurable default 30-game-day vote window, bilateral recognition statuses, and source-tagged regional economic access.

## Constitution Check

- **Layer boundaries**: Pass. Recognition rules remain in `modules/base`; shared actions/events remain passive records; the client reads presenter projections and dispatches intent.
- **Schema and data contracts**: Pass. Cases, votes, statuses, and regional production are registered typed tables carried by existing serialization paths.
- **Modularity and SOLID**: Pass. Lifecycle orchestration, pure eligibility/access policy, economy allocation, and presentation use distinct existing seams; no engine-loop changes are needed.
- **Commenting**: Pass. Use descriptive code; English comments only where a non-obvious contract or bug rationale needs explanation.
- **Empirical verification**: Pass for automated behavior and persistence. The focused matrix and full suite pass; live rendered-client usability remains an open manual gate when no desktop client is available.

## Design Decisions

1. Treat `annexation_claims.status == "annexed"` as the formal completion signal. Open a case only while the claimant owns and controls the referenced region. A direct ownership/controller edit without a completed annexation claim is not a recognition-case trigger.
2. Capture a sorted, deduplicated voter roster from the existing `countries.un_member` attribute at case opening. Exclude the claimant and former political owner; later membership changes do not rewrite an open case's electorate.
3. Use one durable vote per case/country, with authorized replacement before the deadline. Resolve only at or after the deadline; passage requires `yes_votes > eligible_voters / 2`. Abstentions, opposition, and absent votes do not count as support.
4. On passage, persist one status row for every captured eligible voter: `recognized` for yes votes and `not_recognized` otherwise. A rejected case creates no recognized statuses. Recognition is bilateral and never transfers territory or military control.
5. Retain existing snapshot/save machinery by registering feature state in the base schema. Do not introduce a feature-specific persistence store or client-owned state.
6. Restrict cross-border resource flows only when their source region is explicit. `regional_production` is optional scenario data; trade allocation retains `source_region_id` and gates it before market reconciliation. Unassigned/national-only flows stay unassigned: neither national production nor national financial aggregates are used to fabricate a regional source. Any future region-sourced financial, tax, or treaty flow must carry provenance and call the same access policy before applying value.
7. Keep claimant domestic access conditional on current ownership and control. Foreign access requires an active passed case and a non-withdrawn recognized status; a reversal withdraws open/passed cases and recognized statuses on the next recognition update.
8. Reuse the measured SC-009 benchmark. Baseline observations pass the 250 ms gate, so no optimization iteration is warranted; unmeasured simultaneous-deadline and large claim-change workloads are recorded as future measurement risks rather than speculatively tuned.

## Project Structure

The feature uses the existing project layout:

- `modules/base/schema.py`, `registration.py`, and `systems/world/recognition_system.py`
- `modules/base/systems/world/recognition_policy.py`
- `modules/base/systems/economy/treaty_trade_policy.py` and `trade_system.py`
- `src/shared/actions.py` and `src/shared/events.py`
- `src/server/io/data_load_manager.py` for explicit scenario regional-output records
- `src/client/ui/panels/politics/recognition_presenter.py`, `treaties_live.py`, and `region_inspector.py`
- Root `tests/test_recognition_*.py`, `tests/test_regional_recognition_trade.py`, and adjacent integration/persistence suites
- Design artifacts in this feature directory

**Structure Decision**: Extend the current base-module diplomacy and economy systems plus their presentation seam. Do not create a parallel recognition, market, or persistence subsystem.

## Complexity Tracking

No constitution violations or additional architectural projects are proposed.
