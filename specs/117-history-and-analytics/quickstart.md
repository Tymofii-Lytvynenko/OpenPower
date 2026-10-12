# Quickstart: History and Analytics

Run from the repository root with the project virtual environment active.

## Focused regressions

```powershell
python -m pytest tests/test_history_system.py tests/test_history_panel.py tests/test_layer_boundaries.py tests/test_game_state_ipc.py tests/test_snapshot_protocol.py -q
```

This validates configured and derived measures, changed/due/missing observations, idempotent event evidence, relationship/battle timelines, common-boundary comparisons, unit safety, deterministic ranking/ties, retention/downsampling, UI query/render projections, layer placement, state synchronization/save-load continuation, and version-3 append-tail synchronization for `history_snapshots`.

## 10-million-snapshot performance gate

```powershell
$env:RUN_HISTORY_BENCHMARKS = "1"
python -m pytest tests/test_history_performance.py -q -s
```

The controlled workload has 10,000,000 observations across 200 country series. SC-007 passes only when ranking returns the expected boundary/order in under 500 ms. The latest recorded result is 2.67 ms using the revision-matched series index; the test is opt-in because of its memory and runtime cost.

## Recorded validation

- Focused command from the section above plus `tests/test_history_performance.py`, `tests/test_layer_boundaries.py`, `tests/test_game_state_ipc.py`, and `tests/test_save_writer_atomicity.py`: **40 passed, 1 skipped** in 3.92 seconds (2026-10-07, project virtual environment, Windows). The skip is the opt-in 10-million-snapshot test; its latest separately recorded measurement is 2.67 ms.
- The save/load continuation test now confirms the history tables and deterministic samples match after IPC and disk persistence. Runtime-local `source_revision` counters may differ after loading because table revisions are reconstructed; they do not affect observations or gameplay.
- SC-007 ranking latency passes at 2.67 ms. Aggregate retention/storage budget is not defined, and neither the ranking benchmark nor the integrated optimization scenario measures 10-million-row recording/compaction; see the open measurement issue in `research.md`.
- Desktop workflow: pending; no visible game session was available for human acceptance.

## Client acceptance

In a single-player game, open **History & Analytics** from the gameplay system bar. Select a country/region indicator and a range; verify units, current/latest values, line and step modes, and visible gaps. Compare at least two countries at the displayed common boundary; check that mixed units require explicit indexing and that rankings show direction, tie rule, freshness, and exclusions. Open a relationship or event timeline, inspect source/cause evidence (including unknown causes), and copy a series or timeline as CSV. The human-visible check remains pending until a desktop game session is available; headless tests are not a substitute.

## Full repository check

```powershell
python -m pytest -q
```

Record unrelated failures separately; do not suppress them to claim feature success.
