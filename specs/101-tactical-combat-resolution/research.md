# Research and Design Decisions

## 1. Existing implementation baseline

The current military flow already provides the integration points needed for this MVP:

- `military_system.py` owns unit actions, direct movement, contact detection, and engagement mode.
- `combat_system.py` groups stationary hostile units by region, resolves deterministic rounds, emits battle start/end events, and changes regional military control.
- `GameState` stores authoritative Polars tables and the server sends snapshots to a passive client.
- `unit_renderer.py` already has unit selection and progress-overlay primitives; `battle_overview_panel.py` already reads the `battles` table.

The plan therefore extends existing tables and systems instead of replacing the tactical-map or networking architecture.

Feature-specific policy stays out of `src/shared`. Shared files receive only passive action/event/view contracts. Save migration and legacy-default validation run from a server-owned migration boundary, while runtime readiness, order, alliance, combat, and occupation policy remain in `modules/base`. The existing snapshot codec remains a transport boundary; this feature adds round-trip tests rather than gameplay logic to that codec.

## 2. Readiness timing decision

The MVP uses game-time durations expressed in days and converts them through the existing simulation clock:

| From | To | Duration | Rationale |
|------|----|----------|-----------|
| `PARKED` | `READY` | 2 game days | Preserve the current implementation and keep the first mobilization interval short enough for the MVP feedback loop. |
| `READY` | `PARKED` | 0 game days | Preserve the current implementation's immediate stand-down behavior. |
| `READY` | `FORTIFIED` | 2 game days | The exact reference duration was not available, so the MVP uses a configurable symmetric default. |
| `FORTIFIED` | `READY` | 0 game days | Leaving a fixed defensive posture is immediate. |

`PARKED -> FORTIFIED` is never a direct jump. It is a persisted two-stage sequence (`PARKED -> READY`, then `READY -> FORTIFIED`) and therefore takes 4 game days at the MVP defaults. Duration constants belong to a small readiness policy so balancing can change them without changing table shape or UI contracts.

Progress is `0.0` at transition start and reaches `1.0` only when the simulation clock reaches the stored completion timestamp. The completion timestamp is the authoritative ETA; remaining minutes are derived from it at read time and are never stored as a second countdown. A paused simulation does not advance timestamps. Save/load restores the timestamps and pending stage, so a resumed game continues at the same progress.

## 3. Readiness behavior and combat contribution

Stable status is separate from transition state. A unit remains in its last completed status while a target status is being prepared; the progress bar describes the pending target rather than changing combat behavior early. The default combat contribution weights are:

| Status | Contribution weight | Use |
|--------|---------------------|-----|
| `PARKED` | 0.25 | Represents a formation not prepared for immediate combat. |
| `READY` | 1.00 | Baseline field contribution. |
| `FORTIFIED` | 1.50 | Defensive contribution while holding its current region. |

The `FORTIFIED` weight is applied only while the unit is stationary in its current region. Issuing movement or attack cancels the fortified posture and returns the unit to `READY` before the order can execute. A unit in a transition contributes using its last completed status. Terrain, regional fortification, supply, morale, and logistics are intentionally not consulted.

## 4. Transition interruption and order policy

There is one active transition per unit. A repeated request for the same target is idempotent and does not reset progress. The latest valid readiness target replaces the previous target and starts at the current simulation time. For movement and attack, the latest valid order replaces the queued order; an invalid order is rejected without deleting the existing valid order. An explicit readiness command cancels a pending movement/attack order.

Movement and attack orders cannot bypass a transition. They are stored as a pending order when the unit must first become `READY`; the order executes only after the transition completes. An attack or movement command issued by a `FORTIFIED` unit first cancels the fortified posture and performs the immediate `FORTIFIED -> READY` release. If hostile contact and transition completion share a simulation minute, contact interruption is processed first, the transition is canceled, and combat uses the last completed status. Other due transitions finalize after combat interruption processing. If a unit is destroyed or its owner becomes invalid before completion, the transition and pending order are removed.

## 5. Two sides with allied participants

Each battle is keyed by `(region_id, war_id)` and has exactly `SIDE_A` and `SIDE_B`. A country belongs to one side only. A country is eligible to participate when:

