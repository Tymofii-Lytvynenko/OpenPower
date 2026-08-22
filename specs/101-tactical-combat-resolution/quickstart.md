# Quickstart: Tactical Combat Resolution MVP

This guide validates the feature in a headless simulation. Run it from the repository root in PowerShell.

## 1. Baseline regression

Before implementation, the existing combat behavior can be checked with:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_combat_system tests.test_engagement_mvp
```

Expected result: all existing combat and engagement tests pass.

After implementation, run the complete suite:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

## 2. Readiness transition scenario

Use a headless `GameState` fixture with one owned unit in `parked` status and the server's normal fixed-step clock.

1. Submit `ActionSetUnitReadiness(unit_id, "ready")`.
2. Verify one transition row exists with `from_status=parked`, `target_status=ready`, progress `0.0`, and a completion time two game days ahead.
3. Advance simulation time to one half of the interval. Verify stable status is still `parked` and progress is approximately `0.5`.
4. Submit `ActionMoveUnit` while the transition is active. Verify a pending move order exists and no movement begins.
5. Submit a second valid move order. Verify it replaces the first pending order. Submit an invalid order and verify the valid pending order remains.
6. Advance to the completion boundary. Verify the status becomes `ready`, the progress bar reaches `1.0` for the completion snapshot, and the latest pending move is released exactly once.
7. Request `fortified`, save, reload, and advance two game days. Verify the transition completes with `fortified`, the remaining time is derived from the persisted ETA, and the reloaded run matches the uninterrupted run.
8. Issue movement from `fortified`. Verify the release to `ready` is immediate and the movement order is applied without a third status.
9. Schedule a transition to complete at the same minute as hostile contact. Verify contact cancels the transition first and combat uses the last completed status.

## 3. Allied two-side battle scenario

Build a fixture with an active war containing countries `A` and `B`, an active military alliance between `A` and `C`, and stationary units from all three in one region.

1. Run the combat system once. Verify exactly one battle row exists with `SIDE_A` and `SIDE_B`, never a third side. For an engagement-zone contact, verify the anchor region is the lowest positive current region ID with unit-ID tie-break.
2. Verify `A` and eligible `C` appear on the same side, with `C` marked `ally` in `battle_participants` and `battle_units`. Verify a transitive ally-of-ally is excluded.
3. Add a neutral country `D` with a unit in the region. Verify `D` is not a participant and does not change either aggregate strength.
4. Make one ally eligible for both sides through inconsistent treaty data. Verify it is omitted, an `EventBattleParticipantRejected` diagnostic is emitted, and no third side is created.
5. Verify one `EventBattleStarted` is emitted and subsequent identical frames emit no duplicate start event.
6. Advance a resolution boundary. Verify weighted strength uses `parked=0.25`, `ready=1.0`, and stationary `fortified=1.5`; no terrain, supply, or regional fortification value is read.
7. Continue until one side reaches zero. Verify zero-strength units are removed, one conclusion event is emitted, the concluded row is retired from the active `battles` view, `regions.controller` changes to the winning controller, `regions.owner` is unchanged, and an active `occupations` row exists.
8. Run a simultaneous-zero fixture. Verify the battle concludes as a draw with no victor, no controller transfer, and no occupation.

## 4. Battle status interface scenario

Feed the snapshot from step 2 into the existing `MilitaryPresenter` and `BattleOverviewPanel` fixture.

- Verify side country lists, participant roles, status, mode, balance, strengths, and occupation state are present.
- Change only battle strength/status and verify the snapshot signature causes a view refresh.
- Resend an identical snapshot and verify no duplicate redraw/event-side effect is produced.
- Feed an older snapshot without the new columns and verify compatibility defaults render the existing battle row.
- Consume a representative snapshot in a headless client fixture and verify the update completes within the configured bound without graphics or network I/O.

## 5. Focused test commands

The implementation should add and keep these focused modules green:

```powershell
.venv\Scripts\python.exe -m unittest `
  tests.test_unit_readiness `
  tests.test_order_readiness `
  tests.test_battle_allies `
  tests.test_battle_status_interface `
  tests.test_occupation_resolution `
  tests.test_snapshot_protocol `
  tests.test_client_snapshot_performance
```

Run the existing tests as well; no focused command may be used as a substitute for the full discovery run.

## 6. Determinism and performance smoke

Run the same fixture twice from the same serialized input, actions, and simulation minutes. Compare canonical Polars rows and event payloads after sorting by table key; they must be identical.

The performance smoke fixture should create 100 concurrent active engagements and advance one resolution boundary. The server resolution tick must be `≤250 ms`. Run a separate bounded client snapshot-consumption check without graphics or network I/O; it must be `≤100 ms` with a representative payload `≤2 MB`. This is a validation gate for the MVP, not a promise of a final 500-engagement benchmark.

Verification note: the feature-focused suite and both performance gates pass. In the current restricted Windows runner, two full-discovery headless-server tests fail before application startup when `multiprocessing` tries to create a pipe (`PermissionError: [WinError 5] Access is denied`); rerun those two tests in an unrestricted process environment before release.
