# Research: Battle Strategy and Force Posture

## Decisions

- Keep `BattleStrategySystem` as the authoritative command layer and keep `CombatSystem` authoritative for two-side participation, round lifecycle, casualties, and battle outcomes.
- Treat command records and unit combat projections as authoritative state; the client sends `ActionSetBattleStrategy` and renders presenter projections only.
- Reuse `MilitaryRoutePlanner`, movement access, readiness/lifecycle, `battle_units`, and `occupations` for retreat, return, and occupation. Do not invent a parallel combat side or movement contract.
- Make preset definitions scenario-configurable through `battle_strategy_presets`; per-unit-type orders remain more specific than presets.
- Protect nonparticipant battle views by filtering participant positions and country-specific losses through a viewer-scoped presenter contract. A live battle's existence and approximate aggregate may remain visible, but detailed force identity/loss data requires battle participation or another explicit authorization source.
- Preserve the performance policy: measure first, stop when the gate passes, and after at most three measured optimization iterations record the unresolved result and continue to other requirements.

## Existing implementation audit

- `BattleStrategySystem` is registered at `SystemPhase.MILITARY + 1`; it owns posture actions, seven bounded projections, data-driven presets and constraints, deterministic same-boundary precedence, retreat/regroup/return lifecycle, and occupation commands.
- `CombatSystem` consumes attack, defense, casualty, attack-risk, readiness, holding, and counterattack projections while retaining the existing two-side model.
- `battle_force_postures`, `battle_command_orders`, and `battle_casualty_records` are registered authoritative tables. Save, IPC, snapshot, schema migration, and deterministic command re-execution are covered.
- Focused tests cover posture and force-type scope, allied isolation, presets, unauthorized/scenario rejection without table or revision mutation, withdrawal/reorganization, route blocks, occupation routing without sovereignty transfer, viewer-scoped summaries, AI parity, and replayed next transitions.
- Presenter projections enforce viewer authorization and expose outcome, estimate labeling, force positions/losses, command issuer/effective time, and each own force's next action. The panel's balance bar uses the ratio domain directly.
- **Deferred performance debt**: `BattleStrategySystem.update` still materializes posture rows to find due work and, during lifecycle work, materializes unit, battle, route, and command rows. Keep this flagged for future dirty-set processing; do not tune while the controlled gate passes.

## Benchmark protocol and initial measurement

- Controlled gate: 10,000 force-posture rows, 10,000 associated unit rows, and 2,000 battles; only a bounded due subset transitions in the measured update. Three warm-up calls and five measured calls; median must be below 500 ms.
- Record Python, Polars, thread count, OS/CPU, fixture shape, all five samples, and the exact changed algorithm for each optimization iteration.
- Environment on 2026-10-07: Windows 11 build 26200, Python 3.14.1, Polars 1.36.1, 12 logical CPUs, AMD Ryzen 5 2600, `POLARS_MAX_THREADS=1`.
- Baseline command: `$env:POLARS_MAX_THREADS='1'; $env:RUN_BATTLE_STRATEGY_BENCHMARKS='1'; .venv\Scripts\python.exe -m pytest -s -q tests/test_battle_strategy_performance.py`.
- Baseline samples: **257.32, 276.14, 268.73, 280.26, 246.85 ms**; median **268.73 ms**. The gate passed (`1 passed in 2.94s`), 231.27 ms below the 500 ms limit. This is before any optimization change; **0/3** iterations used. Stop tuning unless a comparable later run regresses.

## Post-implementation performance check

- Command: `$env:POLARS_MAX_THREADS='1'; $env:RUN_BATTLE_STRATEGY_BENCHMARKS='1'; .venv\Scripts\python.exe -m pytest -s -q tests/test_battle_strategy_performance.py`.
- Samples after the functional changes: **368.71, 383.90, 354.00, 356.62, 333.11 ms**; median **356.62 ms**. Gate passed (`1 passed in 3.70s`), 143.38 ms below 500 ms.
- The median is 87.89 ms (32.7%) above the pre-change baseline, but remains within specification. **0/3 optimization iterations** used; stop here and carry the full-table scan plus this delta as monitorable performance debt for later functional convergence.
- Final focused quickstart run after exposing all seven projections in authorized history: **92 passed, 8 subtests passed in 6.64s**.

## Unresolved external acceptance

- Automated presenter and action tests cannot verify that a player can identify posture, issuer, effective time, and next action within 30 seconds in a live desktop client. Record live-client UAT separately and do not infer it from headless tests.
- Computer Use inspection returned no desktop applications, and native desktop controls are disabled in this session. T017 remains an external/manual acceptance item; no UI pass is claimed.
