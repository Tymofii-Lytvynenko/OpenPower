# History and Analytics Implementation Notes

## Identity and unit-comparison policy

- Historical subject IDs are stable identities. The client selector unions active subjects with persisted history-series identities so removed entities remain inspectable; when a source entity no longer exists, its ID remains the truthful fallback label rather than inventing a replacement name.
- Series with the same unit are compared at their shared time boundary using their stored values.
- If selected series have different units, the comparison can index each series to its first positive sample in the selected period (`100`), but only when that series keeps the same unit through the common boundary. The UI identifies that basis and retains the original values and units in the raw series export. This is a relative trend comparison, not a currency or physical-unit conversion; an intra-series unit transition without an authoritative conversion is unavailable.
- Absolute rankings use the indicator definition's canonical unit. Samples with other units are listed as incompatible and excluded instead of mixing their magnitudes. A future conversion requires an authoritative, time-effective conversion source; the history layer does not guess one.

## Performance evidence

The opt-in SC-007 ranking fixture contains 10,000,000 snapshots across 200 series. On the current Windows/Python 3.14.1/Polars environment, the latest run ranked the fixture in 2.67 ms, below the 500 ms target. The query uses its revision-matched series index; the aggregate retention measurement gap is tracked below.

Focused post-change regressions on 2026-10-07 reported 40 passed and one opt-in performance skip in 3.92 seconds. The query-service layer move and relationship indicator-ID correction did not alter the ranking benchmark algorithm, so SC-007 was not remeasured in that pass.

## Integrated recording optimization evidence (2026-10-08)

The three-tick `energy_crisis` comparison in `docs/SIMULATION_OPTIMIZATION_REPORT.md` reduced HistorySystem time on steps 2–3 from 2.50–2.62 s to 1.68–1.73 s after prebuilding sample templates/fields and reusing the series index during compaction. The full-workload canonical saved-state hash and all table hashes matched the baseline after each iteration. The route and AI iterations preceded the history iteration; the three-tick total fell from 29.77 s to 14.40 s. This is an integrated workload check, not a 10-million-row recording/compaction measurement or a change to the separate 2.67 ms ranking result. No long-campaign storage budget was established.

## Open performance-measurement issue

- Scope: SC-007's phrase “configured retention budget” has no aggregate row, serialized-byte, or memory ceiling. The data model defines a per-series window and cap, but the total depends on the number of configured series.
- Evidence available: deterministic compaction and per-series caps are covered by focused unit tests; the 10-million-row benchmark measures ranking latency only (2.67 ms).
- Evidence missing: a defined aggregate retention budget and a controlled 10-million-row recording/compaction/storage measurement.
- Outcome: no failing recording-performance gate has been measured, so no optimization attempt was made. Keep this as a future specification/measurement issue; the ranking latency sub-criterion passes, but do not claim the aggregate storage-budget portion of SC-007 is fully verified.

## Layer placement

- Decision: Keep the recorder in the gameplay module and the read-only analytics query service in `src/client/services/history_query_service.py`.
- Rationale: The recorder implements simulation observation policy and writes typed state tables. Querying, comparison, ranking, and CSV formatting are active calculations used only by the gameplay UI; putting them in `src/shared` violated the repository's passive-contract rule. Moving the service does not change query behavior or authoritative state.
- Alternatives considered: Keeping the query class in `src/shared` was rejected because shared must not contain logic. Moving it into `modules` was rejected because the client must not depend on simulation implementation and the service is read-only presentation analytics.