1. it is present in the region with at least one stationary unit;
2. it is a member of the corresponding war side, or it has a direct active military/defensive alliance with a side member and the existing treaty/wartime rules permit participation; and
3. it is not neutral to both sides and is not already assigned to the opposing side. Alliance chains are not transitive.

The resolver reads the existing war and treaty tables, expands side membership deterministically, sorts country and unit identifiers, and records the resolved assignment in `battle_participants`/`battle_units`. A neutral country remains outside the battle even if it is physically present. An ambiguous or conflicting alliance relationship is omitted for that tick and emits a diagnostic event; it never creates a third side.

For an engagement-zone contact that does not yet share a region, the battle region is the lowest positive `current_region_id` among contact units, with unit ID as the tie-breaker. Units still moving do not contribute until they are stationary in that anchor region.

Combat resolves aggregate weighted strength for the two sides. The existing deterministic loss policy remains the baseline: positional rounds resolve on each new in-game hour, assault actions may resolve immediately, readiness-weighted strength is the only new combat input, and a strength ratio of at least `2.5:1` uses the decisive-advantage branch. A side may contain any number of countries, but a battle never creates a third opposing aggregate. If both sides reach zero in the same deterministic round, the result is a draw: the battle is concluded with an empty victor side, no controller transfer, and the region remains contested. This avoids choosing a winner from iteration order.

## 6. Battle lifecycle and status interface

Battle status is explicit and queryable from the authoritative snapshot:

- `ACTIVE`: both sides have positive eligible strength and rounds may resolve.
- `STALEMATE`: both sides remain present but no progress was made in the latest round; it remains visible and does not emit a repeated start event. A later round that changes weighted strength returns the battle to `ACTIVE` and emits one update event.
- `CONCLUDED`: one side has no remaining strength; the winner and conclusion time are persisted for the event/view boundary before the active row is retired.

If both sides reach zero in the same round, `CONCLUDED` is stored with no victor, no controller change, and a contested region. Units at zero strength are removed; no routing state is created.

The server emits one start event, zero or more update events when status/balance/strength changes, and one conclusion event. The client refreshes the battle overview and map markers when the snapshot signature for battles, participants, occupations, or selected-unit readiness changes; it does not poll or mutate gameplay state.

## 7. Occupation behavior

Combat victory changes `regions.controller` and creates or updates an occupation row. `regions.owner` is unchanged. Occupation records contain the winning controller, garrison strength, `resistance=0.0`, start time, and an active/contested flag so later diplomacy can consume the state without a separate resistance simulation in this MVP.

## 8. Alternatives considered

| Alternative | Decision | Reason |
|-------------|----------|--------|
| Apply status changes immediately | Rejected | Removes the requested strategic time cost and makes the progress bar meaningless. |
| Add terrain, supply, or regional fortification fields now | Rejected | These are explicitly outside the MVP and would expand the state contract without data sources. |
| Model each ally as a third combat side | Rejected | Allies support one of two opposing sides; a third aggregate would make victory and occupation ambiguous. |
| Store transition progress only in the client | Rejected | The server must remain authoritative and save/load must be deterministic. |
| Rebuild the map or networking layer | Rejected | Existing overlay, panel, snapshot, and action paths already support the needed integration. |
| Simulate routing for defeated units | Rejected | Zero-strength removal and draw handling provide deterministic MVP outcomes without another unit lifecycle. |
| Use transitive alliance chains | Rejected | Direct treaty membership keeps side assignment auditable and prevents ambiguous coalition expansion. |

## 9. Verification strategy

Use focused `unittest` modules for transition boundaries, interrupted/persisted progress, same-minute precedence, alliance resolution including engagement-zone contact, battle lifecycle events, zero-strength removal/draw, occupation, and snapshot shape. Keep existing combat and engagement tests as regression coverage. Add a deterministic replay fixture, a headless smoke scenario with 100 concurrent engagements and a `≤250 ms` server tick budget, and a bounded client snapshot-consumption check with a `≤100 ms` budget and `≤2 MB` representative payload; neither check may initialize graphics or network I/O. UI validation uses the existing presenter and renderer interfaces with snapshot fixtures rather than requiring a live graphics context.
