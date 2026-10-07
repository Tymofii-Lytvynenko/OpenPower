# Campaign Evaluation Performance Research

## SC-007 Controlled Gate

`tests/test_campaign_performance.py` times the same post-domain evaluation phases used by `CampaignSystem.update`: 10,000 optional research objectives transition to completed, while 5,000 unread messages create advisor recommendations. Fixture construction is outside the measured interval. The test verifies all 10,000 objective updates and all 5,000 recommendations, with a 500 ms limit.

| Stage | Change | Measured duration | Gate |
| --- | --- | ---: | --- |
| Baseline, 2026-10-07 | No performance-specific changes; one controlled run | 616.47 ms | Fail |
| Iteration 1, 2026-10-07 | Reuse authoritative table snapshots during one evaluation boundary | 557.55 ms | Fail |
| Iteration 2, 2026-10-07 | Memoize duplicate objective measurements by their measurement inputs | 614.93 ms (single run) | Fail; no improvement observed |
| Iteration 3, 2026-10-07 | Reuse serialized evidence for identical state transitions while preserving append behavior for existing evidence | 458.45 ms | Pass |

Phase timings during diagnosis were 429.33 ms for objectives, 64.13 ms for campaign outcomes, 131.02 ms for advisor generation, and 0.05 ms for active rules. After iteration 3, objective processing took 214.24 ms, campaign outcomes 78.66 ms, advisor generation 165.45 ms, and active rules 0.04 ms.

SC-007 passes within the three-iteration limit. No further optimization iterations are planned for this gate.

## Functional implementation verification — 2026-10-07

Focused quickstart and its schema, AI, IPC, save, snapshot, and layer-boundary dependencies:

```text
74 passed, 1 skipped, 6 subtests passed in 6.07s
```

The skipped test is the opt-in performance gate. No performance remeasurement or fourth optimization iteration was performed. The previously recorded SC-007 result remains the gate evidence.

Coverage includes setup atomicity/scope, every canonical objective measurement family, all seven objective states, hold reset and decay, deterministic deadline/outcome boundaries, scoped delegation and return, advisor signal lifecycle, overview projection, and campaign continuation through snapshot, IPC, save/load, and replay.

The rendered 30-second desktop usability criterion (T020 / SC-006) remains open: no native desktop app was exposed to this task, so headless tests are not treated as a substitute. `ruff` is not installed in the workspace environment; no lint-pass claim is made.
